from odoo import fields, models


class HrContributionRegister(models.Model):
    _name = 'hr.contribution.register'
    _description = 'Contribution Register'
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    partner_id = fields.Many2one('res.partner')
    note = fields.Text()
