from odoo import models, fields

class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    cons_sample_operation_type = fields.Selection([
        ('issue', 'Consignment/Sample Issue'),
        ('receive', 'Consignment/Sample Receive'),
    ], string='Cons/sample Operation Type', help='Used to dynamically find the correct operation type for Consignment and Sample requests.')
