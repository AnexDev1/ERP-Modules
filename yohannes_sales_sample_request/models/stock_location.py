from odoo import models, fields

class StockLocation(models.Model):
    _inherit = 'stock.location'

    cons_sample_type = fields.Selection([
        ('free_sample', 'Free sample'),
        ('sample_issue_to_return', 'Sample issue to be returned'),
        ('sample_being_returned', 'Sample being returned'),
        ('consignment_customer', 'Consignment customer location'),
        ('consignment_vendor', 'Consignment vendor location'),
        ('sales_placement', 'Sales placement location'),
        ('internal_consumption', 'Internal consumption'),
    ], string='Cons/sample Type', help='Used to dynamically find the correct destination location for Consignment and Sample requests.')
