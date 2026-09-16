from odoo import fields, models


class HrPayslipEmployees(models.TransientModel):
    _name = 'hr.payslip.employees'
    _description = 'Generate Payslips For Employees'

    employee_ids = fields.Many2many('hr.employee')

    def compute_sheet(self):
        run = self.env['hr.payslip.run'].browse(self.env.context.get('active_id'))
        if not run:
            return True
        slips = self.env['hr.payslip']
        for employee in self.employee_ids:
            slips |= slips.create({
                'employee_id': employee.id,
                'company_id': employee.company_id.id or run.company_id.id,
                'date_from': run.date_start,
                'date_to': run.date_end,
                'payslip_run_id': run.id,
                'struct_id': run.struct_id.id,
                'name': f'Salary Slip - {employee.name} - {run.date_start}',
            })
        slips.compute_sheet()
        return True


class HrPayslipChangeState(models.TransientModel):
    _name = 'hr.payslip.change.state'
    _description = 'Change Payslip State'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('verify', 'Waiting'),
        ('done', 'Done'),
        ('cancel', 'Rejected'),
    ])

    def change_state_confirm(self):
        slips = self.env['hr.payslip'].browse(self.env.context.get('active_ids', []))
        if self.state == 'draft':
            slips.action_payslip_draft()
        elif self.state == 'verify':
            slips.action_payslip_verify()
        elif self.state == 'done':
            slips.action_payslip_done()
        elif self.state == 'cancel':
            slips.action_payslip_cancel()
        return True
