from odoo import api, fields, models


class HrPayrollStructure(models.Model):
    _name = 'hr.payroll.structure'
    _description = 'Salary Structure'
    _check_company_auto = True

    name = fields.Char(required=True)
    code = fields.Char()
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, ondelete='restrict',
    )
    parent_id = fields.Many2one('hr.payroll.structure', ondelete='set null')
    children_ids = fields.One2many('hr.payroll.structure', 'parent_id')
    note = fields.Text()
    rule_ids = fields.Many2many(
        'hr.salary.rule',
        'hr_structure_salary_rule_rel',
        'struct_id',
        'rule_id',
        string='Salary Rules',
    )
    require_code = fields.Boolean(compute='_compute_require_code')

    @api.depends('code')
    def _compute_require_code(self):
        for rec in self:
            rec.require_code = not bool(rec.code)

    def _get_parent_structure(self):
        structures = self
        parent = self.parent_id
        while parent:
            structures |= parent
            parent = parent.parent_id
        return structures
