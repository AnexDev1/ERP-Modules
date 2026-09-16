from odoo import models, fields, api
from odoo.exceptions import UserError


class ResUsers(models.Model):
    _inherit = 'res.users'

    stock_location_id = fields.Many2one('stock.location', string='Stock Location',
                                        help='Personal stock location for this sales rep.')


class ConsignmentReturn(models.Model):
    _name = 'consignment.return'
    _description = 'Consignment Return'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'
    _check_company_auto = True

    name = fields.Char(string='Reference', default='New', readonly=True, copy=False)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    return_type = fields.Selection([
        ('return', 'Sample Return'),
        ('consignment', 'Consignment Return')
    ], string='Return Type', required=True,readonly=True, default='consignment')
    requested_by = fields.Many2one('res.users', string='Requested By', default=lambda self: self.env.user,
                                   readonly=True)
    return_date = fields.Date(string='Return Date', default=fields.Date.today)
    remarks = fields.Text(string='Remarks')
    line_ids = fields.One2many('consignment.return.line', 'request_id', string='Product Lines')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('Operations_store_manager', 'Operations/Store Manager'),
        ('requested', 'Requested'),
        ('proceed', 'Proceed'),
        ('rejected', 'Rejected')
    ], string='Status', default='draft', tracking=True)
    delivery_id = fields.Many2one('stock.picking', string='Return Picking', readonly=True, copy=False)
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True, copy=False)
    consignment_request_id = fields.Many2one('consignment.request',string='Consignment Request Reference',
                        domain="[('partner_id', '=', partner_id), ('delivery_id', '!=', False)]",
                        help='Select the Consignment Request for this customer. The delivery order is auto-filled from the request.',
                        copy=False,)
    source_picking_id = fields.Many2one('stock.picking',string='Source Delivery Order',compute='_compute_source_picking',
                                        store=True,readonly=True,copy=False,)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)



    @api.depends('consignment_request_id')
    def _compute_source_picking(self):
        for rec in self:
            rec.source_picking_id = rec.consignment_request_id.delivery_id if rec.consignment_request_id else False

    @api.onchange('consignment_request_id')
    def _onchange_consignment_request_id(self):
        """Auto-fill product lines from the selected Consignment Request."""
        if self.consignment_request_id:
            new_lines = []
            for req_line in self.consignment_request_id.line_ids:
                new_lines.append((0, 0, {
                    'product_id': req_line.product_id.id,
                    'quantity_requested': req_line.quantity_issued or req_line.quantity_requested,
                    'uom_id': req_line.uom_id.id if req_line.uom_id else False,
                    'warehouse_id': req_line.warehouse_id.id if req_line.warehouse_id else False,
                }))
            self.line_ids = [(5, 0, 0)] + new_lines
        else:
            self.line_ids = [(5, 0, 0)]

    #@api.model_create_multi
    #def create(self, vals_list):
     #   for vals in vals_list:
      #      if vals.get('name', 'New') == 'New':
       #         vals['name'] = self.env['ir.sequence'].next_by_code('consignment.return') or 'New'
        #return super().create(vals_list)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                company_id = vals.get('company_id', self.env.company.id)
                seq = self.env['ir.sequence'].search([('code', '=', 'consignment.return'), ('company_id', '=', company_id)], limit=1)
                if not seq:
                    seq = self.env['ir.sequence'].sudo().create({
                        'name': f'Consignment Return [{company_id}]',
                        'code': 'consignment.return',
                        'prefix': 'CON/RECEIPT/%(year)s/',
                        'padding': 5,
                        'company_id': company_id,
                    })
                vals['name'] = seq.next_by_id() or 'New'
        return super().create(vals_list)

    def action_submit(self):
        self.state = 'Operations_store_manager'
        self.message_post(body='Request submitted for approval.')
        # Notify approvers
        try:
            approver_group = self.env.ref('yohannes_sales_consignment.group_consignment_request_approver')
            for user in approver_group.users:
                self.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=f'Consignment Return Approval - {self.name}',
                    note=f'A new consignment return from {self.requested_by.name} requires your approval.',
                    user_id=user.id,
                )
        except Exception:
            pass

    def action_approve(self):
        """Create a return picking from the source consignment delivery order"""
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
        self._create_return_picking()
        self.state = 'requested'

        # Update settlement status on the related consignment request
        if self.consignment_request_id:
            self.consignment_request_id.settlement_type = 'returned'

        self.message_post(body='Request approved. Return picking created in draft.')

        # Notify initiator that return has been approved
        initiator = self.requested_by or self.create_uid
        if initiator:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=f'Consignment Return Approved - {self.name}',
                note='Your consignment return has been approved. A return picking has been created.',
                user_id=initiator.id,
            )

        # Notification to Store
        inventory_users = self.env.ref('yohannes_sales_sample_request.group_sample_request_initiator').user_ids
        self.message_subscribe(partner_ids=inventory_users.partner_id.ids)

    def action_reject(self):
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
        self.state = 'rejected'
        self.message_post(body='Request rejected.')
        # Notify initiator
        initiator = self.requested_by or self.create_uid
        if initiator:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=f'Consignment Return Rejected - {self.name}',
                note='Your consignment return has been rejected.',
                user_id=initiator.id,
            )

    def action_cancel(self):
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
        self.state = 'rejected'
        self.message_post(body='Request rejected.')
        # Notify initiator
        initiator = self.requested_by or self.create_uid
        if initiator:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=f'Consignment Return Cancelled - {self.name}',
                note='Your consignment return has been cancelled.',
                user_id=initiator.id,
            )


    def action_view_delivery(self):
        """Open the return picking created for this consignment return"""
        if not self.delivery_id:
            raise UserError('No return picking found. Please approve the request first.')
        action = self.env.ref('stock.action_picking_tree_all').read()[0]
        action['views'] = [(self.env.ref('stock.view_picking_form').id, 'form')]
        action['res_id'] = self.delivery_id.id
        return action

    def action_view_source_delivery(self):
        """Open the original source delivery order"""
        if not self.source_picking_id:
            raise UserError('No source delivery order found.')
        action = self.env.ref('stock.action_picking_tree_all').read()[0]
        action['views'] = [(self.env.ref('stock.view_picking_form').id, 'form')]
        action['res_id'] = self.source_picking_id.id
        return action

    def action_view_invoice(self):
        """Open invoice"""
        if not self.invoice_id:
            raise UserError('No invoice found for this request.')
        action = self.env.ref('account.action_move_out_invoice_type').read()[0]
        action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
        action['res_id'] = self.invoice_id.id
        return action

    def _create_return_picking(self):
        """Create a return picking linked to the original consignment delivery,
        using a specialized 'Consignment/sample receive' operation type if found.
        """
        if not self.source_picking_id:
            raise UserError(
                'Please select the Consignment Request Reference so the '
                'source delivery order is identified.'
            )
        if self.source_picking_id.state != 'done':
            raise UserError(
                'The source delivery order must be validated (Done) before creating a return.'
            )
        if not self.line_ids:
            raise UserError('No product lines found. Please select a Consignment Request first.')

        source = self.source_picking_id
        warehouse = source.picking_type_id.warehouse_id
        
        # Dynamically fetch Operation Type based on the custom field
        return_type = self.env['stock.picking.type'].search([
            ('warehouse_id', '=', warehouse.id),
            ('cons_sample_operation_type', '=', 'receive'),
            ('company_id', '=', warehouse.company_id.id)
        ], limit=1)

        if not return_type:
            return_type = source.picking_type_id.return_picking_type_id

        if not return_type:
            raise UserError(
                f'No return picking type configured for operation "{source.picking_type_id.name}". '
                'Please configure it in Inventory → Configuration → Operations.'
            )

        fallback_store_location = source.location_id        # original source = return destination
        fallback_customer_location = source.location_dest_id  # original dest = return source

        # For returns, prioritize the original delivery locations (reversing dest as source and source as dest)
        customer_location = fallback_customer_location or return_type.default_location_src_id
        store_location = fallback_store_location or return_type.default_location_dest_id

        source_move_by_product = {
            move.product_id.id: move
            for move in source.move_ids.filtered(lambda m: m.state == 'done')
        }

        move_lines = []
        for line in self.line_ids:
            orig_move = source_move_by_product.get(line.product_id.id)
            move_vals = {
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity_requested,
                'product_uom': line.uom_id.id,
                'location_id': customer_location.id,     # From customer
                'location_dest_id': store_location.id,   # Back to store
                'description_picking': line.product_id.name,
                'state': 'draft',
            }
            if orig_move:
                move_vals['origin_returned_move_id'] = orig_move.id
            move_lines.append((0, 0, move_vals))

        return_picking = self.env['stock.picking'].create({
            'partner_id': self.partner_id.id,
            'owner_id': self.partner_id.id,
            'picking_type_id': return_type.id,
            'location_id': customer_location.id,
            'location_dest_id': store_location.id,
            'origin': self.name,
            'move_ids': move_lines,
        })
        return_picking.scheduled_date = self.return_date
        return_picking.action_confirm()
        return_picking.action_assign()
        return_picking.note = (
            f"Consignment Return: {self.name}\n"
            f"Original Delivery: {source.name}\n"
            f"Customer: {self.partner_id.name}"
        )
        self.delivery_id = return_picking.id
        self.message_post(
            body=f'Return picking <b>{return_picking.name}</b> created in draft '
                 f'(return of consignment delivery {source.name}).'
        )
        return return_picking

    def _create_expense_invoice(self):
        """Create DRAFT expense invoice for free samples with sample request reference"""
        if not self.line_ids:
            raise UserError('No products to invoice.')

        # Get default journal for expenses
        journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)

        if not journal:
            raise UserError('No purchase journal found. Please configure one.')

        # Get expense account from product category or default
        expense_account = False
        for line in self.line_ids:
            if line.product_id.categ_id.property_account_expense_categ_id:
                expense_account = line.product_id.categ_id.property_account_expense_categ_id
                break

        # If no category account, get default expense account
        if not expense_account:
            expense_account = self.env['account.account'].search([
                ('company_ids', 'in', [self.env.company.id]),
                ('account_type', '=', 'expense'),
            ], limit=1)

        if not expense_account:
            raise UserError('No expense account found. Please configure one.')

        # Create invoice lines
        invoice_lines = []
        for line in self.line_ids:
            if line.quantity_requested > 0:
                invoice_lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'name': f"Free Sample: {line.product_id.name}",
                    'quantity': line.quantity_issued or line.quantity_requested,
                    'price_unit': 0.0,  # Free sample - no charge
                    'account_id': expense_account.id,
                }))

        # Create invoice as vendor bill (expense) in DRAFT state
        invoice = self.env['account.move'].create({
            'move_type': 'in_invoice',  # Vendor bill
            'partner_id': self.partner_id.id,
            'invoice_date': self.return_date,
            'journal_id': journal.id,
            'invoice_origin': f'Consignment Return: {self.name}',  # Source document reference
            'ref': f'Consignment Return: {self.name}',  # Reference field
            'narration': f'Consignment Return - Expense\nConsignment Return: {self.name}\nCustomer: {self.partner_id.name}',
            'invoice_line_ids': invoice_lines,
            'state': 'draft',  # Keep as draft
        })

        self.invoice_id = invoice.id
        self.message_post(body=f'Draft Expense Invoice {invoice.name} created with reference to Sample Request.')
        return invoice

        # Clean up related documents when sample request is deleted/cancelled

    def unlink(self):
        for record in self:
            if record.state not in ['draft', 'rejected']:
                raise UserError('Cannot delete a Sample Request that is not in Draft or Rejected state.')
            # Delete related draft documents
            if record.delivery_id and record.delivery_id.state == 'draft':
                record.delivery_id.unlink()
            if record.invoice_id and record.invoice_id.state == 'draft':
                record.invoice_id.unlink()
        return super().unlink()


class ConsignmentReturnLine(models.Model):
    _name = 'consignment.return.line'
    _description = 'Consignment Return Line'
    _check_company_auto = True

    request_id = fields.Many2one('consignment.return', required=True)
    company_id = fields.Many2one(related='request_id.company_id', store=True)
    product_id = fields.Many2one('product.product', string='Product', required=True,
                                 domain="[('type', '=', 'consu')]")  # Storable products only
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', compute='_compute_uom_id', store=True,
                             readonly=True)
    quantity_requested = fields.Float(string='Quantity', required=True)
    balance_rep = fields.Float(string='Stock Balance', compute='_compute_balances', readonly=True)
    balance_store = fields.Float(string='Stock Balance', compute='_compute_balances', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    quantity_issued = fields.Float(string='Quantity Issued')

    @api.depends('product_id')
    def _compute_uom_id(self):
        for rec in self:
            rec.uom_id = rec.product_id.uom_id if rec.product_id else False

    @api.depends('product_id', 'request_id.requested_by', 'request_id.state', 'warehouse_id')
    def _compute_balances(self):
        for line in self:
            if not line.product_id:
                line.balance_rep = 0
                line.balance_store = 0
                continue
                # Sales Rep location
            rep_location = line.request_id.requested_by.stock_location_id

            # Use selected warehouse location, fallback to default stock location
            store_location = line.warehouse_id.lot_stock_id if line.warehouse_id else self.env.ref('stock.stock_location_stock')

            line.balance_rep = self.env['stock.quant']._get_available_quantity(
                line.product_id, rep_location) if rep_location else 0
            line.balance_store = self.env['stock.quant']._get_available_quantity(
                line.product_id, store_location)