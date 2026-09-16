from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    bypass_credit_limit_check = fields.Boolean(
        string="Bypass Credit Limit Check",
        default=False,
        help="When checked, the system will completely skip credit limit validations for sales orders and invoices."
    )
