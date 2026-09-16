from odoo import fields, models


class HrVersion(models.Model):
    _inherit = 'hr.version'

    struct_id = fields.Many2one('hr.payroll.structure', ondelete='set null')
