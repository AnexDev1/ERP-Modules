from odoo import models, fields, api, _
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sale_type = fields.Selection([
        ('cash', 'Cash'),
        ('credit', 'Credit'),
    ], string='Sale Type', required=True, compute='_compute_sale_type', store=True, readonly=True, force_save=True, tracking=True)
    customer_credit_id = fields.Many2one('customer.credit', string="Customer Credit", compute="_compute_customer_credit", store=True)
    credit = fields.Monetary(string="Unsettled Amount", related="partner_id.credit", readonly=True)
    maximum_credit = fields.Monetary(string="Credit Limit", related="customer_credit_id.maximum_credit", readonly=True)
    matured_amount = fields.Monetary(string="Available Credit", related="customer_credit_id.matured_amount", readonly=True)
    payment_terms = fields.Many2one(string="Maximum Payment Term", related="customer_credit_id.payment_term_credit", readonly=True)
    is_credit_positive = fields.Boolean(string="Is Credit Positive", compute="_compute_credit_state", store=True)
    is_credit_negative = fields.Boolean(string="Is Credit Negative", compute="_compute_credit_state", store=True)

    @api.depends('payment_term_id')
    def _compute_sale_type(self):
        for order in self:
            if order.payment_term_id:
                if order.payment_term_id.apply_credit_limit:
                    order.sale_type = 'credit'
                else:
                    order.sale_type = 'cash'
            else:
                order.sale_type = 'cash'

    @api.depends('credit')
    def _compute_credit_state(self):
        for order in self:
            order.is_credit_positive = order.credit > 0
            order.is_credit_negative = order.credit < 0

    @api.depends('partner_id', 'partner_id.commercial_partner_id', 'company_id')
    def _compute_customer_credit(self):
        for order in self:
            if order.partner_id:
                # Odoo credit limits are usually linked to the commercial entity (the parent company).
                partner_id = order.partner_id.commercial_partner_id.id or order.partner_id.id
                
                # Try to find a validated credit record first for the specific company or all companies
                domain = [
                    ('partner_id', '=', partner_id),
                    ('state', '=', 'validated'),
                    '|', ('company_id', '=', False), ('company_id', '=', order.company_id.id)
                ]
                credit_record = self.env['customer.credit'].search(domain, limit=1)
                
                # Fallback to any record if no validated one is found
                if not credit_record:
                    domain_fallback = [
                        ('partner_id', '=', partner_id),
                        '|', ('company_id', '=', False), ('company_id', '=', order.company_id.id)
                    ]
                    credit_record = self.env['customer.credit'].search(domain_fallback, limit=1)
                    
                order.customer_credit_id = credit_record
            else:
                order.customer_credit_id = False

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        invoice_vals['sale_type'] = self.sale_type
        return invoice_vals

    def action_print_report(self):
        # Proxy method to call the report from sales.credit.report
        report_model = self.env['sales.credit.report']
        return report_model.with_context(
            self._context
        ).action_print_report()

    @api.constrains('payment_term_id', 'amount_total')
    def _check_minimum_order_amount(self):
        for order in self:
            if order.payment_term_id and order.payment_term_id.minimum_order_amount > 0:
                if order.amount_total < order.payment_term_id.minimum_order_amount:
                    raise UserError(
                        f"Payment term is not allowed for customer\n"
                        f"Minimum order amount for {order.payment_term_id.name} is {order.payment_term_id.minimum_order_amount}"
                    )

    @api.constrains('payment_term_id', 'customer_credit_id', 'sale_type')
    def _check_payment_term_limit(self):
        for order in self:
            if order.company_id.bypass_credit_limit_check:
                continue
            if order.sale_type == 'credit' and order.payment_term_id and order.customer_credit_id and order.customer_credit_id.payment_term_credit:
                order_days = max(order.payment_term_id.line_ids.mapped('nb_days')) if order.payment_term_id.line_ids else 0
                credit_days = max(order.customer_credit_id.payment_term_credit.line_ids.mapped('nb_days')) if order.customer_credit_id.payment_term_credit.line_ids else 0
                if order_days > credit_days:
                    raise UserError(_(
                        "Payment term is not allowed for this customer!\n\n"
                        "You selected a payment term of %(order_days)s days, but the maximum allowed for this customer is %(credit_days)s days."
                    ) % {
                        'order_days': order_days,
                        'credit_days': credit_days,
                    })