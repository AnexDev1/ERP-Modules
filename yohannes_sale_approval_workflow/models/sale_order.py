from odoo import _, fields, models, api
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # --- Core Custom Fields ---
    matured_outstanding = fields.Monetary(
        string='Matured Amount', compute='_compute_matured_outstanding',
        store=False, help='Total overdue balance for this customer.')

    @api.onchange('order_source')
    def _onchange_order_source(self):
        # Validate/Reset header warehouse
        if self.order_source:
            if self.warehouse_id and self.warehouse_id.wh_type != self.order_source:
                self.warehouse_id = False
            
            # Auto-select a warehouse of the selected type if none set
            if not self.warehouse_id:
                default_wh = self.env['stock.warehouse'].search([
                    ('company_id', '=', self.company_id.id),
                    ('wh_type', '=', self.order_source)
                ], limit=1)
                if default_wh:
                    self.warehouse_id = default_wh
        
        # Trigger recompute/reset on lines
        for line in self.order_line:
            line._compute_line_warehouse()
    sale_type = fields.Selection([
        ('cash', 'Cash'),
        ('credit', 'Credit'),
    ], string='Sale Type', required=True, default='cash')
    payment_term_id = fields.Many2one(
        'account.payment.term', string='Payment Terms',
        help='Select payment terms for credit sales')
    reject_reason = fields.Text(
        string="Reject Reason", help="Reason for rejection", tracking=True)
    approval_workflow_ids = fields.One2many(
        'sale.approval.workflow', 'sale_order_id', string='Approval History')
    manual_discount = fields.Boolean(
        string="Manual Discount", default=False, tracking=True,
        help="Enable manual unit price / discount entry on order lines")
    order_source = fields.Selection(
        selection=lambda self: self.env['stock.warehouse']._fields['wh_type'].selection,
        string="Order Source", default='wholesale', tracking=True)
    enable_order_source = fields.Boolean(
        related='company_id.enable_order_source',
        string="Enable Order Source",
        readonly=True
    )
    is_manual_sale = fields.Boolean(
        string='Manual Sale',
        default=False,
        copy=False,
        help="Check this if this order corresponds to a manual paper receipt."
    )
    manual_sale_reference = fields.Char(
        string='Manual Sale Reference',
        copy=False,
        help="Physical receipt / paper number for manual sale."
    )

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        if self.is_manual_sale:
            invoice_vals['is_manual_invoice'] = True
            if self.manual_sale_reference:
                invoice_vals['manual_receipt_reference'] = self.manual_sale_reference
        return invoice_vals
    is_reset_request = fields.Boolean(string="Is Reset Request", default=False, tracking=True)


    # --- Payment Attachment Field ---
    payment_attachment = fields.Binary(
        string='Payment Proof',
        attachment=True,
        help="Upload the payment slip/transfer proof here before confirming."
    )
    payment_attachment_name = fields.Char(string='payment File Name')
    payment_remark = fields.Char(
        string='Payment Remark',
        help="If no payment attachment is provided, please enter a remark explaining why."
    )

    # --- Proforma Reservation ---
    is_proforma = fields.Boolean(
        string='Is Proforma',
        default=False,
        help="If checked, the delivery will be created immediately upon confirmation, bypassing the invoice restriction."
    )
    proforma_reservation_deadline = fields.Datetime(
        string='Reservation Deadline',
        default=lambda self: fields.Datetime.now() + relativedelta(days=10),
        help="The specific deadline up to which the proforma reservation is valid. If no invoice is created by this time, the order and delivery will be automatically cancelled."
    )

    # --- Customer Type (from partner) ---
    partner_customer_type = fields.Selection(
        related='partner_id.customer_type',
        string='Customer Type',
        store=True,
        readonly=True
    )

    # --- Simplified 3-Step State Machine ---
    state = fields.Selection(
        selection=[
            ('draft', 'Quotation'),
            ('price_change_approval', 'Discount Approval'),
            ('operational_approval', 'Manager Approval'),
            ('finance_approval', 'Finance Approval'),
            ('approved', 'Approved'),
            ('sent', 'Quotation Sent'),
            ('sale', 'Sales Order'),
            ('done', 'Locked'),
            ('cancel', 'Cancelled'),
        ], string='Status', default='draft', tracking=True)
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Warehouse',
        domain="[('wh_type', '=', order_source)]")

    show_price_change_in_statusbar = fields.Boolean(
        compute='_compute_show_price_change_in_statusbar', store=False)
    is_current_user_approver = fields.Boolean(
        compute='_compute_is_current_user_approver')
    is_current_user_initiator = fields.Boolean(
        compute='_compute_is_current_user_initiator')
    show_delivery_button = fields.Boolean(
        compute='_compute_show_delivery_button', store=False)

    @api.depends('state', 'picking_ids.state')
    def _compute_delivery_status(self):
        if hasattr(super(SaleOrder, self), '_compute_delivery_status'):
            super(SaleOrder, self)._compute_delivery_status()
        for order in self:
            if not order.delivery_status:
                order.delivery_status = 'pending'

    @api.depends('order_line.product_id.invoice_policy', 'invoice_ids.state')
    def _compute_show_delivery_button(self):
        for order in self:
            if not hasattr(order, 'delivery_count') or order.delivery_count == 0:
                order.show_delivery_button = False
                continue
            
            # Check if there are any lines with 'ordered quantities'
            has_ordered_policy = any(line.product_id.invoice_policy == 'order' for line in order.order_line if line.product_id)
            
            if has_ordered_policy:
                # Require at least one confirmed invoice
                has_posted_invoice = any(inv.state == 'posted' and inv.move_type == 'out_invoice' for inv in order.invoice_ids)
                order.show_delivery_button = has_posted_invoice
            else:
                # If everything is delivered quantities, show it normally (since delivery count > 0)
                order.show_delivery_button = True

    # --- Customer Info (related, read-only) ---
    category_id = fields.Many2many(
        'res.partner.category', related='partner_id.category_id',
        string='Customer Tag', readonly=True)
    city = fields.Char(
        related='partner_id.city',
        string='City', store=True, readonly=True)
    tin_no = fields.Char(
        related='partner_id.vat', string='TIN No', store=True, readonly=True)

    def _validate_credit_terms(self):
        """Validate credit terms before approval"""
        if self.sale_type != 'credit':
            return True
            
        if self.company_id.bypass_credit_limit_check:
            return True

        if not self.customer_credit_id:
            raise UserError(_("No credit terms established for this customer."))

        # Credit limit validation
        future_credit = (self.partner_id.credit or 0) + self.amount_total
        if future_credit > (self.customer_credit_id.maximum_credit or 0):
            raise UserError(_(
                "Credit limit exceeded!\n\n"
                "Current Credit: %(current).2f\n"
                "Order Amount: %(amount).2f\n"
                "Credit Limit: %(limit).2f",
                current=self.partner_id.credit,
                amount=self.amount_total,
                limit=self.customer_credit_id.maximum_credit,
            ))

        # Payment term validation
        if self.payment_term_id and self.customer_credit_id.payment_term_credit:
            order_days = max(self.payment_term_id.line_ids.mapped('nb_days'), default=0)
            credit_days = max(self.customer_credit_id.payment_term_credit.line_ids.mapped('nb_days'), default=0)
            if order_days > credit_days:
                raise UserError(_(
                    "Payment term too long!\n\n"
                    "Order Term: %(order_days)s days\n"
                    "Allowed Term: %(credit_days)s days",
                    order_days=order_days,
                    credit_days=credit_days,
                ))

    def _get_approver_group(self, state):
        """Return the XML ID of the group that approves the given state."""
        self.ensure_one()
        group_map = {
            'price_change_approval': 'yohannes_sale_approval_workflow.group_price_change_approver',
            'operational_approval':  'yohannes_sale_approval_workflow.group_operational_manager',
            'finance_approval':      'yohannes_sale_approval_workflow.group_finance_approver',
        }
        return group_map.get(state)

    @api.depends('manual_discount', 'state', 'order_line.discount')
    def _compute_show_price_change_in_statusbar(self):
        for order in self:
            # Show if:
            #   - manual discount is checked, OR
            #   - any line has a discount (auto or manual), OR
            #   - the order is currently in that state
            order.show_price_change_in_statusbar = (
                    order.manual_discount
                    or order._needs_price_change_approval()
                    or order.state == 'price_change_approval'
            )

    @api.depends('create_uid', 'user_id')
    def _compute_is_current_user_initiator(self):
        for order in self:
            # Consider the creator or the salesperson as the initiator
            order.is_current_user_initiator = self.env.user in (order.create_uid, order.user_id)

    @api.depends('state')
    def _compute_is_current_user_approver(self):
        for order in self:
            group_xmlid = order._get_approver_group(order.state)
            if group_xmlid:
                order.is_current_user_approver = self.env.user.has_group(group_xmlid)
            else:
                order.is_current_user_approver = False

    @api.depends('order_line.discount_unit_price')
    def _compute_price_change_info(self):
        for order in self:
            lines = order.order_line.filtered(lambda l: l.discount > 0)
            if not lines:
                order.price_change_lines_text = False
                continue
            texts = []
            for line in lines:
                orig = line.price_unit
                new_p = line.discount_unit_price
                texts.append(f"{line.product_id.name}: {orig:,.2f} → {new_p:,.2f}")
            order.price_change_lines_text = "\n".join(texts)

    def _needs_price_change_approval(self):
        self.ensure_one()
        return any(line.discount > 0 for line in self.order_line)



    # Hide price_change_approval state if not needed
    @api.depends('state', 'order_line')
    def _compute_display_state(self):
        # Optional: if you want dynamic visibility in statusbar
        pass  # see view attrs below

    def action_submit_for_approval(self):
        """
        Unified submit button:
        - If manual discount is active + needs price approval → go to price_change_approval
        - If no manual discount (only auto rules or no discount) → go directly to operation approval
        """
        self.ensure_one()

        if self.state != 'draft':
            raise UserError(_("Only draft quotations can be submitted for approval."))

        # Run credit validation
        self._validate_credit_terms()

        # Warehouse validation removed as wh_type is no longer used

        # Validate stock availability depending on order source:
        # - Import (or no order source): block on SUBMIT if any line exceeds available stock
        # - Wholesale: allow submit freely, block only on CONFIRM
        is_import_or_no_source = (not self.enable_order_source) or (self.order_source == 'import')

        if is_import_or_no_source:
            for line in self.order_line:
                if line.product_id and line.product_id.type == 'product':
                    line._compute_available_in_warehouse()
                    if line.product_uom_qty > line.wh_available_qty:
                        raise UserError(_(
                            "Insufficient stock for product '%(product)s' in warehouse '%(warehouse)s'!\n\n"
                            "Required: %(required).2f %(uom)s\n"
                            "Available: %(available).2f %(uom)s\n\n"
                            "Import orders can only include products with sufficient on-hand stock.",
                            product=line.product_id.name,
                            warehouse=self.warehouse_id.name if self.warehouse_id else 'N/A',
                            required=line.product_uom_qty,
                            available=line.wh_available_qty,
                            uom=line.product_uom.name,
                        ))

        # Determine next state based on whether ANY discount is in use (manual or auto)
        has_any_discount = self._needs_price_change_approval()

        if self.manual_discount or has_any_discount:
            next_state = 'price_change_approval'
            message_body = _("Price change approval requested (discounts detected).")
            activity_summary = f"Approve Price Change - {self.name}"
            activity_note = "Discounts (manual or auto) detected."
        else:
            # No discount → skip price change → go to operational approval
            next_state = 'operational_approval'
            message_body = _("Quotation submitted for Operational Manager approval.")
            activity_summary = f"Review Quotation - {self.name}"
            activity_note = "Standard approval flow."

        # Move to the determined state
        self.write({'state': next_state})

        # Record in history
        self.env['sale.approval.workflow'].create({
            'sale_order_id': self.id,
            'approver_id': self.env.user.id,
            'action': 'submitted',
            'state': 'draft',
            'comments': message_body,
        })

        # Log in chatter
        self.message_post(body=message_body)

        # Notify the appropriate group
        group_xmlid = self._get_approver_group(next_state)

        try:
            group = self.env.ref(group_xmlid)
            users = group.users if hasattr(group, 'users') else (group.user_ids if hasattr(group, 'user_ids') else [])
            for user in users:
                self.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=activity_summary,
                    note=activity_note,
                    user_id=user.id,
                    # Optional: date_deadline=fields.Date.today() + relativedelta(days=2)
                )
        except Exception as e:
            _logger.warning(f"Could not schedule activities for group {group_xmlid}: {str(e)}")
            self.message_post(body=_("Warning: Could not notify approvers automatically. Please inform them manually."))

        return True

    #@api.depends('order_line.price_unit', 'order_line.product_uom_qty')
    #def _compute_amount_undiscounted(self):
     #   for order in self:
      #      order.amount_undiscounted = sum(line.price_unit * line.product_uom_qty for line in order.order_line)



    def action_approve_price_change(self):
        """Price Change Approver approves → move to Operational Approval"""
        self.ensure_one()

        if self.state != 'price_change_approval':
            raise UserError(_("Order is not in Price Change Approval state."))

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

        group_xmlid = self._get_approver_group('price_change_approval')
        if not self.env.user.has_group(group_xmlid):
            raise UserError(_("You are not authorized to approve the discount on this order."))

        self.env['sale.approval.workflow'].create({
            'sale_order_id': self.id,
            'approver_id': self.env.user.id,
            'state': 'approved',
            'comments': self.env.context.get('comments', 'Operational approved'),
        })

        self.write({'state': 'operational_approval'})
        self.message_post(
            body=f"Price change approved by {self.env.user.name}. Now awaiting Operational Manager approval.")
        
        # Notify the Operational Managers
        next_group_xmlid = self._get_approver_group('operational_approval')
        try:
            group = self.env.ref(next_group_xmlid)
            users = group.users if hasattr(group, 'users') else (group.user_ids if hasattr(group, 'user_ids') else [])
            for user in users:
                self.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=f"Operational Approval - {self.name}",
                    note="Review and approve the operational aspects of this order.",
                    user_id=user.id,
                )
        except Exception as e:
            _logger.warning(f"Could not schedule activities for group {next_group_xmlid}: {str(e)}")

    def action_approve_operational(self):
        self.ensure_one()
        if self.state != 'operational_approval':
            raise UserError("Not in operational approval pending state.")

        # If this is a request to reset to Draft Quotation
        if self.is_reset_request:
            group_xmlid = self._get_approver_group('operational_approval')
            if not self.env.user.has_group(group_xmlid):
                raise UserError(_("You are not authorized to validate this reset request."))

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

            self.write({
                'is_reset_request': False,
                'state': 'draft'
            })
            self.message_post(body=_("Reset to Quotation request approved by Manager. Order is now a Draft Quotation."))
            
            # Notify the initiator
            user_to_notify = self.user_id or self.create_uid
            if user_to_notify:
                self.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=f"Reset Approved - {self.name}",
                    note="Your request to reset the order to a quotation has been approved.",
                    user_id=user_to_notify.id,
                )
            return True
            
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
        group_xmlid = self._get_approver_group('operational_approval')
        if not self.env.user.has_group(group_xmlid):
            raise UserError(_("You are not authorized to validate this order."))

        # HARD STOCK VALIDATION: Check warehouse balance for all lines
        for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id and l.product_id.type in ('product', 'storable')):
            line._compute_available_in_warehouse() # Fresh compute
            if line.product_uom_qty > line.wh_available_qty:
                raise ValidationError(_(
                    "Insufficient stock for product '%(product)s' in warehouse '%(warehouse)s'.\n\n"
                    "Requested: %(requested).2f\n"
                    "Available in WH: %(available).2f\n\n"
                    "Please adjust the quantity or select a different warehouse/location.",
                    product=line.product_id.display_name,
                    warehouse=line.warehouse_id.name,
                    requested=line.product_uom_qty,
                    available=line.wh_available_qty,
                ))

        self.env['sale.approval.workflow'].create({
            'sale_order_id': self.id,
            'approver_id': self.env.user.id,
            'state': 'approved',
            'comments': self.env.context.get('comments', 'Operational approved'),
        })

        if self.sale_type == 'credit':
            # Credit sales require Finance Approval
            self.write({'state': 'finance_approval'})
            message_body = f"Order validated by {self.env.user.name}. Awaiting Finance Credit Approval."
            activity_summary = f"Finance Credit Approval - {self.name}"
            next_state = 'finance_approval'
        else:
            # Cash sales or others bypass Finance
            self.write({'state': 'approved'})
            message_body = f"Order approved by {self.env.user.name}. Ready to confirm as Sales Order."
            
            # Notify the initiator
            user_to_notify = self.user_id or self.create_uid
            if user_to_notify:
                self.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=f"Order Fully Approved - {self.name}",
                    note="Your sales order has been fully approved and is ready for confirmation.",
                    user_id=user_to_notify.id,
                )
            return self.message_post(body=message_body)

        # Notify the Finance group if state is finance_approval
        self.message_post(body=message_body)
        group_xmlid = self._get_approver_group(next_state)
        try:
            group = self.env.ref(group_xmlid)
            users = group.users if hasattr(group, 'users') else (group.user_ids if hasattr(group, 'user_ids') else [])
            for user in users:
                self.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=activity_summary,
                    note="Review customer credit limit and payment history.",
                    user_id=user.id,
                )
        except Exception as e:
            _logger.warning(f"Could not schedule activities for group {group_xmlid}: {str(e)}")

    def action_approve_finance(self):
        """Finance Approver approves credit → move to sent state"""
        self.ensure_one()
        if self.state != 'finance_approval':
            raise UserError(_("Order is not in Finance Approval state."))

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

        group_xmlid = self._get_approver_group('finance_approval')
        if not self.env.user.has_group(group_xmlid):
            raise UserError(_("Only authorized Finance Credit Approvers can perform this action."))

        self.env['sale.approval.workflow'].create({
            'sale_order_id': self.id,
            'approver_id': self.env.user.id,
            'state': 'approved',
            'comments': self.env.context.get('comments', 'Finance credit approved'),
        })

        self.write({'state': 'approved'})
        self.message_post(body=f"Credit approved by {self.env.user.name} (Finance). Ready for confirmation.")
        
        # Notify the initiator
        user_to_notify = self.user_id or self.create_uid
        if user_to_notify:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=f"Order Fully Approved - {self.name}",
                note="Your sales order has been fully approved and is ready for confirmation.",
                user_id=user_to_notify.id,
            )

    @api.depends('partner_id.credit')
    def _compute_matured_outstanding(self):
        for order in self:
            order.matured_outstanding = order.partner_id.credit or 0.0

    def action_reject(self):
        if any(request.state == 'done' for request in self):
            raise UserError("Completed requests cannot be Rejected")
            
        # Clear pending activities for all users
        activities = self.env['mail.activity'].search([
            ('res_model', '=', self._name),
            ('res_id', 'in', self.ids),
            ('activity_type_id', '=', self.env.ref('mail.mail_activity_data_todo').id)
        ])
        activities.action_done()
        
        self.write({
            'state': 'cancel',
            'is_reset_request': False
        })
        self.message_post(body=_("Request Rejected"))
        
        for order in self:
            user_to_notify = order.user_id or order.create_uid
            if user_to_notify:
                order.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=f"Order Rejected - {order.name}",
                    note="Your sales order has been rejected and cancelled.",
                    user_id=user_to_notify.id,
                )

    def action_cancel(self):
        # Block cancellation if any non-cancelled invoice exists
        if self.invoice_ids.filtered(lambda inv: inv.state != 'cancel'):
            raise UserError(_("You cannot cancel an order that has already been invoiced."))
            
        # Clear pending activities for all users
        activities = self.env['mail.activity'].search([
            ('res_model', '=', self._name),
            ('res_id', 'in', self.ids),
            ('activity_type_id', '=', self.env.ref('mail.mail_activity_data_todo').id)
        ])
        activities.action_done()
        self.write({
            'state': 'cancel',
            'is_reset_request': False
        })

    def action_draft(self):
        # Block reset if any non-cancelled invoice exists
        if self.invoice_ids.filtered(lambda inv: inv.state != 'cancel'):
            raise UserError(_("You cannot reset an order to quotation if it has already been invoiced."))

        # Clear pending activities for all users
        activities = self.env['mail.activity'].search([
            ('res_model', '=', self._name),
            ('res_id', 'in', self.ids),
            ('activity_type_id', '=', self.env.ref('mail.mail_activity_data_todo').id)
        ])
        activities.action_done()
        
        # Move to operational approval state for reset request
        self.write({
            'is_reset_request': True,
            'state': 'operational_approval'
        })
        self.message_post(body=_("Requested to reset order to Quotation. Awaiting Manager Approval."))
        
        # Schedule activity for Operational Managers
        for order in self:
            group_xmlid = order._get_approver_group('operational_approval')
            try:
                group = order.env.ref(group_xmlid)
                users = group.users if hasattr(group, 'users') else (group.user_ids if hasattr(group, 'user_ids') else [])
                for user in users:
                    order.activity_schedule(
                        'mail.mail_activity_data_todo',
                        summary=f"Approve Reset to Quotation - {order.name}",
                        note="The user requested to reset this order back to a Draft Quotation. Please review.",
                        user_id=user.id,
                    )
            except Exception as e:
                _logger.warning(f"Could not schedule activities for group {group_xmlid}: {str(e)}")
                
        return True

    def _create_invoices(self, grouped=False, final=False, date=None):
        moves = super(SaleOrder, self)._create_invoices(grouped=grouped, final=final, date=date)
        for move in moves:
            orders = move.mapped('invoice_line_ids.sale_line_ids.order_id')
            if not orders:
                continue
                
            so_attachments = self.env['ir.attachment'].search([
                ('res_model', '=', 'sale.order'),
                ('res_id', 'in', orders.ids),
                ('res_field', '=', 'payment_attachment')
            ])
            
            if so_attachments:
                # Find the auto-generated origin message on the move
                origin_msg = self.env['mail.message'].search([
                    ('res_id', '=', move.id),
                    ('model', '=', 'account.move'),
                    ('body', 'ilike', 'This journal entry has been created from:')
                ], limit=1)
                
                ref_str = move.payment_reference or 'N/A'
                
                if origin_msg:
                    # Append to the original HTML body to preserve the clickable link
                    new_body = origin_msg.body.replace('</p>', f' with payment reference {ref_str}</p>')
                    origin_msg.write({
                        'body': new_body,
                        'attachment_ids': [(4, so_attachments[0].id)]
                    })
                else:
                    so_names = orders.mapped('name')
                    so_str = ', '.join(so_names) if so_names else 'Sales Order'
                    custom_body = f"<p>This journal entry has been created from: {so_str} with payment reference {ref_str}</p>"
                    move.message_post(
                        body=custom_body,
                        attachment_ids=[so_attachments[0].id]
                    )
        return moves

    def action_confirm(self):
        """
        Custom confirmation that:
        1. Ensures the order is in a valid state (Sent/Approved).
        2. Requires payment attachment.
        3. For Wholesale orders: blocks if stock is insufficient.
        4. Calls standard Odoo confirmation (Standard Routing).
        5. Automatically notifies the Warehouse Team to prepare for delivery.
        """
        # Handle empty recordset (e.g., when called from payment processing)
        if not self:
            _logger.warning("action_confirm called on empty recordset - skipping")
            return True

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

        # Handle multiple records
        if len(self) > 1:
            _logger.info("action_confirm called on multiple orders (%s) - processing individually", self.ids)
            for order in self:
                order.action_confirm()
            return True

        # Now we have exactly one record
        self.ensure_one()

        allowed_states = ['approved', 'operational_approval', 'finance_approval']

        if self.state not in allowed_states:
            raise UserError(
                _("Cannot confirm order. Current state: %s\n"
                  "Order must be in 'Approved', 'Manager Approval', or 'Finance Approval' state.")
                % dict(self._fields['state'].selection).get(self.state, self.state)
            )

        # Payment Attachment/Remark validation
        # Require payment proof OR a remark to confirm for ALL non-credit orders unconditionally
        if self.sale_type != 'credit' and not self.payment_attachment and not self.payment_remark:
            raise ValidationError(_("A Payment Proof attachment or a Payment Remark is required before confirmation for non-credit sales."))

        # For Wholesale orders: hard stock check at confirmation
        is_wholesale = self.order_source == 'wholesale'
        if is_wholesale:
            for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id and l.product_id.type in ('product', 'consu')):
                line._compute_available_in_warehouse()
                if line.product_uom_qty > line.wh_available_qty:
                    raise UserError(_(
                        "Insufficient stock for product '%(product)s' in warehouse '%(warehouse)s'!\n\n"
                        "Required: %(required).2f %(uom)s\n"
                        "Available: %(available).2f %(uom)s\n\n"
                        "Please wait for stock to be replenished.",
                        product=line.product_id.name,
                        warehouse=line.warehouse_id.name if line.warehouse_id else 'N/A',
                        required=line.product_uom_qty,
                        available=line.wh_available_qty,
                        uom=line.product_id.uom_id.name,
                    ))

        # Safety check: warehouse must be set
        if not self.warehouse_id:
            raise UserError(_("No warehouse selected on the order. Cannot create delivery."))

        try:
            # Step 1: Force state to 'sent' right before core confirmation so Odoo doesn't reject it
            if self.state in ('approved', 'operational_approval', 'finance_approval'):
                self.write({'state': 'sent'})
                # Flush might not be necessary here as super().action_confirm() will trigger a flush
                # self.flush_recordset(['state'])

            # Step 2: Sync line warehouses to the header warehouse
            # This prevents "No rule to replenish in Inter-warehouse transit" errors
            # when a line's warehouse (e.g. from product default) differs from the order header.
            mismatched_lines = self.order_line.filtered(
                lambda l: not l.display_type and l.warehouse_id != self.warehouse_id
            )
            if mismatched_lines:
                _logger.info("Syncing %d line warehouse(s) to order warehouse %s for %s",
                             len(mismatched_lines), self.warehouse_id.name, self.name)
                mismatched_lines.write({'warehouse_id': self.warehouse_id.id})

            # Save the original date_order to prevent Odoo from overwriting it with today's date
            original_dates = {order.id: order.date_order for order in self}

            # Step 3: Call standard confirmation (Odoo routing takes over)
            res = super(SaleOrder, self).action_confirm()
            
            # Restore original date_order
            for order in self:
                if order.id in original_dates and original_dates[order.id]:
                    order.date_order = original_dates[order.id]

            _logger.info(">>> [DEBUG] confirmed Order %s using standard routing", self.name)

            for order in self:
                # If there are lines that are 'delivered' quantities, they just created a delivery.
                # So we should notify the warehouse team for those.
                has_delivered_policy = any(line.product_id.invoice_policy != 'order' for line in order.order_line if line.product_id)
                if has_delivered_policy:
                    warehouse_group_xmlid = 'yohannes_sale_approval_workflow.group_warehouse_user'
                    try:
                        group = order.env.ref(warehouse_group_xmlid)
                        users = group.users if hasattr(group, 'users') else (group.user_ids if hasattr(group, 'user_ids') else [])
                        for user in users:
                            # Filter notifications based on warehouse access
                            if hasattr(user, 'allowed_warehouse_ids'):
                                if user.allowed_warehouse_ids and order.warehouse_id not in user.allowed_warehouse_ids:
                                    continue
                                if not user.allowed_warehouse_ids and order.warehouse_id.company_id not in user.company_ids:
                                    continue
                                    
                            order.activity_schedule(
                                'mail.mail_activity_data_todo',
                                summary=f"Delivery Preparation - {order.name}",
                                note="Sales order confirmed. Please prepare items for delivery.",
                                user_id=user.id,
                            )
                        order.message_post(body=_("Warehouse team notified for delivery preparation."))
                    except Exception as e:
                        _logger.warning(f"Could not notify warehouse group: {str(e)}")

                # Notify Cashiers for Invoicing
                cashier_group_xmlid = 'yohannes_sale_approval_workflow.group_sales_cashier'
                try:
                    cashier_group = order.env.ref(cashier_group_xmlid)
                    cashier_users = cashier_group.users if hasattr(cashier_group, 'users') else (cashier_group.user_ids if hasattr(cashier_group, 'user_ids') else [])
                    for user in cashier_users:
                        order.activity_schedule(
                            'mail.mail_activity_data_todo',
                            summary=f"Invoice Preparation - {order.name}",
                            note="Sales order confirmed. Please create and confirm the invoice.",
                            user_id=user.id,
                        )
                except Exception as e:
                    _logger.warning(f"Could not notify cashier group: {str(e)}")

            return res

        except Exception as e:
            _logger.error("Confirmation failed for Sale Order %s: %s", self.name, str(e), exc_info=True)

            # You might want to catch specific exceptions here if needed
            raise UserError(_(
                "Confirmation failed due to an error.\n\n"
                "Error details: %s\n\n"
                "Please verify:\n"
                "• Stock availability for all products\n"
                "• Correct warehouse selected\n"
                "• Product types are 'Storable Product'",
                str(e)  # Use str(e) directly instead of error_msg variable
            ))

    def action_preview_proforma(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': f'/report/html/sale.report_saleorder_pro_forma/{self.id}',
        }

    has_line_discounts = fields.Boolean(compute='_compute_has_line_discounts')

    @api.depends('order_line.discount', 'order_line.manual_discount_active', 'order_line.discount_rule_display')
    def _compute_has_line_discounts(self):
        for order in self:
            order.has_line_discounts = any(line.discount > 0 or line.manual_discount_active or line.discount_rule_display for line in order.order_line)

    def get_available_products_domain(self):
        """Returns a domain for filtering products based on order source"""
        self.ensure_one()
        domain = []
        return domain
    @api.onchange('partner_id')
    def _onchange_partner_id_recalculate_prices(self):
        if not self.partner_id:
            return
        
        customer_type = self.partner_id.customer_type
        for line in self.order_line:
            if not line.product_id:
                continue
            product_tmpl = line.product_id.product_tmpl_id
            
            # Use appropriate price
            if customer_type in ('retail',):
                if product_tmpl.retail_price:
                    line.price_unit = product_tmpl.retail_price
            elif customer_type in ('wholesale', 'both'):
                if product_tmpl.wholesale_price:
                    line.price_unit = product_tmpl.wholesale_price


    def write(self, vals):
        res = super(SaleOrder, self).write(vals)
        if 'payment_attachment' in vals and vals.get('payment_attachment'):
            for order in self:
                attachment = self.env['ir.attachment'].search([
                    ('res_model', '=', 'sale.order'),
                    ('res_id', '=', order.id),
                    ('res_field', '=', 'payment_attachment')
                ], limit=1)
                if attachment:
                    order.message_post(
                        body=_("Payment Attachment has been uploaded."),
                        attachment_ids=[attachment.id]
                    )
                else:
                    order.message_post(body=_("Payment Attachment has been uploaded."))
        return res

    @api.model
    def cron_cancel_un_invoiced_orders(self):
        """
        Automated Task: Cancels confirmed orders (state='sale') if no invoice 
        is created by the next morning, or if the proforma deadline is exceeded.
        """
        from datetime import datetime, time
        
        now = datetime.now()
        
        # We look for orders in 'sale' state
        orders = self.search([('state', '=', 'sale')])
        
        for order in orders:
            # Check if there's any active invoice
            has_active_invoice = any(inv.state != 'cancel' for inv in order.invoice_ids)
            if has_active_invoice:
                continue
                
            if order.is_proforma:
                # Scenario 2: Proforma reservation
                if order.proforma_reservation_deadline and now > order.proforma_reservation_deadline:
                    order.action_cancel()
                    order.message_post(body=_("Order automatically cancelled by system: Proforma reservation deadline exceeded and no invoice was created."))
            else:
                order.action_cancel()
                order.message_post(body=_("Order automatically cancelled by system: No invoice was created."))

    def _get_next_manual_so_name(self, company):
        """Generate next manual sales order sequence name (1, 2... up to limit)."""
        manual_count = self.env['sale.order'].sudo().search_count([
            ('company_id', '=', company.id),
            ('is_manual_sale', '=', True)
        ])
        next_num = manual_count + 1

        if next_num > company.so_manual_sequence_limit:
            raise UserError(_(
                "Manual Sales Order sequence limit of %s has been reached for company '%s'. "
                "No more manual sales orders can be created under this limit."
            ) % (company.so_manual_sequence_limit, company.name))

        seq_ids = self.env['ir.sequence'].sudo().search([
            ('code', '=', 'sale.order'),
            ('company_id', 'in', [company.id, False])
        ], order='company_id')

        prefix = "S"
        suffix = ""
        padding = 5
        if seq_ids:
            seq = seq_ids[0]
            try:
                prefix, suffix = seq._get_prefix_suffix()
            except Exception:
                prefix = seq.prefix or "S"
                suffix = seq.suffix or ""
            padding = seq.padding or 5

        return f"{prefix}{str(next_num).zfill(padding)}{suffix}"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            is_manual = vals.get('is_manual_sale') or self.env.context.get('default_is_manual_sale', False)
            company_id = vals.get('company_id') or self.env.company.id
            company = self.env['res.company'].browse(company_id)

            if company and company.use_so_manual_sequence_limit and company.so_manual_sequence_limit > 0:
                limit = company.so_manual_sequence_limit
                target_next_for_digital = limit + 1

                if is_manual:
                    # Manual Sales Order: assign next sequence number within manual limit
                    vals['name'] = self._get_next_manual_so_name(company)
                else:
                    # Non-manual (Digital) Sales Order: start standard sequence at limit + 1
                    seq_ids = self.env['ir.sequence'].sudo().search([
                        ('code', '=', 'sale.order'),
                        ('company_id', 'in', [company_id, False])
                    ], order='company_id')

                    if seq_ids:
                        seq = seq_ids[0]
                        seq.invalidate_recordset()
                        if seq.number_next_actual < target_next_for_digital:
                            seq.write({'number_next': target_next_for_digital})
                            seq.invalidate_recordset()

        return super().create(vals_list)




class SaleOrderLine(models.Model):

    _inherit = 'sale.order.line'

    def _validate_analytic_distribution(self):
        # Bypass the 100% analytic distribution requirement as per user request
        return True

    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        """
        Prevent delivery creation if the invoicing policy is 'order', 
        unless it's being triggered from an already posted invoice.
        """
        if self.env.context.get('skip_ordered_policy_check'):
            return super(SaleOrderLine, self)._action_launch_stock_rule(previous_product_uom_qty=previous_product_uom_qty)

        lines_to_run = self.env['sale.order.line']
        for line in self:
            if line.product_id.invoice_policy == 'order' and not line.order_id.is_proforma:
                continue
            lines_to_run |= line

        if not lines_to_run:
            return True

        return super(SaleOrderLine, lines_to_run)._action_launch_stock_rule(previous_product_uom_qty=previous_product_uom_qty)


    discount_rule_display = fields.Char(string='Discount Rule', store=True, readonly=True)
    manual_discount_active = fields.Boolean(string="Manual Disc. Active", related='order_id.manual_discount',store=True, readonly=True)
    show_discount_unit_price = fields.Boolean(compute='_compute_show_discount_unit_price')
    wh_available_qty = fields.Float(string='WH Balance', compute='_compute_available_in_warehouse', readonly=True, help="Total available quantity in the entire selected warehouse")
    warehouse_id = fields.Many2one('stock.warehouse', string="Warehouse", store=True, readonly=False, 
                               compute='_compute_line_warehouse', inverse='_inverse_line_warehouse')
    discount_unit_price = fields.Float(string='DisUnit Price', digits='Product Price',compute='_compute_discount_unit_price',
                                       inverse='_inverse_discount_unit_price', store=True, readonly=False)
    location_id = fields.Many2one(
        'stock.location', string="Location",
        domain="[('usage', '=', 'internal'), '|', ('warehouse_id', '=', warehouse_id), ('warehouse_id', '=', False)]",
        store=True)
    on_hand_qty = fields.Float(
        string='On Hand', compute='_compute_available_in_warehouse',
        readonly=True, help="Total quantity on hand in the selected location")
    reserved_qty = fields.Float(
        string='Reserved', compute='_compute_available_in_warehouse',
        readonly=True, help="Quantity reserved in the selected location")
    available_in_warehouse = fields.Float(
        string='Stock Balance', compute='_compute_available_in_warehouse',
        readonly=True, help="Available (free) quantity in the selected location")
    
    
    
    
    


    # Removed _get_dispatch_location since we use standard routing

    @api.depends('discount', 'manual_discount_active', 'discount_rule_display')
    def _compute_show_discount_unit_price(self):
        for line in self:
            # Show if a discount exists (manually or via rule)
            line.show_discount_unit_price = (line.discount > 0) or line.manual_discount_active or bool(line.discount_rule_display)

    @api.depends('order_id.warehouse_id', 'product_id', 'product_id.default_warehouse_id', 'order_id.order_source')
    def _compute_line_warehouse(self):
        for line in self:
            source = line.order_id.order_source
            # 1. Try product's default warehouse if it matches the source
            if line.product_id and line.product_id.default_warehouse_id and (not source or line.product_id.default_warehouse_id.wh_type == source):
                line.warehouse_id = line.product_id.default_warehouse_id
            # 2. Try order's warehouse if it matches the source
            elif line.order_id.warehouse_id and (not source or line.order_id.warehouse_id.wh_type == source):
                line.warehouse_id = line.order_id.warehouse_id
            # 3. If current warehouse is invalid for the source, clear it
            elif source and line.warehouse_id and line.warehouse_id.wh_type != source:
                line.warehouse_id = False

    def _inverse_line_warehouse(self):
        for line in self:
            pass # allow manual selection

    @api.depends('product_id', 'warehouse_id', 'location_id', 'lot_id')
    def _compute_available_in_warehouse(self):
        """Compute available stock based on selected location and entire warehouse."""
        for line in self:
            line.on_hand_qty = 0.0
            line.reserved_qty = 0.0
            line.available_in_warehouse = 0.0
            line.wh_available_qty = 0.0

            if not line.product_id or line.display_type:
                continue

            # Context
            company_id = line.company_id.id or self.env.company.id
            product = line.product_id

            if line.warehouse_id:
                # [Keep the location stock part in case they use it]
                loc = line.location_id or line.warehouse_id.lot_stock_id
                if loc:
                    quants = self.env['stock.quant'].search([
                        ('product_id', '=', product.id),
                        ('location_id', 'child_of', loc.id),
                        ('company_id', '=', company_id)
                    ])
                    line.on_hand_qty = sum(quants.mapped('quantity'))
                    line.reserved_qty = sum(quants.mapped('reserved_quantity'))
                    line.available_in_warehouse = line.on_hand_qty - line.reserved_qty

                # --- 2. Warehouse-wide Stock (for reference) ---
                wh_domain = [
                    ('product_id', '=', product.id),
                    ('location_id', 'child_of', line.warehouse_id.view_location_id.id),
                    ('company_id', '=', company_id)
                ]
                
                # Exclude suspense locations (where allow_negative_stock is True)
                if 'allow_negative_stock' in self.env['stock.location']._fields:
                    wh_domain.append(('location_id.allow_negative_stock', '!=', True))
                    
                if line.lot_id:
                    wh_domain.append(('lot_id', '=', line.lot_id.id))
                    
                wh_quants = self.env['stock.quant'].search(wh_domain)
                wh_on_hand = sum(wh_quants.mapped('quantity'))
                wh_reserved = sum(wh_quants.mapped('reserved_quantity'))
                line.wh_available_qty = wh_on_hand - wh_reserved
            else:
                line.wh_available_qty = 0.0

            _logger.debug("Stock calc - Product: %s | Loc: %s | WH: %s | Avail: %.2f | WH Avail: %.2f",
                         product.display_name, loc.display_name if loc else 'None', line.warehouse_id.name, 
                         line.available_in_warehouse, line.wh_available_qty)

    @api.onchange('location_id')
    def _onchange_location_id(self):
        self._compute_available_in_warehouse()

    @api.onchange('product_uom_qty')
    def _onchange_product_uom_qty(self):
        self._compute_available_in_warehouse()
        if self.product_id and self.product_id.type in ('product', 'consu'):
            if self.product_uom_qty > self.wh_available_qty:
                return {
                    'warning': {
                        'title': _("Stock Warning"),
                        'message': _("Insufficient stock for product '%(product)s' in warehouse '%(warehouse)s'.\n\n"
                                     "Requested: %(requested).2f\n"
                                     "Available in WH: %(available).2f\n\n"
                                     "Note: You will not be able to save this order.",
                                     product=self.product_id.display_name,
                                     warehouse=self.warehouse_id.name or 'N/A',
                                     requested=self.product_uom_qty,
                                     available=self.wh_available_qty)
                    }
                }

    @api.constrains('product_uom_qty', 'product_id', 'order_id')
    def _check_stock_availability(self):
        """Only block on save for Import/No-Source orders. Wholesale can exceed stock until confirm."""
        for line in self:
            order = line.order_id
            is_import_or_no_source = (not order.enable_order_source) or (order.order_source == 'import')
            if not is_import_or_no_source:
                continue  # Wholesale: allow, will be checked at confirm
            if line.product_id and line.product_id.type in ('product', 'consu') and order.state in ('draft', 'sent', 'sale'):
                line._compute_available_in_warehouse()
                if line.product_uom_qty > line.wh_available_qty:
                    raise ValidationError(_("Insufficient stock for product '%(product)s'.\n\n"
                                          "Requested: %(requested).2f\n"
                                          "Available in WH: %(available).2f\n\n"
                                          "Import orders cannot exceed available on-hand stock.",
                                          product=line.product_id.display_name,
                                          requested=line.product_uom_qty,
                                          available=line.wh_available_qty))

    @api.onchange('product_id')
    def _onchange_product_id(self):
        result = super(SaleOrderLine, self)._onchange_product_id() or {}

        # Recompute current stock balance (important after product change)
        self._compute_available_in_warehouse()

        # Auto-apply wholesale or retail price based on customer type
        if self.product_id and self.order_id.partner_id:
            customer_type = self.order_id.partner_id.customer_type
            product_tmpl = self.product_id.product_tmpl_id
            if customer_type in ('retail',):
                if product_tmpl.retail_price:
                    self.price_unit = product_tmpl.retail_price
            elif customer_type in ('wholesale', 'both'):
                if product_tmpl.wholesale_price:
                    self.price_unit = product_tmpl.wholesale_price

        return result

    @api.depends('price_unit', 'discount', 'manual_discount_active')
    def _compute_discount_unit_price(self):
        for line in self:
            if line.manual_discount_active:
                # Manual mode: editable field, compute from price_unit & discount only if discount changed
                if line.discount:
                    line.discount_unit_price = line.price_unit * (1 - line.discount / 100.0)
                # else keep user-entered value
            else:
                # Auto mode
                line.discount_unit_price = line.price_unit * (1 - line.discount / 100.0)

    def _inverse_discount_unit_price(self):
        for line in self:
            if line.manual_discount_active and line.price_unit:
                line.discount = (1 - line.discount_unit_price / line.price_unit) * 100.0

            # else ignore (auto mode)



    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_ids', 'manual_discount_active', 'discount_unit_price')
    def _compute_amount(self):
        """
        Override Odoo's standard compute amount to use discount_unit_price when manual discount is active.
        """
        for line in self:
            if line.manual_discount_active:
                price = line.discount_unit_price
                taxes = line.tax_ids.compute_all(price, line.order_id.currency_id, line.product_uom_qty, product=line.product_id, partner=line.order_id.partner_shipping_id)
                line.update({
                    'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                    'price_total': taxes['total_included'],
                    'price_subtotal': taxes['total_excluded'],
                })
            else:
                super(SaleOrderLine, line)._compute_amount()

    @api.onchange('discount_unit_price', 'price_unit', 'product_uom_qty', 'tax_ids', 'manual_discount_active')
    def _onchange_manual_discount_amounts(self):
        """
        Force the web client to immediately show the exact totals when the discount unit price is edited.
        """
        for line in self:
            if line.manual_discount_active:
                price = line.discount_unit_price
                taxes = line.tax_ids.compute_all(price, line.order_id.currency_id, line.product_uom_qty, product=line.product_id, partner=line.order_id.partner_shipping_id)
                line.price_tax = sum(t.get('amount', 0.0) for t in taxes.get('taxes', []))
                line.price_total = taxes['total_included']
                line.price_subtotal = taxes['total_excluded']

    def _prepare_base_line_for_taxes_computation(self, **kwargs):
        """
        Override to ensure that the order-level totals computation uses the manual discount unit price
        instead of recalculating with the standard price_unit and rounded discount percentage.
        """
        self.ensure_one()
        if self.manual_discount_active:
            kwargs.update({
                'price_unit': self.discount_unit_price,
                'discount': 0.0,
            })
        return super(SaleOrderLine, self)._prepare_base_line_for_taxes_computation(**kwargs)

    def _prepare_invoice_line(self, **optional_values):
        """
        Override to ensure invoice lines exactly match the manual discount unit price.
        """
        res = super(SaleOrderLine, self)._prepare_invoice_line(**optional_values)
        if self.manual_discount_active:
            res['price_unit'] = self.discount_unit_price
            res['discount'] = 0.0
        return res










