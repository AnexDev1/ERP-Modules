from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import fields, models


class HrPayslipRun(models.Model):
    _name = 'hr.payslip.run'
    _description = 'Payslip Batches'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, ondelete='restrict',
    )
    struct_id = fields.Many2one('hr.payroll.structure', ondelete='set null')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('verify', 'Verify'),
        ('close', 'Close'),
    ], default='draft', index=True)
    date_start = fields.Date(required=True, default=lambda self: date.today().replace(day=1))
    date_end = fields.Date(
        required=True,
        default=lambda self: (date.today().replace(day=1) + relativedelta(months=1, days=-1)),
    )
    credit_note = fields.Boolean()
    slip_ids = fields.One2many('hr.payslip', 'payslip_run_id')

    def action_validate(self):
        self.slip_ids.action_payslip_done()
        self.state = 'close'

    def action_draft(self):
        self.state = 'draft'
