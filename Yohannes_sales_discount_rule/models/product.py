from odoo import api, fields, models

class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_core_product = fields.Boolean(string='Is Core Product', default=False,
                                     help="Indicates if this is a core product for discount rule purposes.")