from odoo import fields, models


class HrPayrollStructureType(models.Model):
    _name = 'hr.payroll.structure.type'
    _description = 'Salary Structure Type'

    name = fields.Char()
    country_id = fields.Many2one('res.country', ondelete='set null')
    default_resource_calendar_id = fields.Many2one('resource.calendar', ondelete='set null')
