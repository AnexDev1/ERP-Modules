
from odoo import fields, models

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sale_type = fields.Selection([
        ('cash', 'Cash'),
        ('credit', 'Credit'),
    ], string='Sale Type', required=True, default='cash')
    payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Payment Terms',
        help='Select payment terms for credit sales'
    )
