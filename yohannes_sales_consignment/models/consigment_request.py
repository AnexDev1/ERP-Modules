from odoo import models, fields, api
from odoo.exceptions import UserError


class ResUsers(models.Model):
    _inherit = 'res.users'

    stock_location_id = fields.Many2one('stock.location', string='Stock Location',
                                        help='Personal stock location for this sales rep.')


class ConsignmentRequest(models.Model):
    _name = 'consignment.request'
    _description = 'Consignment Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'
    _check_company_auto = True

    name = fields.Char(string='Reference', default='New', readonly=True, copy=False)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    issue_type = fields.Selection([
        ('free', 'Free Sample Request'),
        ('return', 'Sample to be Returned'),
        ('consignment', 'Consignment Issues')
    ], string='Issue Type', required=True, readonly=True, default='consignment')
    requested_by = fields.Many2one('res.users', string='Requested By',default=lambda self: self.env.user, readonly=True)
    issue_date = fields.Date(string='Issue Date', default=fields.Date.today)
    remarks = fields.Text(string='Remarks')
    line_ids = fields.One2many('consignment.request.line', 'request_id', string='Product Lines')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('Operations_store_manager', 'Operations/Store Manager'),
        ('requested', 'Requested'),
        ('proceed', 'Proceed'),
        ('rejected', 'Rejected')
    ], string='Status', default='draft', tracking=True)

    delivery_id = fields.Many2one('stock.picking', string='Delivery Order', readonly=True, copy=False)
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True, copy=False)
    picking_count = fields.Integer(compute='_compute_picking_count', string='Picking Count')
    #is_free_sample = fields.Boolean(string='Free Sample', compute='_compute_is_free_sample', store=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    settlement_type = fields.Selection([
        ('pending', 'Pending'),
        ('returned', 'Returned'),
        ('sold', 'Converted (Sale/Purchase)'),
    ], string='Status', default='pending', tracking=True, readonly=True)
    
    consignment_role = fields.Selection([
        ('giver', 'Consignment Issuer'),
        ('receiver', 'Consignment Receiver')
    ], string='Consignment Type', default='giver', required=True, tracking=True, copy=False)
    
    sale_order_ids = fields.One2many('sale.order', 'consignment_request_id', string='Related Sales')
    sale_count = fields.Integer(compute='_compute_sale_count', string='Sale Count')
    local_purchase_ids = fields.One2many('local.purchase.requisition', 'consignment_request_id', string='Local Purchases')
    local_purchase_count = fields.Integer(compute='_compute_local_purchase_count', string='Local Purchase Count')

    def _compute_sale_count(self):
        for rec in self:
            rec.sale_count = len(rec.sale_order_ids)

    def _compute_local_purchase_count(self):
        for rec in self:
            rec.local_purchase_count = len(rec.local_purchase_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                company_id = vals.get('company_id', self.env.company.id)
                seq = self.env['ir.sequence'].search([('code', '=', 'consignment.request'), ('company_id', '=', company_id)], limit=1)
                if not seq:
                    seq = self.env['ir.sequence'].sudo().create({
                        'name': f'Consignment Request [{company_id}]',
                        'code': 'consignment.request',
                        'prefix': 'CON/ISSUE/%(year)s/',
                        'padding': 5,
                        'company_id': company_id,
                    })
                vals['name'] = seq.next_by_id() or 'New'
        return super().create(vals_list)

   # @api.model_create_multi
    #def create(self, vals_list):
     #   for vals in vals_list:
      #      if vals.get('name', 'New') == 'New':
       #         vals['name'] = self.env['ir.sequence'].next_by_code('general.request') or 'New'
        #return super().create(vals_list)

    def action_submit(self):
        self.state = 'Operations_store_manager'
        self.message_post(body='Request submitted for approval.')
        # Notify approvers
        try:
            approver_group = self.env.ref('yohannes_sales_consignment.group_consignment_request_approver')
            for user in approver_group.users:
                self.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=f'Consignment Request Approval - {self.name}',
                    note=f'A new consignment request from {self.requested_by.name} requires your approval.',
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
        #if self.issue_type == 'free':
         #   self._create_expense_invoice()

        self.state = 'requested'
        self.message_post(body='Request approved. Delivery and Invoice created in draft.')

        # Notify initiator that request has been approved
        initiator = self.requested_by or self.create_uid
        if initiator:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=f'Consignment Request Approved - {self.name}',
                note='Your consignment request has been approved. A delivery order has been created.',
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
                summary=f'Consignment Request Rejected - {self.name}',
                note='Your consignment request has been rejected.',
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
                summary=f'Consignment Request Cancelled - {self.name}',
                note='Your consignment request has been cancelled.',
                user_id=initiator.id,
            )


    def _compute_picking_count(self):
        for rec in self:
            if not rec.id or not rec.name or rec.name == 'New':
                rec.picking_count = 0
            else:
                # Count the original delivery and any return pickings
                pickings = self.env['stock.picking'].search(['|', ('id', '=', rec.delivery_id.id), ('origin', 'ilike', rec.name)])
                rec.picking_count = len(pickings)

    def action_view_delivery(self):
        """Open delivery order(s) related to this request (including returns)"""
        pickings = self.env['stock.picking'].search(['|', ('id', '=', self.delivery_id.id), ('origin', 'ilike', self.name)])
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

    def _create_auto_return(self):
        """Automatically returns the consignment stock to its original location to prevent double stock deduction/reception."""
        self.ensure_one()
        # Find the original picking(s) that are done
        pickings = self.env['stock.picking'].search([
            ('state', '=', 'done'),
            ('id', '=', self.delivery_id.id)
        ])
        
        for picking in pickings:
            # Create Return Wizard with default lines
            ReturnPicking = self.env['stock.return.picking'].with_context(
                active_id=picking.id,
                active_ids=picking.ids
            )
            default_data = ReturnPicking.default_get(
                ['product_return_moves', 'move_dest_exists', 'original_location_id', 'parent_location_id', 'location_id']
            )
            default_data['picking_id'] = picking.id
            
            return_wizard = ReturnPicking.create(default_data)
            return_wizard._compute_moves_locations()
            
            # In Odoo 17, return wizard lines default to 0 quantity. We must forcefully set them.
            for return_line in return_wizard.product_return_moves:
                if getattr(return_line.move_id, 'quantity', 0) > 0:
                    return_line.quantity = return_line.move_id.quantity
                elif getattr(return_line.move_id, 'quantity_done', 0) > 0:
                    return_line.quantity = return_line.move_id.quantity_done
            
            # Execute returns
            return_picking = return_wizard._create_return()
            
            if return_picking:
                self.message_post(body=f"Auto-generated Return Picking: {return_picking.name} to revert stock before conversion.")

    def action_convert_to_sale(self):
        self.ensure_one()
        if self.settlement_type != 'pending':
            raise UserError('This consignment has already been settled.')
        if self.consignment_role != 'giver':
            raise UserError('Only Consignment Issuers can convert to Sale.')
            
        if self.delivery_id and self.delivery_id.state != 'done':
            raise UserError('You cannot convert to Sale until the original Consignment Delivery has been validated (Done). Please process the delivery first.')

        # Automatically return the stock before generating standard SO
        self._create_auto_return()

        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)], limit=1)
        if self.delivery_id and self.delivery_id.picking_type_id.warehouse_id:
            warehouse = self.delivery_id.picking_type_id.warehouse_id

        # Create Sale Order
        sale_vals = {
            'partner_id': self.partner_id.id,
            'consignment_request_id': self.id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'warehouse_id': warehouse.id if warehouse else False,
            'order_line': [],
        }

        for line in self.line_ids:
            line_vals = (0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity_issued or line.quantity_requested,
                'product_uom_id': line.product_id.uom_id.id,
                'price_unit': line.product_id.lst_price,
                'consignment_request_line_id': line.id,
                'name': line.product_id.display_name,
            })
            sale_vals['order_line'].append(line_vals)

        sale_order = self.env['sale.order'].create(sale_vals)
        
        self.settlement_type = 'sold'
        self.state = 'proceed'
        self.message_post(body=f"Draft Sale Order created: {sale_order.name}")
        
        return self.action_view_sales()

    def action_convert_to_purchase(self):
        self.ensure_one()
        if self.settlement_type != 'pending':
            raise UserError('This consignment has already been settled.')
        if self.consignment_role != 'receiver':
            raise UserError('Only Consignment Receivers can convert to Purchase.')
            
        if self.delivery_id and self.delivery_id.state != 'done':
            raise UserError('You cannot convert to Purchase until the original Consignment Receipt has been validated (Done). Please process the receipt first.')

        # Automatically return the stock before generating standard PO
        self._create_auto_return()

        # Create Local Purchase Request
        req_vals = {
            'company_id': self.company_id.id,
            'consignment_request_id': self.id,
            'procurement_method': 'po',
            'line_ids': [],
        }

        for line in self.line_ids:
            req_line = (0, 0, {
                'product_id': line.product_id.id,
                'quantity': line.quantity_issued or line.quantity_requested,
                'unit_price': line.product_id.standard_price,
                'description': line.product_id.display_name,
            })
            req_vals['line_ids'].append(req_line)

        local_req = self.env['local.purchase.requisition'].create(req_vals)

        self.settlement_type = 'sold'
        self.state = 'proceed'
        self.message_post(body=f"Draft Local Purchase Requisition created: {local_req.name}")
        
        return self.action_view_purchases()

    def action_view_sales(self):
        self.ensure_one()
        action = self.env.ref('sale.action_orders').read()[0]
        if len(self.sale_order_ids) == 1:
            action['views'] = [(self.env.ref('sale.view_order_form').id, 'form')]
            action['res_id'] = self.sale_order_ids.id
        else:
            action['domain'] = [('id', 'in', self.sale_order_ids.ids)]
        return action

    def action_view_purchases(self):
        self.ensure_one()
        action = self.env.ref('procurement_local_purchase.action_local_purchase_requisitions').read()[0]
        if len(self.local_purchase_ids) == 1:
            action['views'] = [(self.env.ref('procurement_local_purchase.view_local_purchase_requisition_form').id, 'form')]
            action['res_id'] = self.local_purchase_ids.id
        else:
            action['domain'] = [('id', 'in', self.local_purchase_ids.ids)]
        return action

    def _create_delivery_order(self):
        """Create DRAFT delivery or receipt orders grouped by warehouse"""
        # Default locations
        fallback_customer_location = self.env.ref('stock.stock_location_customers')
        fallback_vendor_location = self.env.ref('stock.stock_location_suppliers')
        fallback_store_location = self.env.ref('stock.stock_location_stock')
        default_picking_type_out = self.env.ref('stock.picking_type_out')
        default_picking_type_in = self.env.ref('stock.picking_type_in')

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

        for warehouse, lines in lines_by_warehouse.items():
            store_location = warehouse.lot_stock_id if warehouse else fallback_store_location
            
            is_receiver = (self.consignment_role == 'receiver')
            op_type_search = 'receive' if is_receiver else 'issue'
            
            # Dynamically fetch Operation Type based on the custom field
            picking_type = self.env['stock.picking.type'].search([
                ('warehouse_id', '=', warehouse.id),
                ('cons_sample_operation_type', '=', op_type_search),
                ('company_id', '=', warehouse.company_id.id)
            ], limit=1)

            if not picking_type:
                picking_type = warehouse.in_type_id if is_receiver else warehouse.out_type_id
                if not picking_type:
                    picking_type = default_picking_type_in if is_receiver else default_picking_type_out

            cons_type_search = 'consignment_vendor' if is_receiver else 'consignment_customer'
            
            # Dynamically fetch the special Consignment Location
            special_cons_location = self.env['stock.location'].search([
                ('cons_sample_type', '=', cons_type_search),
                ('company_id', 'in', [False, warehouse.company_id.id])
            ], limit=1)
            
            # If not configured by type, fallback to name search
            if not special_cons_location:
                name_search = 'consignment receiving' if is_receiver else 'consignment issue'
                special_cons_location = self.env['stock.location'].search([
                    ('name', 'ilike', name_search),
                    ('company_id', 'in', [False, warehouse.company_id.id])
                ], limit=1)

            if is_receiver:
                # Coming FROM Vendor TO Consignment Receiving
                src_loc = picking_type.default_location_src_id or fallback_vendor_location
                dest_loc = special_cons_location or picking_type.default_location_dest_id or store_location
            else:
                # Coming FROM WH/Stock TO Consignment Issue
                src_loc = picking_type.default_location_src_id or store_location
                dest_loc = special_cons_location or picking_type.default_location_dest_id or fallback_customer_location

            move_lines = []
            for line in lines:
                move_lines.append((0, 0, {
                    'description_picking': line.product_id.name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity_issued or line.quantity_requested,
                    'product_uom': line.uom_id.id,
                    'location_id': src_loc.id,
                    'location_dest_id': dest_loc.id,
                    'state': 'draft',
                }))

            picking_vals = {
                'partner_id': self.partner_id.id,
                'owner_id': self.partner_id.id,
                'picking_type_id': picking_type.id,
                'location_id': src_loc.id,
                'location_dest_id': dest_loc.id,
                'origin': self.name,
                'state': 'draft',
                'move_ids': move_lines,
            }

            picking = self.env['stock.picking'].with_context(
                is_consignment=True,
                consignment_prefix='COI'
            ).create(picking_vals)
            picking.scheduled_date = self.issue_date
            picking.note = f"Consignment Request: {self.name}\nPartner: {self.partner_id.name}"
            picking.action_confirm()
            picking.action_assign()
            created_pickings |= picking

        if created_pickings:
            self.delivery_id = created_pickings[0].id
            self.message_post(body=f'{len(created_pickings)} Order(s) created in Ready state for Consignment.')

        return created_pickings

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
            'invoice_date': self.issue_date,
            'journal_id': journal.id,
            'invoice_origin': f'Sample Request: {self.name}',  # Source document reference
            'ref': f'Sample Request: {self.name}',  # Reference field
            'narration': f'Free Sample Issuance - Expense\nSample Request: {self.name}\nCustomer: {self.partner_id.name}',
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

class ConsignmentRequestLine(models.Model):
     _name = 'consignment.request.line'
     _description = 'Consignment Request Line'
     _check_company_auto = True

     request_id = fields.Many2one('consignment.request', required=True)
     company_id = fields.Many2one(related='request_id.company_id', store=True)
     product_id = fields.Many2one('product.product', string='Product', required=True, domain="[('type', '=', 'consu')]")
     uom_id = fields.Many2one('uom.uom', string='Unit of Measure', compute='_compute_uom_id', store=True,readonly=True)
     quantity_requested = fields.Float(string='Quantity', required=True)
     balance_rep = fields.Float(string='Stock Balance', compute='_compute_balances', readonly=True)
     balance_store = fields.Float(string='Stock Balance', compute='_compute_balances', readonly=True)
     quantity_issued = fields.Float(string='Quantity Issued')
     warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')

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