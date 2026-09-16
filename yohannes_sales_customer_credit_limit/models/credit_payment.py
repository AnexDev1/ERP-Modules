from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta

class CreditPayment(models.Model):
    _name = 'credit.payment'
    _description = 'Credit Payment'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Reference", required=True, default="New", tracking=True)
    partner_id = fields.Many2one('res.partner', string="Partner", required=True, tracking=True)
    amount = fields.Monetary(string="Amount", currency_field='currency_id', required=True)
    currency_id = fields.Many2one('res.currency', string="Currency", related='partner_id.currency_id')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('paid', 'Paid'),
    ], string="Status", default='draft', tracking=True)
    due_date = fields.Date(string="Due Date", compute="_compute_dates", store=True, readonly=False)
    payment_date = fields.Date(string="Payment Date", compute="_compute_dates", store=True, readonly=False)
    invoice_id = fields.Many2one('account.move', string="Invoice", domain="[('move_type', '=', 'out_invoice'), ('partner_id', '=', partner_id)]")
    payment_id = fields.Many2one('account.payment', string="Payment")
    payment_term_id = fields.Many2one('account.payment.term', string="Payment Term")
    notification_sent = fields.Boolean(string="Notification Sent", default=False)

    @api.depends('payment_term_id', 'invoice_id.invoice_date')
    def _compute_dates(self):
        for record in self:
            if record.payment_term_id and record.invoice_id and record.invoice_id.invoice_date:
                days = record.payment_term_id.line_ids[0].nb_days if record.payment_term_id.line_ids else 0
                record.payment_date = record.invoice_id.invoice_date + timedelta(days=days)
                record.due_date = record.payment_date - timedelta(days=3)
            elif not record.payment_date: # Only reset if not set manually (though store=True/readonly=False allows manual override, compute usually takes precedence if dependencies change)
                 # Keep existing values if manually set or not computable
                 pass

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('credit.payment') or 'New'
        return super().create(vals_list)

    def action_confirm(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Only draft payments can be confirmed."))
        self.write({'state': 'confirmed'})
        return True

    def action_paid(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_("Only confirmed payments can be marked as paid."))
        if not self.payment_id:
            raise UserError(_("No payment linked to this credit payment."))
        self.payment_date = fields.Date.today()
        self.write({'state': 'paid'})
        return True

    @api.model
    def check_due_dates(self):
        today = fields.Date.today()
        notification_date = today + timedelta(days=3)
        overdue_payments = self.search([
            ('due_date', '<', today),
            ('state', 'not in', ['paid'])
        ])
        upcoming_payments = self.search([
            ('due_date', '=', notification_date),
            ('state', 'not in', ['paid'])
        ])
        for payment in upcoming_payments:
            payment.message_post(
                body=f"Payment due in 3 days (Due Date: {payment.due_date})",
                subject="Upcoming Payment Due",
                partner_ids=[payment.partner_id.id])
        for payment in overdue_payments:
            payment.message_post(
                body=f"Payment overdue (Due Date: {payment.due_date})",
                subject="Overdue Payment",
                partner_ids=[payment.partner_id.id] )