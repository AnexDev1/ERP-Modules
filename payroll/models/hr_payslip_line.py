from odoo import api, fields, models

from .hr_salary_rule import AMOUNT_SELECT, CONDITION_SELECT


class HrPayslipLine(models.Model):
    _name = 'hr.payslip.line'
    _description = 'Payslip Line'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(required=True, default=5, index=True)
    slip_id = fields.Many2one('hr.payslip', required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', required=True, ondelete='restrict')
    contract_id = fields.Many2one('hr.version', required=True, ondelete='restrict', index=True)
    salary_rule_id = fields.Many2one('hr.salary.rule', required=True, ondelete='restrict')
    category_id = fields.Many2one('hr.salary.rule.category', ondelete='set null')
    parent_rule_id = fields.Many2one('hr.salary.rule', ondelete='set null', index=True)
    parent_line_id = fields.Many2one('hr.payslip.line', ondelete='set null')
    child_ids = fields.One2many('hr.payslip.line', 'parent_line_id')
    company_id = fields.Many2one('res.company', related='slip_id.company_id', store=True)
    register_id = fields.Many2one('hr.contribution.register', ondelete='set null')
    date_from = fields.Date()
    note = fields.Text()
    quantity = fields.Float(default=1.0)
    amount = fields.Float()
    amount_fix = fields.Float()
    amount_percentage = fields.Float()
    amount_percentage_base = fields.Char()
    amount_python_compute = fields.Text()
    amount_select = fields.Selection(AMOUNT_SELECT, required=True, default='fix', index=True)
    condition_select = fields.Selection(CONDITION_SELECT, required=True, default='none')
    condition_python = fields.Text(required=True, default='result = True')
    condition_range = fields.Char()
    condition_range_min = fields.Float()
    condition_range_max = fields.Float()
    rate = fields.Float(default=100.0)
    total = fields.Float()
    active = fields.Boolean(default=True)
    appears_on_payslip = fields.Boolean(default=True)
    input_ids = fields.One2many(related='salary_rule_id.input_ids')
    payslip_run_id = fields.Many2one(related='slip_id.payslip_run_id')
    allow_edit_payslip_lines = fields.Boolean(compute='_compute_allow_edit')
    require_code_and_category = fields.Boolean(compute='_compute_require_code')

    @api.depends('slip_id.state')
    def _compute_allow_edit(self):
        for line in self:
            line.allow_edit_payslip_lines = line.slip_id.state in ('draft', 'verify')

    @api.depends('code', 'category_id')
    def _compute_require_code(self):
        for line in self:
            line.require_code_and_category = not (line.code and line.category_id)
