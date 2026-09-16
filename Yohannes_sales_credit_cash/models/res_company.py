from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    trade_default_rec_cash_id = fields.Many2one(
        'account.account',
        string="Default Trade Rec Cash Account",
        domain="[('account_type', '=', 'asset_receivable')]",
        help="Default receivable account for cash customers. Auto-filled on new customer creation.",
    )
    trade_default_rec_credit_id = fields.Many2one(
        'account.account',
        string="Default Trade Rec Credit Account",
        domain="[('account_type', '=', 'asset_receivable')]",
        help="Default receivable account for credit customers. Auto-filled on new customer creation.",
    )
    trade_default_payable_id = fields.Many2one(
        'account.account',
        string="Default Trade Payable Account",
        domain="[('account_type', '=', 'liability_payable')]",
        help="Default payable account for vendors. Auto-filled on new vendor creation.",
    )
