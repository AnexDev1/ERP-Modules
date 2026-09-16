from odoo import models, fields, api


class StockMove(models.Model):
    _inherit = 'stock.move'

    product_categ_id = fields.Many2one('product.category', related='product_id.categ_id', store=True, string='Product Category')
