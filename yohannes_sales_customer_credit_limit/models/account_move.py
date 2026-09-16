from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import timedelta

class AccountMove(models.Model):
    _inherit = 'account.move'

    sale_type = fields.Selection([
        ('cash', 'Cash'),
        ('credit', 'Credit'),
    ], string='Sale Type',required=True, default='cash')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)

    @api.model
    def create(self, vals):
        move = super().create(vals)
        if move.move_type == 'out_invoice' and move.partner_id and move.sale_type == 'credit':
            # Determine payment term
            payment_term = move.invoice_payment_term_id or move.sale_order_id.payment_term_id
            
            # Use invoice_date_due if available, otherwise calculate
            if move.invoice_date_due:
                due_date = move.invoice_date_due
            else:
                days = max(payment_term.line_ids.mapped('nb_days'), default=0) if payment_term else 0
                invoice_date = move.invoice_date or fields.Date.today()
                due_date = invoice_date + timedelta(days=days)

            # Create credit payment record
            self.env['credit.payment'].create({
                'partner_id': move.partner_id.id,
                'amount': move.amount_total,
                'due_date': due_date,
                'invoice_id': move.id,
                'state': 'draft',
                'payment_term_id': payment_term.id if payment_term else False,
            })
        return move

    def action_post(self):
        res = super().action_post()
        for move in self:
            if move.company_id.bypass_credit_limit_check:
                continue
            if move.move_type == 'out_invoice' and move.sale_type == 'credit':
                credit_record = self.env['customer.credit'].search([
                    ('partner_id', '=', move.partner_id.id),
                    ('state', '=', 'validated'),
                    '|', ('company_id', '=', False), ('company_id', '=', move.company_id.id)
                ], limit=1)
                
                if not credit_record:
                    credit_record = self.env['customer.credit'].search([
                        ('partner_id', '=', move.partner_id.id),
                        '|', ('company_id', '=', False), ('company_id', '=', move.company_id.id)
                    ], limit=1)
                    
                if credit_record and move.amount_residual > credit_record.maximum_credit:
                    raise UserError(
                        f"Invoice amount ({move.amount_residual}) exceeds credit limit ({credit_record.maximum_credit}) for {move.partner_id.name}."
                    )
        return res

    def write(self, vals):
        res = super().write(vals)
        if 'payment_state' in vals:
            for move in self:
                if move.move_type == 'out_invoice' and move.sale_type == 'credit' and move.payment_state == 'paid':
                    credit_payment = self.env['credit.payment'].search([('invoice_id', '=', move.id)], limit=1)
                    if credit_payment and credit_payment.state != 'paid':
                        credit_payment.action_paid()
        return res