from odoo import fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    x_is_property = fields.Boolean(string='Is Property Unit')
    x_property_building_id = fields.Many2one('rrg.building', string='Building')
    x_property_address = fields.Char(string='Property Address')
    x_property_type = fields.Char(string='Property Type')
    x_studio_floor_no = fields.Char(string='Floor')
    x_rental_contract_id = fields.Many2one('sale.order', string='Rental Contract')
    x_invoice_status = fields.Char(string='Invoice Status')
