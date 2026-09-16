from odoo import fields, models


class HrPayslipWorkedDays(models.Model):
    _name = 'hr.payslip.worked.days'
    _description = 'Payslip Worked Days'
    _order = 'payslip_id, sequence'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    payslip_id = fields.Many2one('hr.payslip', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(required=True, default=10)
    contract_id = fields.Many2one('hr.version', required=True, ondelete='restrict')
    number_of_days = fields.Float()
    number_of_hours = fields.Float()
