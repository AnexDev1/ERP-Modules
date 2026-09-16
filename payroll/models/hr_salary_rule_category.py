from odoo import fields, models


class HrSalaryRuleCategory(models.Model):
    _name = 'hr.salary.rule.category'
    _description = 'Salary Rule Category'
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    parent_id = fields.Many2one('hr.salary.rule.category', ondelete='set null')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    note = fields.Text()
