from odoo import api, fields, models

class Warehouse(models.Model):
    _inherit = 'stock.warehouse'

    wh_type = fields.Selection([
        ('import', 'Import'),
        ('wholesale', 'Wholesale')
    ], string="Warehouse Type", default='wholesale')
    
    analytic_account_id = fields.Many2one('account.analytic.account', string="Analytic Account")
