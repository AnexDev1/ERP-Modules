from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    trade_default_rec_cash_id = fields.Many2one(
        related='company_id.trade_default_rec_cash_id',
        string="Trade Rec Cash Account",
        readonly=False,
        domain="[('account_type', '=', 'asset_receivable')]",
    )
    trade_default_rec_credit_id = fields.Many2one(
        related='company_id.trade_default_rec_credit_id',
        string="Trade Rec Credit Account",
        readonly=False,
        domain="[('account_type', '=', 'asset_receivable')]",
    )
    trade_default_payable_id = fields.Many2one(
        related='company_id.trade_default_payable_id',
        string="Trade Payable Account",
        readonly=False,
        domain="[('account_type', '=', 'liability_payable')]",
    )

