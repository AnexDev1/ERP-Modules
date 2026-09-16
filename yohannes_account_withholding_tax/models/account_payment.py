from odoo import models, fields

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    withholding_certificate_no = fields.Char(
        string='Withholding Ref No.',
        help='Withholding Ref No.'
    )
