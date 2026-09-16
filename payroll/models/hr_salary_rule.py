from odoo import api, fields, models

AMOUNT_SELECT = [
    ('percentage', 'Percentage (%)'),
    ('fix', 'Fixed Amount'),
    ('code', 'Python Code'),
]
CONDITION_SELECT = [
    ('none', 'Always True'),
    ('range', 'Range'),
    ('python', 'Python Expression'),
]


class HrRuleInput(models.Model):
    _name = 'hr.rule.input'
    _description = 'Salary Rule Input'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    input_id = fields.Many2one('hr.salary.rule', required=True, ondelete='restrict')


class HrSalaryRule(models.Model):
    _name = 'hr.salary.rule'
    _description = 'Salary Rule'
    _order = 'sequence, id'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(required=True, default=5)
    category_id = fields.Many2one('hr.salary.rule.category', ondelete='set null')
    parent_rule_id = fields.Many2one('hr.salary.rule', ondelete='set null', index=True)
    child_ids = fields.One2many('hr.salary.rule', 'parent_rule_id')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    register_id = fields.Many2one('hr.contribution.register', ondelete='set null')
    active = fields.Boolean(default=True)
    appears_on_payslip = fields.Boolean(default=True)
    note = fields.Text()
    quantity = fields.Char(default='1.0')
    condition_select = fields.Selection(CONDITION_SELECT, required=True, default='none')
    condition_range = fields.Char()
    condition_range_min = fields.Float()
    condition_range_max = fields.Float()
    condition_python = fields.Text(required=True, default='result = True')
    amount_select = fields.Selection(AMOUNT_SELECT, required=True, default='fix', index=True)
    amount_fix = fields.Float()
    amount_percentage = fields.Float()
    amount_percentage_base = fields.Char()
    amount_python_compute = fields.Text()
    input_ids = fields.One2many('hr.rule.input', 'input_id')
    require_code_and_category = fields.Boolean(compute='_compute_require_code_and_category')

    @api.depends('code', 'category_id')
    def _compute_require_code_and_category(self):
        for rule in self:
            rule.require_code_and_category = not (rule.code and rule.category_id)

    def _satisfy_condition(self, localdict):
        self.ensure_one()
        if self.condition_select == 'none':
            return True
        if self.condition_select == 'range':
            try:
                value = eval(self.condition_range or '0', localdict)  # noqa: S307
                return self.condition_range_min <= value <= self.condition_range_max
            except Exception:
                return False
        try:
            eval(self.condition_python or 'result = False', localdict, localdict)  # noqa: S307
            return bool(localdict.get('result'))
        except Exception:
            return False

    def _compute_rule(self, localdict):
        self.ensure_one()
        try:
            qty = float(eval(self.quantity or '1.0', localdict))  # noqa: S307
        except Exception:
            qty = 1.0
        if self.amount_select == 'fix':
            amount = self.amount_fix or 0.0
        elif self.amount_select == 'percentage':
            try:
                base = float(eval(self.amount_percentage_base or '0', localdict))  # noqa: S307
            except Exception:
                base = 0.0
            amount = base * (self.amount_percentage or 0.0) / 100.0
        else:
            try:
                eval(self.amount_python_compute or 'result = 0', localdict, localdict)  # noqa: S307
                amount = float(localdict.get('result') or 0.0)
            except Exception:
                amount = 0.0
        return amount, qty, 100.0
