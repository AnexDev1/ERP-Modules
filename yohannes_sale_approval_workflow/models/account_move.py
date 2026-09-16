from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    approval_state = fields.Selection([
        ('draft', 'Draft'),
        ('manager_approval', 'Manager Approval'),
        ('gm_approval', 'GM Approval'),
        ('ceo_approval', 'CEO Approval'),
        ('approved', 'Approved'),
    ], string='Return Approval Status', default='draft', copy=False, tracking=True)

    def _get_last_sequence(self, relaxed=False, with_prefix=None):
        self.ensure_one()
        company = self.company_id or self.env.company
        journal = self.journal_id

        limit = 0
        if company and company.use_so_manual_sequence_limit and company.so_manual_sequence_limit > 0:
            limit = company.so_manual_sequence_limit
        elif journal and journal.use_manual_sequence_limit and journal.manual_sequence_limit > 0:
            limit = journal.manual_sequence_limit

        is_manual = getattr(self, 'is_manual_invoice', False) or self.env.context.get('default_is_manual_invoice', False)

        if limit > 0 and is_manual:
            # Search for the last manual invoice sequence in this company
            domain = [
                ('company_id', '=', company.id),
                ('move_type', 'in', ['out_invoice', 'out_refund']),
                ('is_manual_invoice', '=', True),
                ('id', '!=', self.id),
                ('name', '!=', '/'),
                ('state', '!=', 'cancel')
            ]
            last_manual = self.env['account.move'].sudo().search(domain, order='id desc', limit=1)
            if last_manual and last_manual.name:
                last_sequence = last_manual.name
                try:
                    fmt_str, fmt_vals = self._get_sequence_format_param(last_sequence)
                    if fmt_vals.get('seq', 0) >= limit:
                        raise UserError(_(
                            "Manual Invoice sequence limit of %s has been reached for company '%s'. "
                            "No more manual invoices can be created under this limit."
                        ) % (limit, company.name))
                except UserError:
                    raise
                except Exception:
                    pass
                return last_sequence
            else:
                # First manual invoice: starting sequence 0 so next sequence is 1
                starting = self._get_starting_sequence()
                fmt_str, fmt_vals = self._get_sequence_format_param(starting)
                fmt_vals['seq'] = 0
                return fmt_str.format(**fmt_vals)

        last_sequence = super()._get_last_sequence(relaxed=relaxed, with_prefix=with_prefix)

        if limit > 0 and not is_manual:
            # Standard non-manual invoices start sequence after manual limit (limit + 1)
            if not last_sequence:
                starting = self._get_starting_sequence()
                fmt_str, fmt_vals = self._get_sequence_format_param(starting)
                fmt_vals['seq'] = limit
                last_sequence = fmt_str.format(**fmt_vals)
            else:
                try:
                    fmt_str, fmt_vals = self._get_sequence_format_param(last_sequence)
                    if fmt_vals.get('seq', 0) < limit:
                        fmt_vals['seq'] = limit
                        last_sequence = fmt_str.format(**fmt_vals)
                except Exception:
                    pass

        return last_sequence

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            is_manual = vals.get('is_manual_invoice') or self.env.context.get('default_is_manual_invoice', False)
            company_id = vals.get('company_id') or self.env.company.id
            company = self.env['res.company'].browse(company_id)

            limit = 0
            if company and company.use_so_manual_sequence_limit and company.so_manual_sequence_limit > 0:
                limit = company.so_manual_sequence_limit

            if limit > 0 and is_manual:
                manual_count = self.sudo().search_count([
                    ('company_id', '=', company.id),
                    ('move_type', 'in', ['out_invoice', 'out_refund']),
                    ('is_manual_invoice', '=', True),
                    ('state', '!=', 'cancel')
                ])
                if manual_count >= limit:
                    raise UserError(_(
                        "Manual Invoice sequence limit of %s has been reached for company '%s'. "
                        "No more manual invoices can be created under this limit."
                    ) % (limit, company.name))
        return super().create(vals_list)

    # --- Payment Attachment (copied from Sale Order at invoice creation) ---
    payment_attachment = fields.Binary(
        string='Payment Proof',
        attachment=True,
        help="Payment proof copied from the Sale Order. Verify before posting."
    )
    payment_attachment_name = fields.Char(string='payment File Name')

    is_return_approval_required = fields.Boolean(compute='_compute_is_return_approval_required')

    @api.depends('move_type', 'state')
    def _compute_is_return_approval_required(self):
        for move in self:
            move.is_return_approval_required = (move.move_type == 'out_refund')

    def action_submit_return_approval(self):
        self.ensure_one()
        if self.move_type != 'out_refund':
            return
        self.approval_state = 'manager_approval'
        self._notify_return_approvers('yohannes_sale_approval_workflow.group_operational_manager', "Return Approval Required")

    def action_approve_return_manager(self):
        self.ensure_one()
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
        if self.amount_total > 50000:
            self.approval_state = 'gm_approval'
            self._notify_return_approvers('yohannes_sale_approval_workflow.group_price_change_approver', "Return GM Approval Required")
        else:
            self.approval_state = 'approved'
            self.message_post(body=_("Return approved by Manager. Ready to post."))

    def action_approve_return_gm(self):
        self.ensure_one()
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
        if self.amount_total > 200000:
            self.approval_state = 'ceo_approval'
            self._notify_return_approvers('yohannes_sale_approval_workflow.group_price_change_approver', "Return CEO Approval Required")
        else:
            self.approval_state = 'approved'
            self.message_post(body=_("Return approved by GM. Ready to post."))

    def action_approve_return_ceo(self):
        self.ensure_one()
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
        self.approval_state = 'approved'
        self.message_post(body=_("Return approved by CEO. Ready to post."))

    def preview_invoice(self):
        """Override the standard portal preview to open the Invoice HTML in the browser"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/html/account.account_invoices/%s' % self.id,
            'target': 'new',
        }

    def action_register_payment(self):
        """Block Cashiers from registering payments even if they find a way to click the button"""
        if self.env.user.has_group('yohannes_sale_approval_workflow.group_sales_cashier') and not self.env.user.has_group('yohannes_sale_approval_workflow.group_finance_approver') and not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_("Cashiers are only permitted to create and confirm invoices. Payment registration must be done by the Finance Admin."))

        activities = self.env['mail.activity'].search([
            ('res_model', '=', self._name),
            ('res_id', 'in', self.ids),
            ('summary', 'ilike', 'Payment Registration')
        ])
        for record_id in self.ids:
            rec_activities = activities.filtered(lambda a: a.res_id == record_id)
            if rec_activities:
                rec_activities[0].write({'note': False, 'user_id': self.env.user.id})
                rec_activities[0].action_done()
                if len(rec_activities) > 1:
                    rec_activities[1:].unlink()

        return super(AccountMove, self).action_register_payment()

    def action_post(self):
        """Override post to ensure approval is completed for Credit Notes"""
        for move in self:
            if move.move_type == 'out_refund' and move.approval_state != 'approved' and not self.env.context.get('skip_return_approval'):
                raise UserError(_("This Credit Note must be approved by management before it can be posted."))
        
        res = super(AccountMove, self).action_post()
        
        for move in self.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted'):
            sale_lines = move.mapped('invoice_line_ids.sale_line_ids')
            orders = sale_lines.mapped('order_id')
            
            if orders:
                inv_activities = move.env['mail.activity'].search([
                    ('res_model', '=', 'sale.order'),
                    ('res_id', 'in', orders.ids),
                    ('summary', 'ilike', 'Invoice Preparation')
                ])
                for order_id in orders.ids:
                    rec_activities = inv_activities.filtered(lambda a: a.res_id == order_id)
                    if rec_activities:
                        rec_activities[0].write({'note': False, 'user_id': self.env.user.id})
                        rec_activities[0].action_done()
                        if len(rec_activities) > 1:
                            rec_activities[1:].unlink()

            ordered_lines = sale_lines.filtered(lambda l: l.product_id.invoice_policy == 'order' and not l.order_id.is_proforma)
            if ordered_lines:
                ordered_lines.with_context(skip_ordered_policy_check=True)._action_launch_stock_rule()
                
                for order in ordered_lines.mapped('order_id'):
                    if hasattr(order, 'consignment_request_id') and order.consignment_request_id:
                        continue
                        
                    order.message_post(body=_("Invoice confirmed. Delivery has been created."))
                    
                    warehouse_group_xmlid = 'yohannes_sale_approval_workflow.group_warehouse_user'
                    try:
                        group = order.env.ref(warehouse_group_xmlid)
                        users = group.users if hasattr(group, 'users') else (group.user_ids if hasattr(group, 'user_ids') else [])
                        for user in users:
                            order.activity_schedule(
                                'mail.mail_activity_data_todo',
                                summary=f"Delivery Preparation - {order.name}",
                                note="Invoice confirmed. Please prepare items for delivery.",
                                user_id=user.id,
                            )
                    except Exception:
                        pass
                        
            try:
                finance_group = move.env.ref('yohannes_sale_approval_workflow.group_finance_approver')
                finance_users = finance_group.users if hasattr(finance_group, 'users') else (finance_group.user_ids if hasattr(finance_group, 'user_ids') else [])
                for user in finance_users:
                    move.activity_schedule(
                        'mail.mail_activity_data_todo',
                        summary=f"Payment Registration - {move.name}",
                        note="Invoice confirmed. Please review and register the payment.",
                        user_id=user.id,
                    )
                move.message_post(body=_("Finance Admin notified for payment registration."))
            except Exception:
                pass
                
        return res

    def _notify_return_approvers(self, group_xmlid, summary):
        try:
            group = self.env.ref(group_xmlid)
            users = group.users if hasattr(group, 'users') else (group.user_ids if hasattr(group, 'user_ids') else [])
            for user in users:
                self.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=summary,
                    note=f"Credit Note {self.name or self.ref} requires your approval.",
                    user_id=user.id,
                )
        except Exception:
            pass
