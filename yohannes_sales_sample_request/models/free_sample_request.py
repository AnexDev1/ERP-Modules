from odoo import models, fields, api,_
from odoo.exceptions import UserError


class ResUsers(models.Model):
    _inherit = 'res.users'

    stock_location_id = fields.Many2one('stock.location', string='Stock Location',help='Personal stock location for this sales rep.')

class FreeSampleRequest(models.Model):
    _name = 'free.sample.request'
    _description = 'Sample Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True
    

    FSR_reference = fields.Char('Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    name = fields.Char(string='Reference', related='FSR_reference', store=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    issue_type = fields.Selection([
        ('free', 'Free Sample Request'),
        ('return', 'Sample to be Returned'),
        ('consignment', 'Consignment Issues')
    ], string='Issue Type', required=True, readonly=True, default='free')
    requested_by = fields.Many2one('res.users', string='Requested By',default=lambda self: self.env.user, readonly=True)
    issue_date = fields.Date(string='Issue Date', default=fields.Date.today)
    remarks = fields.Text(string='Remarks')
    line_ids = fields.One2many('free.sample.request.line', 'request_id', string='Product Lines')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('Operations_store_manager', 'Operations/Store Manager'),
        ('requested', 'Requested'),
        ('proceed', 'Proceed'),
        ('rejected','Rejected')
    ], string='Status', default='draft', tracking=True)
    delivery_id = fields.Many2one('stock.picking', string='Delivery Order', readonly=True, copy=False)
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True, copy=False)
    is_free_sample = fields.Boolean(string='Free Sample', compute='_compute_is_free_sample', store=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('FSR_reference', 'New') == 'New':
                company_id = vals.get('company_id', self.env.company.id)
                seq = self.env['ir.sequence'].search([('code', '=', 'free.sample.request'), ('company_id', '=', company_id)], limit=1)
                if not seq:
                    seq = self.env['ir.sequence'].sudo().create({
                        'name': f'Free Sample Request [{company_id}]',
                        'code': 'free.sample.request',
                        'prefix': 'FS/ISSUE/%(year)s/',
                        'padding': 5,
                        'company_id': company_id,
                    })
                vals['FSR_reference'] = seq.next_by_id() or 'New'
        return super().create(vals_list)

    def action_submit(self):
        self.state = 'Operations_store_manager'
        self.message_post(body='Request submitted for approval.')
        # Notify approvers
        try:
            approver_group = self.env.ref('yohannes_sales_sample_request.group_sample_request_approver')
            for user in approver_group.users:
                self.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=f'Sample Request Approval - {self.FSR_reference}',
                    note=f'A new sample request from {self.requested_by.name} requires your approval.',
                    user_id=user.id,
                )
        except Exception:
            pass

    def action_approve(self):
        """Create draft delivery and draft invoice (for free samples only)"""
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
        # Create draft delivery order for both free and return samples
        self._create_delivery_order()

        # Create draft invoice ONLY for Free samples (as expense)
       # if self.issue_type == 'free':
        #    self._create_expense_invoice()

        self.state = 'requested'
        self.message_post(body='Request approved. Delivery and Invoice created in draft.')

        # Notify initiator that request has been approved
        initiator = self.requested_by or self.create_uid
        if initiator:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=f'Sample Request Approved - {self.FSR_reference}',
                note='Your sample request has been approved. A delivery order has been created.',
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
                summary=f'Sample Request Rejected - {self.FSR_reference}',
                note='Your sample request has been rejected.',
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
                summary=f'Sample Request Cancelled - {self.FSR_reference}',
                note='Your sample request has been cancelled.',
                user_id=initiator.id,
            )

    #def action_issue(self):
     #   """Process delivery and invoice when issuing products"""
      #  if not self.delivery_id:
       #     raise UserError('Delivery order not found. Please create one first.')

        # Check stock availability before issuing
      #  for line in self.line_ids:
          #  if line.quantity_issued > line.balance_store:
           #     raise UserError(f'Insufficient stock for {line.product_id.name} in store.')

        # Process delivery - confirm and validate
        #if self.delivery_id.state == 'draft':
         #   self.delivery_id.action_confirm()

        #if self.delivery_id.state != 'done':
         #   self.delivery_id.action_assign()

            # Set done quantities
          #  for move in self.delivery_id.move_ids_without_package:
           #     move.quantity_done = move.product_uom_qty

            #self.delivery_id.button_validate()

        # Post invoice if exists (for free samples)
        #if self.invoice_id and self.invoice_id.state == 'draft':
         #   self.invoice_id.action_post()
          #  self.message_post(body='Invoice posted as expense.')

       # self.state = 'issued'
        #self.message_post(body='Products issued successfully.')



    #def action_done(self):
     #   """Mark request as completed"""
      #  if self.delivery_id.state == 'done':
       #     # For Free samples: Verify invoice is posted
        #    if self.issue_type == 'free' and self.invoice_id.state != 'posted':
         #       raise UserError('Please post the invoice before completing.')

      #      self.state = 'done'
       #     self.message_post(body='Sample request completed.')
        #else:
         #   raise UserError('Delivery is not completed yet.')

    def action_view_delivery(self):
        """Open delivery order(s) related to this request"""
        pickings = self.env['stock.picking'].search(['|', ('id', '=', self.delivery_id.id), ('origin', '=', self.name)])
        if not pickings:
             raise UserError('No delivery orders found.')

        action = self.env.ref('stock.action_picking_tree_all').read()[0]
        if len(pickings) == 1:
            action['views'] = [(self.env.ref('stock.view_picking_form').id, 'form')]
            action['res_id'] = pickings.id
        else:
            action['domain'] = [('id', 'in', pickings.ids)]
        return action

    def action_view_invoice(self):
        """Open invoice"""
        if not self.invoice_id:
            raise UserError('No invoice found for this request.')
        action = self.env.ref('account.action_move_out_invoice_type').read()[0]
        action['views'] = [(self.env.ref('account.view_move_form').id, 'form')]
        action['res_id'] = self.invoice_id.id
        return action

    def _create_delivery_order(self):
        """Create DRAFT delivery orders grouped by warehouse"""
        # Default locations for fallback (though lines should ideally have a warehouse)
        fallback_customer_location = self.env.ref('stock.stock_location_customers')
        fallback_store_location = self.env.ref('stock.stock_location_stock')
        default_picking_type = self.env.ref('stock.picking_type_out')

        # Group lines by warehouse
        lines_by_warehouse = {}
        for line in self.line_ids:
            if line.quantity_requested <= 0:
                continue
            warehouse = line.warehouse_id
            if warehouse not in lines_by_warehouse:
                lines_by_warehouse[warehouse] = []
            lines_by_warehouse[warehouse].append(line)

        created_pickings = self.env['stock.picking']

        # Extract only the reference number from the source document
        source_ref = self.name
        if 'Sample Request:' in source_ref:
            source_ref = source_ref.split('Sample Request:')[-1].strip()
        # Or if it's in a specific format like "Sample Request: CON/ISSUE/2026/00001"
        # You can also use regex or split by colon to get the part after the colon

        for warehouse, lines in lines_by_warehouse.items():
            store_location = warehouse.lot_stock_id if warehouse else fallback_store_location

            # Dynamically fetch Operation Type based on the custom field
            picking_type = self.env['stock.picking.type'].search([
                ('warehouse_id', '=', warehouse.id),
                ('cons_sample_operation_type', '=', 'issue'),
                ('company_id', '=', warehouse.company_id.id)
            ], limit=1)

            if not picking_type:
                picking_type = warehouse.out_type_id if warehouse else default_picking_type

            # Dynamically fetch Customer Location based on the custom field
            customer_location = self.env['stock.location'].search([
                ('cons_sample_type', '=', 'free_sample'),
                ('company_id', '=', warehouse.company_id.id)
            ], limit=1)

            # Use locations configured on the Operation Type if available, else fallback
            final_store_location = picking_type.default_location_src_id or store_location
            final_customer_location = customer_location or picking_type.default_location_dest_id or fallback_customer_location

            move_lines = []
            for line in lines:
                move_lines.append((0, 0, {
                    'description_picking': line.product_id.name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity_issued or line.quantity_requested,
                    'product_uom': line.uom_id.id,
                    'location_id': final_store_location.id,
                    'location_dest_id': final_customer_location.id,
                    'state': 'draft',
                }))

            picking_vals = {
                'partner_id': self.partner_id.id,
                'owner_id': self.partner_id.id,
                'picking_type_id': picking_type.id,
                'location_id': final_store_location.id,
                'location_dest_id': final_customer_location.id,
                'origin': source_ref,  # Using the extracted reference number
                'state': 'draft',
                'move_ids': move_lines,
            }

            picking = self.env['stock.picking'].create(picking_vals)
            picking.scheduled_date = self.issue_date
            picking.note = f"Source: {self.name}\nCustomer: {self.partner_id.name}"
            picking.action_confirm()
            picking.action_assign()
            created_pickings |= picking

        if created_pickings:
            self.delivery_id = created_pickings[0].id
            self.message_post(body=f'{len(created_pickings)} Delivery Order(s) created in Ready state for Source: {self.name}.')

        return created_pickings

   # def _create_expense_invoice(self):
    #    """Create DRAFT expense invoice for free samples with sample request reference"""
     #   if not self.line_ids:
      #      raise UserError('No products to invoice.')

        # Get default journal for expenses
       # journal = self.env['account.journal'].search([
        #    ('type', '=', 'purchase'),
         #   ('company_id', '=', self.env.company.id)
       # ], limit=1)

        #if not journal:
         #   raise UserError('No purchase journal found. Please configure one.')

        # Get expense account from product category or default
       # expense_account = False
       # for line in self.line_ids:
        #    if line.product_id.categ_id.property_account_expense_categ_id:
         #       expense_account = line.product_id.categ_id.property_account_expense_categ_id
          #      break

        # If no category account, get default expense account
       # if not expense_account:
        #    expense_account = self.env['account.account'].search([
         #       ('company_ids', 'in', [self.env.company.id]),
          #      ('account_type', '=', 'expense'),
           # ], limit=1)

       # if not expense_account:
       #     raise UserError('No expense account found. Please configure one.')

        # Create invoice lines
       # invoice_lines = []
       # for line in self.line_ids:
       #     if line.quantity_requested > 0:
        #        invoice_lines.append((0, 0, {
         #           'product_id': line.product_id.id,
          #          'name': f"Free Sample: {line.product_id.name}",
           #         'quantity': line.quantity_issued or line.quantity_requested,
            #        'price_unit': 0.0,  # Free sample - no charge
             #       'account_id': expense_account.id,
              #  }))

        # Create invoice as vendor bill (expense) in DRAFT state
       # invoice = self.env['account.move'].create({
        #    'move_type': 'in_invoice',  # Vendor bill
         #   'partner_id': self.partner_id.id,
          #  'invoice_date': self.issue_date,
           # 'journal_id': journal.id,
           # 'invoice_origin': f'Sample Request: {self.name}',  # Source document reference
           # 'ref': f'Sample Request: {self.name}',  # Reference field
           # 'narration': f'Free Sample Issuance - Expense\nSample Request: {self.name}\nCustomer: {self.partner_id.name}',
           # 'invoice_line_ids': invoice_lines,
           # 'state': 'draft',  # Keep as draft
       # })

       # self.invoice_id = invoice.id
       # self.message_post(body=f'Draft Expense Invoice {invoice.name} created with reference to Sample Request.')
       # return invoice

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



class FreeSampleRequestLine(models.Model):
    _name = 'free.sample.request.line'
    _description = 'Free Sample Request Line'

    request_id = fields.Many2one('free.sample.request', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True,domain="[('type', '=', 'consu')]")  # Storable products only
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', compute='_compute_uom_id', store=True,readonly=True)
    quantity_requested = fields.Float(string='Quantity', required=True)
    balance_rep = fields.Float(string='Sales Rep Stock Balance', compute='_compute_balances', readonly=True)
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