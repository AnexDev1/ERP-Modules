from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _name = 'hr.payslip'
    _description = 'Pay Slip'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char()
    number = fields.Char(copy=False)
    employee_id = fields.Many2one('hr.employee', required=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    contract_id = fields.Many2one('hr.version', ondelete='set null')
    struct_id = fields.Many2one('hr.payroll.structure', ondelete='set null')
    payslip_run_id = fields.Many2one('hr.payslip.run', ondelete='set null')
    refunded_id = fields.Many2one('hr.payslip', ondelete='set null')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('verify', 'Waiting'),
        ('done', 'Done'),
        ('cancel', 'Rejected'),
    ], default='draft', index=True, tracking=True)
    date_from = fields.Date(required=True, default=lambda self: date.today().replace(day=1))
    date_to = fields.Date(
        required=True,
        default=lambda self: (date.today().replace(day=1) + relativedelta(months=1, days=-1)),
    )
    compute_date = fields.Date()
    note = fields.Text()
    paid = fields.Boolean()
    credit_note = fields.Boolean()
    basic_wage = fields.Float()
    gross_wage = fields.Float()
    net_wage = fields.Float()
    hide_child_lines = fields.Boolean()
    hide_invisible_lines = fields.Boolean()
    line_ids = fields.One2many('hr.payslip.line', 'slip_id')
    input_line_ids = fields.One2many('hr.payslip.input', 'payslip_id')
    worked_days_line_ids = fields.One2many('hr.payslip.worked.days', 'payslip_id')
    dynamic_filtered_payslip_lines = fields.One2many(
        'hr.payslip.line', compute='_compute_dynamic_lines',
    )
    payslip_count = fields.Integer(compute='_compute_payslip_count')
    allow_cancel_payslips = fields.Boolean(compute='_compute_flags')
    prevent_compute_on_confirm = fields.Boolean(compute='_compute_flags')

    @api.depends('line_ids', 'hide_child_lines', 'hide_invisible_lines')
    def _compute_dynamic_lines(self):
        for slip in self:
            lines = slip.line_ids
            if slip.hide_child_lines:
                lines = lines.filtered(lambda line: not line.parent_line_id)
            if slip.hide_invisible_lines:
                lines = lines.filtered('appears_on_payslip')
            slip.dynamic_filtered_payslip_lines = lines

    @api.depends('employee_id')
    def _compute_payslip_count(self):
        for slip in self:
            slip.payslip_count = self.search_count([('employee_id', '=', slip.employee_id.id)]) if slip.employee_id else 0

    @api.depends('state')
    def _compute_flags(self):
        for slip in self:
            slip.allow_cancel_payslips = slip.state in ('draft', 'verify', 'done')
            slip.prevent_compute_on_confirm = slip.state == 'done'

    @api.onchange('employee_id', 'date_from', 'date_to')
    def _onchange_employee(self):
        if not self.employee_id:
            return
        version = (
            self.employee_id.version_id
            if 'version_id' in self.employee_id._fields else self.env['hr.version']
        ) or self.employee_id.version_ids[:1]
        self.contract_id = version
        self.company_id = self.employee_id.company_id or self.env.company
        if version and 'struct_id' in version._fields and version.struct_id:
            self.struct_id = version.struct_id
        self.name = f'Salary Slip - {self.employee_id.name} - {self.date_from}'

    def compute_sheet(self):
        for slip in self:
            slip.line_ids.unlink()
            contract = slip.contract_id
            structure = slip.struct_id or (contract.struct_id if contract and 'struct_id' in contract._fields else False)
            if not contract:
                raise UserError(self.env._('Set a contract on the payslip first.'))
            if not structure:
                raise UserError(self.env._('Set a salary structure on the payslip or contract.'))
            localdict = slip._get_localdict(contract)
            lines = []
            sequence = 5
            for rule in structure._get_parent_structure().mapped('rule_ids').sorted('sequence'):
                if not rule.active or not rule._satisfy_condition(localdict):
                    continue
                amount, qty, rate = rule._compute_rule(localdict)
                total = amount * qty * rate / 100.0
                localdict[rule.code or f'R{rule.id}'] = total
                localdict.setdefault('categories', {})
                if rule.category_id and rule.category_id.code:
                    localdict['categories'][rule.category_id.code] = (
                        localdict['categories'].get(rule.category_id.code, 0.0) + total
                    )
                lines.append({
                    'name': rule.name,
                    'code': rule.code,
                    'sequence': sequence,
                    'slip_id': slip.id,
                    'employee_id': slip.employee_id.id,
                    'contract_id': contract.id,
                    'salary_rule_id': rule.id,
                    'category_id': rule.category_id.id,
                    'parent_rule_id': rule.parent_rule_id.id,
                    'company_id': slip.company_id.id,
                    'register_id': rule.register_id.id,
                    'date_from': slip.date_from,
                    'quantity': qty,
                    'amount': amount,
                    'rate': rate,
                    'total': total,
                    'amount_select': rule.amount_select,
                    'amount_fix': rule.amount_fix,
                    'amount_percentage': rule.amount_percentage,
                    'amount_percentage_base': rule.amount_percentage_base,
                    'amount_python_compute': rule.amount_python_compute,
                    'condition_select': rule.condition_select,
                    'condition_python': rule.condition_python or 'result = True',
                    'appears_on_payslip': rule.appears_on_payslip,
                })
                sequence += 5
            if lines:
                self.env['hr.payslip.line'].create(lines)
            slip.compute_date = fields.Date.context_today(slip)
            if not slip.number:
                slip.number = self.env['ir.sequence'].next_by_code('hr.payslip') or str(slip.id)
        return True

    def _get_localdict(self, contract):
        wage = 0.0
        if contract:
            for fname in ('wage', 'contract_wage', 'monthly_wage'):
                if fname in contract._fields and contract[fname]:
                    wage = contract[fname]
                    break
        inputs = {line.code: line.amount or 0.0 for line in self.input_line_ids if line.code}
        worked = {line.code: line.number_of_days or 0.0 for line in self.worked_days_line_ids if line.code}
        return {
            'payslip': self,
            'employee': self.employee_id,
            'contract': contract,
            'version': contract,
            'wage': wage,
            'categories': {},
            'inputs': inputs,
            'worked_days': worked,
            'result': None,
            'result_qty': 1.0,
            'result_rate': 100.0,
        }

    def action_payslip_draft(self):
        self.write({'state': 'draft'})

    def action_payslip_done(self):
        for slip in self.filtered(lambda rec: rec.state in ('draft', 'verify')):
            if not slip.line_ids:
                slip.compute_sheet()
            slip.state = 'done'
            slip.paid = True

    def action_payslip_cancel(self):
        self.write({'state': 'cancel', 'paid': False})

    def action_payslip_verify(self):
        self.write({'state': 'verify'})
