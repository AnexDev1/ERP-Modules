from odoo import models, fields

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    enable_order_source = fields.Boolean(
        related='company_id.enable_order_source',
        string="Enable Order Source",
        readonly=True
    )
