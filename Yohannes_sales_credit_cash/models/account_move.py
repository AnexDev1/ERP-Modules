from odoo import models, api

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.depends('display_type', 'company_id')
    def _compute_account_id(self):
        super()._compute_account_id()
        for line in self:
            # Only affect receivable lines (for invoices)
            if line.display_type == 'payment_term' and line.move_id.is_invoice(include_receipts=True) and line.move_id.move_type == 'out_invoice':
                if hasattr(line.move_id, 'sale_type') and line.move_id.sale_type:
                    cash_acc_id = line.partner_id.property_account_receivable_id.id
                    credit_acc_id = line.partner_id.trade_rec_credit_account_id.id
                    
                    if line.move_id.sale_type == 'cash' and cash_acc_id:
                        line.account_id = int(cash_acc_id)
                    elif line.move_id.sale_type == 'credit' and credit_acc_id:
                        line.account_id = int(credit_acc_id)
