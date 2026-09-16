from odoo import models, fields


class SaleApprovalWorkflow(models.Model):
    _name = 'sale.approval.workflow'
    _description = 'Sale Approval Workflow History'

    name = fields.Char(string='Description')
    sale_order_id = fields.Many2one(
        'sale.order', string='Sale Order', ondelete='cascade', index=True)
    approver_id = fields.Many2one(
        'res.users', string='Intended Approver',
        help="The user or group member expected to take action")
    user_id = fields.Many2one(
        'res.users', string='Action By',
        default=lambda self: self.env.user,
        help="The user who actually performed the action")
    approval_date = fields.Datetime(string='Date/Time', default=fields.Datetime.now)
    level = fields.Char(string='Approval Level')
    comments = fields.Text(string='Comments')
    action = fields.Selection([
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Action')
    state = fields.Selection([
        ('draft', 'Quotation'),
        ('price_change_approval', 'Discount Approval'),
        ('operational_approval', 'Manager Approval'),
        ('finance_approval', 'Finance Approval'),
        ('approved', 'Approved'),
        ('cancel', 'Rejected'),
    ], string='Workflow Step')