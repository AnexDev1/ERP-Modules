from odoo import models

class StockLot(models.Model):
    _inherit = 'stock.lot'
    
    # Ensure lots are ordered by FEFO (First Expiring First Out) globally
    _order = 'expiration_date ASC, name'
