from odoo import fields, models


class HrPayslipInput(models.Model):
    _name = 'hr.payslip.input'
    _description = 'Payslip Input'
    _order = 'payslip_id, sequence'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    payslip_id = fields.Many2one('hr.payslip', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(required=True, default=10)
    contract_id = fields.Many2one('hr.version', required=True, ondelete='restrict')
    amount = fields.Float()
    amount_qty = fields.Float()
