from odoo import models, fields

class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    display_terms_on_invoice = fields.Boolean(string="Display terms on invoice")
    apply_credit_limit = fields.Boolean(string="Apply credit limit", default=True)
    delivery_after_payment = fields.Boolean(string="Delivery after payment")
    minimum_order_amount = fields.Monetary(string="Minimum order amount", currency_field='company_currency_id')
    term_used_under = fields.Selection([
        ('sale', 'Sales'),
        ('purchase', 'Purchases'),
        ('both', 'Both')
    ], string="Term used under", default='both')
    related_payment_term_id = fields.Many2one('account.payment.term', string="Related Payment Terms")
    
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string="Company Currency", readonly=True)
