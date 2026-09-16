from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountPaymentRegisterWithholding(models.TransientModel):
    _name = 'account.payment.register.withholding'
    _description = 'Payment Register Withholding Line'

    payment_register_id = fields.Many2one('account.payment.register', required=True, ondelete='cascade')
    tax_type = fields.Selection([
        ('2', '2%'),
        ('3', '3%'),
        ('30', '30%'),
    ], string='Withholding Tax Types', required=True)
    reference = fields.Char(string='Reference')
    date = fields.Date(string='Date', default=fields.Date.context_today)
    before_value = fields.Monetary(string='Before Value', currency_field='currency_id')
    withholding_amount = fields.Monetary(string='Withholding Amount', currency_field='currency_id', compute='_compute_withholding_amount', store=True, readonly=False)
    currency_id = fields.Many2one('res.currency', related='payment_register_id.currency_id')
    withholding_account_id = fields.Many2one('account.account', string="Withholding Account", required=True,
        domain="[('company_ids', 'in', [company_id])]")
    company_id = fields.Many2one(related='payment_register_id.company_id')

    @api.onchange('tax_type')
    def _onchange_tax_type_default_amount(self):
        # Default the before_value from the full original invoice amount
        for rec in self:
            if not rec.before_value and rec.payment_register_id:
                active_model = self.env.context.get('active_model')
                active_ids = self.env.context.get('active_ids', [])
                
                moves = rec.payment_register_id.line_ids.mapped('move_id')
                if not moves and active_model == 'account.move':
                    moves = self.env['account.move'].browse(active_ids)
                elif not moves and active_model == 'account.move.line':
                    moves = self.env['account.move.line'].browse(active_ids).mapped('move_id')
                
                if moves:
                    rec.before_value = sum(moves.mapped('amount_total'))
                else:
                    rec.before_value = rec.payment_register_id.source_amount

    @api.depends('before_value', 'tax_type')
    def _compute_withholding_amount(self):
        for rec in self:
            if rec.before_value and rec.tax_type:
                percentage = float(rec.tax_type) / 100.0
                rec.withholding_amount = rec.before_value * percentage
            else:
                rec.withholding_amount = 0.0


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    apply_withholding_tax = fields.Boolean(string="Apply Withholding Tax", default=False)
    
    withholding_line_ids = fields.One2many(
        'account.payment.register.withholding',
        'payment_register_id',
        string="Withholding Lines"
    )

    @api.constrains('apply_withholding_tax')
    def _check_apply_withholding_tax_validation(self):
        for record in self:
            if record.apply_withholding_tax:
                moves = record.line_ids.mapped('move_id')
                if not moves and self.env.context.get('active_model') == 'account.move':
                    moves = self.env['account.move'].browse(self.env.context.get('active_ids', []))
                elif not moves and self.env.context.get('active_model') == 'account.move.line':
                    moves = self.env['account.move.line'].browse(self.env.context.get('active_ids', [])).mapped('move_id')
                
                for move in moves:
                    has_wh = getattr(move, 'has_negative_tax', False) or getattr(move, 'withholding_amount', 0.0) > 0 or getattr(move, 'has_payment_wht', False) or getattr(move, 'withholding_invoice', False)
                    if not has_wh:
                        for line in move.invoice_line_ids:
                            for tax in line.tax_ids:
                                if tax.amount < 0 or 'WH' in tax.name or 'Withholding' in tax.name:
                                    has_wh = True
                                    break
                    if has_wh:
                        raise UserError(_("The invoice %s already has a withholding tax applied. Applying it again will cause double entry validation.") % move.name)

    @api.onchange('apply_withholding_tax')
    def _onchange_apply_withholding_tax_validation(self):
        if self.apply_withholding_tax:
            moves = self.line_ids.mapped('move_id')
            if not moves and self.env.context.get('active_model') == 'account.move':
                moves = self.env['account.move'].browse(self.env.context.get('active_ids', []))
            elif not moves and self.env.context.get('active_model') == 'account.move.line':
                moves = self.env['account.move.line'].browse(self.env.context.get('active_ids', [])).mapped('move_id')
            
            for move in moves:
                has_wh = getattr(move, 'has_negative_tax', False) or getattr(move, 'withholding_amount', 0.0) > 0 or getattr(move, 'has_payment_wht', False) or getattr(move, 'withholding_invoice', False)
                if not has_wh:
                    for line in move.invoice_line_ids:
                        for tax in line.tax_ids:
                            if tax.amount < 0 or 'WH' in tax.name or 'Withholding' in tax.name:
                                has_wh = True
                                break
                
                if has_wh:
                    self.apply_withholding_tax = False
                    return {
                        'warning': {
                            'title': _("Invalid Operation"),
                            'message': _("The invoice %s already has a withholding tax applied. Applying it again will cause double entry validation.") % move.name
                        }
                    }

    @api.onchange('withholding_line_ids')
    def _onchange_withholding_tax(self):
        # Adjust payment amount dynamically if withholding changes
        total_withholding = sum(self.withholding_line_ids.mapped('withholding_amount'))
        self.amount = self.source_amount - total_withholding

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        
        if self.withholding_line_ids:
            refs = [line.reference for line in self.withholding_line_ids if line.reference]
            if refs:
                payment_vals['withholding_certificate_no'] = ', '.join(refs)

            if 'write_off_line_vals' not in payment_vals:
                payment_vals['write_off_line_vals'] = []

            for line in self.withholding_line_ids:
                if line.withholding_amount > 0 and line.withholding_account_id:
                    conversion_rate = self.env['res.currency']._get_conversion_rate(
                        self.currency_id,
                        self.company_id.currency_id,
                        self.company_id,
                        self.payment_date,
                    )
                    
                    if self.payment_type == 'inbound':
                        write_off_amount_currency = line.withholding_amount
                    else:
                        write_off_amount_currency = -line.withholding_amount

                    write_off_balance = self.company_id.currency_id.round(write_off_amount_currency * conversion_rate)
                    label_prefix = _("Withholding Tax")
                    if line.reference:
                        writeoff_label = f"{label_prefix} {line.tax_type}% (Ref: {line.reference})"
                    else:
                        writeoff_label = f"{label_prefix} {line.tax_type}%"

                    payment_vals['write_off_line_vals'].append({
                        'name': writeoff_label,
                        'account_id': line.withholding_account_id.id,
                        'partner_id': self.partner_id.id,
                        'currency_id': self.currency_id.id,
                        'amount_currency': write_off_amount_currency,
                        'balance': write_off_balance,
                        'company_id': self.company_id.id,
                    })
        return payment_vals
