from odoo import models, fields

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    mtov_type_id = fields.Many2one(
        'stock.picking.type',
        string='MTOV Operation Type',
        domain="[('code', '=', 'internal'), ('company_id', '=', company_id)]"
    )
    
    mtiv_type_id = fields.Many2one(
        'stock.picking.type',
        string='MTIV Operation Type',
        domain="[('code', '=', 'internal'), ('company_id', '=', company_id)]"
    )

