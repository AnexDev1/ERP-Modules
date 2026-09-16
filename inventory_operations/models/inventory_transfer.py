from odoo import models, fields, api, _
from odoo.exceptions import UserError
from collections import defaultdict


class DrogaInventoryTransferCustom(models.Model):
    _name = 'inventory.transfer.custom'
    _description = 'Store Transfer Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
        tracking=True
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('store_manager', 'Store Manager'),
        ('requested', 'Requested'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled')
    ], default='draft', tracking=True)

    source_warehouse_id = fields.Many2one(
        'stock.warehouse',
        required=False,
        domain="[('company_id', '=', company_id)]",
        tracking=True
    )

    allowed_dest_location_ids = fields.Many2many(
        'stock.location',
        compute='_compute_allowed_dest_location_ids'
    )

    destination_location_id = fields.Many2one(
        'stock.location',
        required=True,
        domain="[('id', 'in', allowed_dest_location_ids)]",
        tracking=True
    )

    @api.depends('company_id')
    def _compute_allowed_dest_location_ids(self):
        for rec in self:
            user_warehouses = self.env.user.allowed_warehouse_ids
            if user_warehouses:
                view_locations = user_warehouses.mapped('view_location_id')
                locations = self.env['stock.location'].search([
                    ('company_id', 'in', (rec.company_id.id, False)),
                    ('usage', '=', 'internal'),
                    ('id', 'child_of', view_locations.ids)
                ])
            else:
                if self.env.user.has_group('base.group_system'):
                    locations = self.env['stock.location'].search([
                        ('company_id', 'in', (rec.company_id.id, False)),
                        ('usage', '=', 'internal')
                    ])
                else:
                    locations = self.env['stock.location'].browse()
            rec.allowed_dest_location_ids = locations

    request_date = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
        tracking=True
    )


    line_ids = fields.One2many(
        'inventory.transfer.custom.detail',
        'transfer_id',
        copy=True
    )

    picking_ids = fields.One2many(
        'stock.picking',
        'transfer_request_id'
    )

    picking_count = fields.Integer(
        compute='_compute_picking_count',
        store=True
    )

    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company
    )


    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)



    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'inventory.transfer.custom'
                ) or 'New'
        return super().create(vals_list)


    def action_submit(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Add at least one product."))

            for line in rec.line_ids:
                if line.qty_requested <= 0:
                    raise UserError(_("Requested quantity must be greater than zero."))

                if line.qty_requested > line.qty_available:
                    raise UserError(_(
                        "Requested quantity for %s exceeds available stock."
                    ) % line.product_id.display_name)

        self.write({'state': 'store_manager'})

    def action_approve(self):
        if self.picking_ids:
            raise UserError(_("Pickings already created."))

        # Clear pending activities for all users
        activities = self.env['mail.activity'].search([
            ('res_model', '=', self._name),
            ('res_id', 'in', self.ids),
            ('activity_type_id', '=', self.env.ref('mail.mail_activity_data_todo').id)
        ])
        for record_id in self.ids:
            rec_activities = activities.filtered(lambda a: a.res_id == record_id)
            if rec_activities:
                rec_activities[0].write({'note': False, 'user_id': self.env.user.id})
                rec_activities[0].action_done()
                if len(rec_activities) > 1:
                    rec_activities[1:].unlink()

        self.sudo()._create_stock_pickings()
        self.write({'state': 'requested'})
        
        for rec in self:
            rec.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=rec.create_uid.id,
                summary=_('Transfer Approved'),
                note=_('Your transfer request %s has been approved and operations have been created.') % rec.name
            )



    def _create_stock_pickings(self):
        Picking = self.env['stock.picking']
        Move = self.env['stock.move']

        for rec in self:
            transit_location = rec.company_id.internal_transit_location_id
            if not transit_location:
                raise UserError(_("Please configure an internal transit location for the company %s.") % rec.company_id.name)

            dest_warehouse = self.env['stock.warehouse'].search([
                ('view_location_id', 'parent_of', rec.destination_location_id.id),
                ('company_id', '=', rec.company_id.id)
            ], limit=1)

            warehouse_lines = defaultdict(lambda: self.env['inventory.transfer.custom.detail'])

            for line in rec.line_ids:
                warehouse_lines[line.source_warehouse_id] |= line

            for warehouse, lines in warehouse_lines.items():

                picking_type = warehouse.mtov_type_id or warehouse.int_type_id
                if not picking_type:
                    raise UserError(_(
                        "No MTOV or internal transfer type found for warehouse %s."
                    ) % warehouse.name)

                # 1. Create Issue Picking (Source -> Transit)
                issue_picking = Picking.create({
                    'picking_type_id': picking_type.id,
                    'location_id': warehouse.lot_stock_id.id,
                    'location_dest_id': transit_location.id,
                    'origin': rec.name,
                    'transfer_request_id': rec.id,
                    'company_id': rec.company_id.id,
                })

                issue_move_vals = []
                for line in lines:
                    issue_move_vals.append({
                        'product_id': line.product_id.id,
                        'product_uom_qty': line.qty_requested,
                        'product_uom': line.uom_id.id,
                        'picking_id': issue_picking.id,
                        'location_id': warehouse.lot_stock_id.id,
                        'location_dest_id': transit_location.id,
                        'company_id': rec.company_id.id,
                        'description_picking': line.product_id.display_name,
                    })

                issue_moves = Move.create(issue_move_vals)

                # 2. Create Receive Picking (Transit -> Destination)
                receipt_picking_type = dest_warehouse.mtiv_type_id or dest_warehouse.int_type_id if dest_warehouse else picking_type
                if not receipt_picking_type:
                    receipt_picking_type = picking_type
                    
                receive_picking = Picking.create({
                    'picking_type_id': receipt_picking_type.id,
                    'location_id': transit_location.id,
                    'location_dest_id': rec.destination_location_id.id,
                    'origin': rec.name,
                    'transfer_request_id': rec.id,
                    'company_id': rec.company_id.id,
                })

                receive_move_vals = []
                for issue_move in issue_moves:
                    receive_move_vals.append({
                        'product_id': issue_move.product_id.id,
                        'product_uom_qty': issue_move.product_uom_qty,
                        'product_uom': issue_move.product_uom.id,
                        'picking_id': receive_picking.id,
                        'location_id': transit_location.id,
                        'location_dest_id': rec.destination_location_id.id,
                        'company_id': rec.company_id.id,
                        'description_picking': issue_move.description_picking,
                    })

                receive_moves = Move.create(receive_move_vals)
                
                # Link Issue Moves to Receive Moves
                for issue_move, receive_move in zip(issue_moves, receive_moves):
                    issue_move.write({'move_dest_ids': [(4, receive_move.id)]})

                # Confirm and assign
                issue_moves._action_confirm()
                receive_moves._action_confirm()
                issue_moves._action_assign()



    def action_cancel(self):
        for rec in self:
            done_pickings = rec.picking_ids.filtered(lambda p: p.state == 'done')
            if done_pickings:
                raise UserError(_("Cannot cancel. Some pickings are already done."))

            rec.picking_ids.action_cancel()

        # Clear pending activities for all users
        activities = self.env['mail.activity'].search([
            ('res_model', '=', self._name),
            ('res_id', 'in', self.ids),
            ('activity_type_id', '=', self.env.ref('mail.mail_activity_data_todo').id)
        ])
        for record_id in self.ids:
            rec_activities = activities.filtered(lambda a: a.res_id == record_id)
            if rec_activities:
                rec_activities[0].write({'note': False, 'user_id': self.env.user.id})
                rec_activities[0].action_done()
                if len(rec_activities) > 1:
                    rec_activities[1:].unlink()

        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_view_pickings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Transfers'),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.picking_ids.ids)],
            'context': {'create': False},
        }



class DrogaInventoryTransferCustomDetail(models.Model):
    _name = 'inventory.transfer.custom.detail'
    _description = 'Store Transfer Request Detail'
    _check_company_auto = True

    transfer_id = fields.Many2one(
        'inventory.transfer.custom',
        ondelete='cascade'
    )

    product_id = fields.Many2one(
        'product.product',
        required=True
    )

    uom_id = fields.Many2one(
        'uom.uom',
        related='product_id.uom_id',
        readonly=True
    )

    qty_requested = fields.Float(
        default=1.0,
        required=True
    )

    qty_available = fields.Float(
        compute='_compute_qty_available',
        store=False
    )

    source_warehouse_id = fields.Many2one(
        'stock.warehouse'
    )

    _sql_constraints = [
        ('qty_positive',
         'CHECK(qty_requested > 0)',
         'Requested quantity must be positive.')
    ]


    @api.depends('product_id', 'source_warehouse_id')
    def _compute_qty_available(self):
        lines = self.filtered(lambda l: l.product_id and l.source_warehouse_id)
        if not lines:
            for rec in self:
                rec.qty_available = 0
            return

        products = lines.mapped('product_id')
        warehouses = lines.mapped('source_warehouse_id')

        quant_data = self.env['stock.quant'].read_group(
            [
                ('product_id', 'in', products.ids),
                ('location_id', 'child_of', warehouses.mapped('lot_stock_id').ids)
            ],
            ['product_id', 'quantity:sum'],
            ['product_id']
        )

        qty_map = {data['product_id'][0]: data['quantity'] for data in quant_data}

        for line in self:
            line.qty_available = qty_map.get(line.product_id.id, 0.0)




class StockPicking(models.Model):
    _inherit = 'stock.picking'

    transfer_request_id = fields.Many2one(
        'inventory.transfer.custom',
        readonly=True,
        index=True
    )

    def _action_done(self):
        res = super()._action_done()
        for picking in self:
            if picking.transfer_request_id and picking.transfer_request_id.state == 'requested':
                transfer = picking.transfer_request_id
                all_done = all(p.state in ('done', 'cancel') for p in transfer.picking_ids)
                if all_done:
                    transfer.write({'state': 'received'})
                    transfer.activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=transfer.create_uid.id,
                        summary=_('Transfer Fully Received'),
                        note=_('All operations for transfer request %s have been completed.') % transfer.name
                    )
        return res
