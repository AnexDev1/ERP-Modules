from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    trade_rec_credit_account_id = fields.Many2one(
        'account.account', company_dependent=True,
        string="Trade Rec Credit Account",
        domain="[('account_type', '=', 'asset_receivable')]",
        help="This account will be used instead of the default one as the receivable account for Credit sales."
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            company = record.company_id or self.env.company
            vals = {}
            # Always apply company default for credit receivable if configured
            if company.trade_default_rec_credit_id:
                vals['trade_rec_credit_account_id'] = company.trade_default_rec_credit_id.id
            # Always apply company default for cash receivable if configured
            if company.trade_default_rec_cash_id:
                vals['property_account_receivable_id'] = company.trade_default_rec_cash_id.id
            # Always apply company default for payable if configured
            if company.trade_default_payable_id:
                vals['property_account_payable_id'] = company.trade_default_payable_id.id
            if vals:
                record.write(vals)
        return records

