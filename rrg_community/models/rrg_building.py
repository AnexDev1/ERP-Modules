from odoo import fields, models


class RrgBuilding(models.Model):
    _name = 'rrg.building'
    _description = 'Building'
    _order = 'name'

    name = fields.Char(required=True)
    street = fields.Char()
    street2 = fields.Char()
    city = fields.Char()
    zip = fields.Char()
    country_id = fields.Many2one('res.country')
    state_id = fields.Many2one('res.country.state')
    meter_ids = fields.One2many('rrg.meter', 'building_id')
    analytic_account_ids = fields.One2many('account.analytic.account', 'x_property_building_id')
    analytic_count = fields.Integer(compute='_compute_analytic_count')

    def _compute_analytic_count(self):
        for rec in self:
            rec.analytic_count = len(rec.analytic_account_ids)

    def action_open_units(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Units',
            'res_model': 'account.analytic.account',
            'view_mode': 'list,form',
            'domain': [('x_property_building_id', '=', self.id)],
        }
