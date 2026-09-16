from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # customer_type_id = fields.Many2one('customer.type', string='Customer Type',
    #                                    help="Customer type for discount rules.")