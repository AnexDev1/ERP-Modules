from odoo import fields, models


class PayslipLinesContributionRegister(models.TransientModel):
    _name = 'payslip.lines.contribution.register'
    _description = 'Payslip Lines Contribution Register'

    register_id = fields.Many2one('hr.contribution.register')
    date_from = fields.Date()
    date_to = fields.Date()


class ReportPayslipDetails(models.AbstractModel):
    _name = 'report.payroll.report_payslipdetails'
    _description = 'Payslip Details Report'

    def _get_report_values(self, docids, data=None):
        return {
            'doc_ids': docids,
            'doc_model': 'hr.payslip',
            'docs': self.env['hr.payslip'].browse(docids),
            'data': data or {},
        }


class ReportContributionRegister(models.AbstractModel):
    _name = 'report.payroll.report_contributionregister'
    _description = 'Contribution Register Report'

    def _get_report_values(self, docids, data=None):
        return {
            'doc_ids': docids,
            'doc_model': 'hr.contribution.register',
            'docs': self.env['hr.contribution.register'].browse(docids),
            'data': data or {},
        }
