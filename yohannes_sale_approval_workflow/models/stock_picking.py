from odoo import models, fields, api, _
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _name = 'stock.picking'
    _inherit = ['stock.picking', 'mail.thread', 'mail.activity.mixin']

    approval_state = fields.Selection([
        ('draft', 'Not Requested'),
        ('pending', 'Store Manager'),
        ('approved', 'Approved')
    ], string='Approval Status', default='draft', tracking=True, copy=False)

    picking_display_state = fields.Selection([
        ('draft', 'Draft'),
        ('ready', 'Ready'),
        ('store_manager', 'Store Manager'),
        ('done', 'Done'),
    ], string='Status', compute='_compute_picking_display_state', store=False)

    @api.depends('state', 'approval_state', 'picking_type_id.code')
    def _compute_picking_display_state(self):
        for picking in self:
            if picking.state == 'done':
                picking.picking_display_state = 'done'
            elif picking.state == 'draft':
                picking.picking_display_state = 'draft'
            elif picking.picking_type_id.code == 'incoming':
                if picking.approval_state == 'pending':
                    picking.picking_display_state = 'store_manager'
                else:
                    picking.picking_display_state = 'ready'
            else:
                picking.picking_display_state = 'ready' if picking.state in ('confirmed', 'assigned') else 'draft'

    requires_approval = fields.Boolean(
        compute='_compute_requires_approval',
        store=False
    )

    requester_id = fields.Many2one('res.users', string='Requester', tracking=True)

    is_store_manager = fields.Boolean(
        compute='_compute_is_store_manager', store=False
    )

    @api.depends_context('uid')
    def _compute_is_store_manager(self):
        is_mgr = self.env.user.has_group('yohannes_sale_approval_workflow.group_store_manager')
        for picking in self:
            picking.is_store_manager = is_mgr

    @api.depends('picking_type_id.code')
    def _compute_requires_approval(self):
        for picking in self:
            picking.requires_approval = picking.picking_type_id.code == 'incoming'

    def action_approve(self):
        for picking in self:
            if picking.approval_state != 'pending':
                raise UserError(_('Only pending requests can be approved.'))

            if not self.env.user.has_group('yohannes_sale_approval_workflow.group_store_manager'):
                raise UserError(_('Only Store Managers can approve stock receipts.'))

            picking.write({'approval_state': 'approved'})

            # Mark activities as done
            activities = self.env['mail.activity'].search([
                ('res_id', '=', picking.id),
                ('res_model_id', '=', self.env['ir.model']._get('stock.picking').id),
                ('activity_type_id', '=', self.env.ref('mail.mail_activity_data_todo').id)
            ])
            if activities:
                activities[0].write({'note': False, 'user_id': self.env.user.id})
                activities[0].action_done()
                if len(activities) > 1:
                    activities[1:].unlink()

        # Auto-validate by using the standard Odoo workflow (which safely handles quantities, backorders, and wizards).
        # We pass skip_approval=True to prevent button_validate from intercepting it again.
        return self.with_context(skip_approval=True).button_validate()

    is_proforma_delivery = fields.Boolean(
        related='sale_id.is_proforma',
        string="Is Proforma Delivery",
        readonly=True
    )
    sale_invoice_count = fields.Integer(
        related='sale_id.invoice_count',
        string="Sale Invoice Count",
        readonly=True
    )

    def button_validate(self):
        for picking in self:
            if picking.is_proforma_delivery and picking.sale_invoice_count == 0:
                raise UserError(_("This is a Proforma Delivery. You cannot validate it until an invoice is created for the Sales Order."))

        if self.env.context.get('skip_approval'):
            return super(StockPicking, self).button_validate()

        for picking in self:
            if picking.requires_approval:
                if picking.approval_state == 'draft':
                    # Intercept — send to approval instead of validating
                    picking.write({
                        'approval_state': 'pending',
                        'requester_id': self.env.user.id
                    })

                    group_store_manager = self.env.ref(
                        'yohannes_sale_approval_workflow.group_store_manager',
                        raise_if_not_found=False
                    )
                    if not group_store_manager:
                        raise UserError(_('Store Manager group not found.'))

                    self.env.cr.execute(
                        "SELECT uid FROM res_groups_users_rel WHERE gid = %s",
                        [group_store_manager.id]
                    )
                    user_ids = [row[0] for row in self.env.cr.fetchall()]
                    managers = self.env['res.users'].browse(user_ids)
                    if not managers:
                        raise UserError(_('No Store Manager found to assign the approval activity.'))

                    for manager in managers:
                        self.env['mail.activity'].create({
                            'res_id': picking.id,
                            'res_model_id': self.env['ir.model']._get('stock.picking').id,
                            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                            'summary': _('Receipt Approval Required'),
                            'note': _('Please review and approve this stock receipt.'),
                            'user_id': manager.id,
                        })

                    # Reload the view so the status bar moves to Store Manager
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    }

                elif picking.approval_state == 'pending':
                    raise UserError(_('This receipt is waiting for Store Manager approval.'))

        # No approval needed, or already approved — normal validation
        res = super(StockPicking, self).button_validate()
        
        # CLEAR DELIVERY PREPARATION ACTIVITIES ON SALE ORDER
        for picking in self:
            if picking.sale_id:
                del_activities = self.env['mail.activity'].search([
                    ('res_model', '=', 'sale.order'),
                    ('res_id', '=', picking.sale_id.id),
                    ('summary', 'ilike', 'Delivery Preparation')
                ])
                if del_activities:
                    del_activities[0].write({'note': False, 'user_id': self.env.user.id})
                    del_activities[0].action_done()
                    if len(del_activities) > 1:
                        del_activities[1:].unlink()
                        
        return res

    def _action_done(self):
        # Inject force_period_date into context BEFORE super() so stock_account picks it up!
        # stock_account uses force_period_date to backdate accounting entries.
        ctx_update = {}
        for picking in self:
            if picking.sale_id and picking.sale_id.date_order:
                ctx_update['force_period_date'] = picking.sale_id.date_order.date()
                break
        
        if ctx_update:
            self = self.with_context(**ctx_update)
            
        res = super(StockPicking, self)._action_done()

        # Now, forcefully update the picking and move dates, because stock.move uses fields.Datetime.now() explicitly
        for picking in self:
            if picking.sale_id and picking.sale_id.date_order:
                forced_date = picking.sale_id.date_order
                
                # Update picking date_done
                picking.write({'date_done': forced_date})
                
                # Update moves and valuation layers
                for move in picking.move_ids.filtered(lambda m: m.state == 'done'):
                    move.write({'date': forced_date})
                    # Update stock_valuation_layer create_date via SQL (since ORM protects create_date)
                    if 'stock.valuation.layer' in self.env:
                        self.env.cr.execute(
                            "UPDATE stock_valuation_layer SET create_date = %s WHERE stock_move_id = %s",
                            (forced_date, move.id)
                        )
        return res

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super(StockPicking, self).create(vals_list)
        for picking in pickings:
            # Strip order-source prefix from sequence if company doesn't use order source
            if picking.company_id and not picking.company_id.enable_order_source and picking.name:
                if 'WHOLESALE/' in picking.name:
                    picking.name = picking.name.replace('WHOLESALE/', '')
                elif 'RETAIL/' in picking.name:
                    picking.name = picking.name.replace('RETAIL/', '')
        return pickings
