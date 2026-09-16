from odoo import fields, models


class RrgMeter(models.Model):
    _name = 'rrg.meter'
    _description = 'Utility Meter Rate'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    price = fields.Float(digits=(16, 4))
    building_id = fields.Many2one('rrg.building', ondelete='set null')
