from odoo import models, fields, api,_
from odoo.exceptions import UserError
from num2words import num2words
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    sale_type = fields.Selection(
        selection=[('cash', 'Cash'),
                   ('credit', 'Credit')],
        string='Sale Type', default='cash',
        help='Indicates whether the invoice is for cash or credit sales.')
    fs_no = fields.Char(string='Fs No.')
    machine_id = fields.Char(string='Machine ID')
    show_stamp_signature = fields.Boolean(string="Show Stamp/Signature", default=False, help="Check to show the signature stamp on this specific invoice printout.")
    order_no = fields.Char(string='Order No.', compute='_compute_order_no', store=True)
    payment_term = fields.Char(string='Payment Term', help='Payment terms for the invoice (e.g., 2 Months).')
    amount_in_words = fields.Char(string='Total Amount in Words', compute='_compute_amount_in_words', store=True,
                                  help='Total amount in words.')
    memo_note = fields.Text(string='Memo/Note', help='Additional notes or memo for the invoice.')
    prepared_by = fields.Char(string='Prepared By', help='Name of the person who prepared the invoice.')
    checked_by = fields.Char(string='Checked By', help='Name of the person who checked the invoice.')
    approved_by = fields.Char(string='Approved By', help='Name of the person who approved the invoice.')
    received_by = fields.Char(string='Received By', help='Name of the person who received the goods/services.')

    daily_sales_amount = fields.Monetary(string='Daily Sales Amount', currency_field='currency_id',compute='_compute_daily_sales_amount', store=True)
    # Custom fields for List View
    city = fields.Char(string='City Name', related='partner_id.city', store=True, readonly=True)
    state_id = fields.Many2one('res.country.state', string='Region', related='partner_id.state_id', store=True, readonly=True)
    category_id = fields.Many2many('res.partner.category', string='Customer Tag', related='partner_id.category_id', readonly=True)
    stock_move_ref = fields.Char(string='Stock Movement') # Placeholder for Stock M...
    stock_valuation = fields.Float(string='Stock Valuation') # Placeholder for Stock Valuat...
    tin_no = fields.Char(string='Tin No', related='partner_id.vat', readonly=False, store=True)
    sales_cost = fields.Float(string='Sales Cost')
    core_amount = fields.Monetary(string='Core Amount', currency_field='currency_id')
    non_core_amount = fields.Monetary(string='Non-core Amount', currency_field='currency_id')
    total_in_birr = fields.Monetary(string='Total in Birr', currency_field='currency_id') # Usually बिर on screenshot
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now)

    crv_line_ids = fields.One2many('account.move.crv', 'move_id', string='CRV Lines')
    withholding_line_ids = fields.One2many('account.move.withholding', 'move_id_wh', string='Withholding Lines')
    picking_ids = fields.Many2many('stock.picking', string='Related Pickings', compute='_compute_picking_ids', help='Pickings related to this invoice via sales orders.')
    card_no = fields.Char(string='Card No')
    delivery_purpose = fields.Char(string='Purpose')
    received_name = fields.Char(string='Name')
    #transaction_type = fields.Many2one('transaction.type', string='Transaction Type')
    #transaction_no = fields.Char(string='Transaction No')
    withholding_invoice = fields.Boolean(string='Withholding Invoice', default=False)
    withholding_invoice_provided = fields.Boolean(string='Withholding Invoice Provided', default=False)
    withholding_no = fields.Char(string='Withholding No')
    withholding_internal_ref = fields.Char(string='Withholding Internal Ref', readonly=True, copy=False)
    withholding_amount = fields.Monetary(string='Withholding Amount', currency_field='currency_id',
                                         compute='_compute_withholding_amount', store=True)

    #@api.model
    #def create(self, vals):
     #   """Handle transaction number generation for new records"""
      #  if vals.get('transaction_no') == 'New':
       #     vals['transaction_no'] = self.env['ir.sequence'].next_by_code('account.move.transaction') or 'New'
        #return super(AccountMove, self).create(vals)

    has_negative_tax = fields.Boolean(
        string="Has Negative Tax",
        compute="_compute_has_negative_tax",
        store=True,
        help="Indicates if the invoice has negative tax amounts (withholding tax)"
    )

    has_payment_wht = fields.Boolean(
        string="WHT via Payment",
        compute="_compute_wht_followup_fields",
        store=True,
        help="Indicates if any payment reconciled with this invoice has a withholding certificate."
    )
    payment_wht_cert_no = fields.Char(
        string="Payment WHT Reference No.",
        compute="_compute_wht_followup_fields",
        store=True,
        help="Withholding certificate numbers from reconciled payments."
    )
    paid_amount_calculated = fields.Monetary(
        string="Paid Amount",
        currency_field='currency_id',
        compute="_compute_wht_followup_fields",
        store=True,
        help="Calculated paid amount (amount_total - amount_residual)."
    )
    wht_total_amount = fields.Monetary(
        string="WHT Amount",
        currency_field='currency_id',
        compute="_compute_wht_followup_fields",
        store=True,
        help="Total withholding amount (invoice level + payment level)."
    )

    @api.depends('line_ids.tax_ids', 'line_ids.price_subtotal')
    def _compute_has_negative_tax(self):
        for move in self:
            has_negative = False
            # Check all invoice lines for negative tax amounts
            for line in move.invoice_line_ids:
                # Get the computed tax amount for this line
                tax_amount = 0.0
                if line.tax_ids:
                    # Calculate tax amount based on line price and taxes
                    taxes = line.tax_ids.compute_all(
                        line.price_subtotal,
                        line.currency_id or move.currency_id,
                        line.quantity,
                        line.product_id,
                        move.partner_id
                    )
                    # Check if any tax is negative (withholding)
                    for tax in taxes.get('taxes', []):
                        if tax.get('amount', 0) < 0:
                            has_negative = True
                            break
                    if has_negative:
                        break

            move.has_negative_tax = has_negative

    @api.depends('amount_total', 'amount_residual', 'payment_state', 
                 'line_ids.matched_credit_ids.credit_move_id.payment_id', 
                 'line_ids.matched_debit_ids.debit_move_id.payment_id', 
                 'withholding_line_ids.withholding_amount', 'has_negative_tax')
    def _compute_wht_followup_fields(self):
        for move in self:
            # 1. paid_amount_calculated
            move.paid_amount_calculated = move.amount_total - move.amount_residual

            # 2. Extract reconciled payments
            payments = move.env['account.payment']
            try:
                payments = move._get_reconciled_payments()
            except Exception:
                pass

            # 3. has_payment_wht & payment_wht_cert_no
            wht_payments = payments.filtered(lambda p: getattr(p, 'withholding_certificate_no', False))
            move.has_payment_wht = bool(wht_payments)
            
            cert_nos = []
            for p in wht_payments:
                if p.withholding_certificate_no:
                    cert_nos.append(p.withholding_certificate_no)
            move.payment_wht_cert_no = ", ".join(cert_nos) if cert_nos else False

            # 4. wht_total_amount
            # Start with invoice-level withholding
            invoice_wht = 0.0
            if move.has_negative_tax:
                # Calculate negative tax amount (withholding tax)
                for line in move.invoice_line_ids:
                    if line.tax_ids:
                        taxes = line.tax_ids.compute_all(
                            line.price_subtotal,
                            line.currency_id or move.currency_id,
                            line.quantity,
                            line.product_id,
                            move.partner_id
                        )
                        for tax in taxes.get('taxes', []):
                            if tax.get('amount', 0) < 0:
                                invoice_wht += abs(tax.get('amount', 0))
            
            # Also add withholding amount from withholding lines if any
            if move.withholding_line_ids:
                invoice_wht += sum(move.withholding_line_ids.mapped('withholding_amount'))

            # Payment-level withholding
            payment_wht = 0.0
            for payment in wht_payments:
                # Find write-off lines starting with "Withholding Tax"
                for line in payment.move_id.line_ids:
                    if line.name and line.name.startswith("Withholding Tax"):
                        payment_wht += abs(line.amount_currency) if line.currency_id == move.currency_id else abs(line.balance)

            move.wht_total_amount = invoice_wht + payment_wht




    @api.depends('line_ids.withholding_amount')
    def _compute_withholding_amount(self):
        """Compute total withholding amount from lines"""
        for move in self:
            move.withholding_amount = sum(
                move.line_ids.filtered(lambda l: l.withholding_amount).mapped('withholding_amount'))

    def generate_withholding_ref(self):
        """Generate withholding reference for customer invoices"""
        for move in self:
            if move.move_type != 'out_invoice':
                raise UserError(_('Withholding Ref can only be generated for customer invoices.'))

            if move.withholding_internal_ref:
                raise UserError(_('Withholding Ref already generated for this invoice.'))

            # Generate withholding reference
            withholding_ref = self.env['ir.sequence'].next_by_code('withholding.reference') or 'WH/New'

            # Create withholding record in account.move.withholding model
            withholding_vals = {
                'move_id_wh': move.id,
                'reference': withholding_ref,
                'date': fields.Date.today(),
                'before_value': move.amount_untaxed,
                'entry_id': move.id,
            }

            withholding_record = self.env['account.move.withholding'].create(withholding_vals)

            # Update the invoice with withholding reference
            move.write({
                'withholding_internal_ref': withholding_ref,
                'withholding_no': withholding_ref
            })

        return True

    def _create_withholding_journal_entry(self):
        """Create journal entry for withholding on individual invoice"""
        for move in self:
            if not move.withholding_amount or move.withholding_amount <= 0:
                return

            # Create withholding line on the same invoice
            withholding_account = self.env['account.account'].search([
                ('code', '=', '116002'),  # Withholding Tax Receivables-Clients
                ('company_id', '=', move.company_id.id)
            ], limit=1)

            if not withholding_account:
                raise UserError(_('Withholding account (116002) not found.'))

            # Add withholding line to the invoice
            move.write({
                'line_ids': [(0, 0, {
                    'name': _('Withholding Tax'),
                    'account_id': withholding_account.id,
                    'partner_id': move.partner_id.id,
                    'debit': move.withholding_amount,
                    'credit': 0.00,
                    'withholding_amount': move.withholding_amount,
                    'withholding_ref': move.withholding_internal_ref,
                })]
            })

            # Adjust the original invoice line to reduce by withholding amount
            # Find the main invoice line (Trade Debtors)
            trade_debtor_account = self.env['account.account'].search([
                ('code', '=', '114001'),  # Trade Debtors
                ('company_id', '=', move.company_id.id)
            ], limit=1)

            if trade_debtor_account:
                # Add contra entry for withholding
                move.write({
                    'line_ids': [(0, 0, {
                        'name': _('Withholding Adjustment'),
                        'account_id': trade_debtor_account.id,
                        'partner_id': move.partner_id.id,
                        'debit': 0.00,
                        'credit': move.withholding_amount,
                        'withholding_amount': move.withholding_amount,
                        'withholding_ref': move.withholding_internal_ref,
                    })]
                })

    def update_accounting_date(self):
        """Update accounting date for the invoice"""
        for move in self:
            # Open wizard to update accounting date
            return {
                'name': _('Update Accounting Date'),
                'type': 'ir.actions.act_window',
                'res_model': 'update.accounting.date.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_move_id': move.id}
            }

    @api.depends('invoice_line_ids.sale_line_ids.order_id.picking_ids', 'invoice_line_ids.purchase_line_id.order_id.picking_ids')
    def _compute_picking_ids(self):
        for move in self:
            sale_orders = move.invoice_line_ids.mapped('sale_line_ids.order_id')
            purchase_orders = move.invoice_line_ids.mapped('purchase_line_id.order_id')
            move.picking_ids = sale_orders.mapped('picking_ids') | purchase_orders.mapped('picking_ids')

    @api.depends('invoice_line_ids.sale_line_ids.order_id')
    def _compute_order_no(self):
        for invoice in self:
            # Get sales orders linked via invoice lines
            sale_orders = invoice.invoice_line_ids.mapped('sale_line_ids.order_id')
            if sale_orders:
                # Concatenate sales order names (e.g., "SOD-25-164511, SOD-25-164512")
                invoice.order_no = ', '.join(sale_orders.mapped('name'))
            else:
                invoice.order_no = ''

    @api.depends('invoice_date', 'amount_total')
    def _compute_daily_sales_amount(self):
        for invoice in self:
            if invoice.invoice_date:
                # Sum amount_total for all invoices on the same date
                daily_invoices = self.env['account.move'].search([
                    ('invoice_date', '=', invoice.invoice_date),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '=', 'posted')
                ])
                invoice.daily_sales_amount = sum(daily_invoices.mapped('amount_total'))
            else:
                invoice.daily_sales_amount = 0.0

    def action_print_invoice(self):
        """Action to trigger the custom invoice report."""
        if self.state != 'posted':
            raise UserError('You can only print invoices in the Posted state.')
        return self.env.ref('Yohannes_sales_person_target_management.action_report_invoice_custom').report_action(self)

    @api.depends('amount_total', 'currency_id')
    def _compute_amount_in_words(self):
        for invoice in self:
            if invoice.amount_total:
                invoice.amount_in_words = num2words(
                    invoice.amount_total, lang='en'
                ).replace(' and ', ' ').title() + ' ' + invoice.currency_id.name
            else:
                invoice.amount_in_words = ''



    # Tracking fields for Payment Followup Report
    payment_followup_paid_date = fields.Date(string='Paid Date', compute='_compute_payment_followup_fields', store=True)
    payment_followup_paid_amount = fields.Monetary(string='Paid Amount', currency_field='currency_id', compute='_compute_payment_followup_fields', store=True)
    payment_followup_settled_amount = fields.Monetary(string='Settled Amount', currency_field='currency_id', compute='_compute_payment_followup_fields', store=True)
    payment_followup_due_days = fields.Integer(string='Due Days', compute='_compute_payment_followup_fields', store=True)

    @api.depends('amount_total', 'amount_residual', 'invoice_date_due', 'payment_state', 'line_ids.matched_credit_ids', 'line_ids.matched_debit_ids', 'withholding_line_ids.withholding_amount')
    def _compute_payment_followup_fields(self):
        for move in self:
            due_days = 0
            if move.invoice_date_due and move.amount_residual > 0:
                delta = fields.Date.today() - move.invoice_date_due
                due_days = max(0, delta.days)
            move.payment_followup_due_days = due_days

            cleared_amount = move.amount_total - move.amount_residual
            withheld_amount = sum(move.withholding_line_ids.mapped('withholding_amount')) if hasattr(move, 'withholding_line_ids') else 0
            move.payment_followup_paid_amount = cleared_amount
            move.payment_followup_settled_amount = withheld_amount or cleared_amount

            paid_date = False
            if move.payment_state in ('paid', 'in_payment', 'partial'):
                try:
                    payments = move._get_reconciled_payments()
                    if payments:
                        paid_date = max(payments.mapped('date'))
                except Exception:
                    pass
                if not paid_date:
                    reconciled_lines = move.line_ids.filtered(lambda l: l.account_type == 'asset_receivable').mapped('matched_credit_ids.credit_move_id')
                    if reconciled_lines:
                        paid_date = max(reconciled_lines.mapped('date'))
            move.payment_followup_paid_date = paid_date or move.invoice_date

class AccountMoveCrv(models.Model):
    _name = 'account.move.crv'
    _description = 'Invoice CRV Line'

    move_id = fields.Many2one('account.move', string='Invoice', ondelete='cascade')
    crv_reference = fields.Char(string='CRV Reference')
    amount = fields.Monetary(string='Amount', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='move_id.currency_id')
    payment_description = fields.Char(string='Payment Description')
    document_printed = fields.Boolean(string='Document Printed')
    amount_word = fields.Char(string='Amount Word', compute='_compute_amount_word', store=True)

    @api.depends('amount', 'currency_id')
    def _compute_amount_word(self):
        for rec in self:
            if rec.amount:
                rec.amount_word = num2words(
                    rec.amount, lang='en'
                ).replace(' and ', ' ').title() + ' ' + (rec.currency_id.name or '')
            else:
                rec.amount_word = ''

    def action_print_crv(self):
        """Action to trigger the CRV report."""
        for rec in self:
            if rec.move_id.move_type not in ['out_invoice', 'out_refund']:
                raise UserError(_('CRV can only be printed for customer invoices/credit notes.'))

        return self.env.ref('Yohannes_sales_person_target_management.action_report_crv').report_action(self.move_id)

class AccountMoveWithholding(models.Model):
    _name = 'account.move.withholding'
    _description = 'Invoice Withholding Line'

    #move_id = fields.Many2one('account.move', string='Invoice', ondelete='cascade')
    move_id_wh = fields.Many2one('account.move', string='Invoice', required=True, ondelete='cascade')
    tax_type = fields.Selection([
        ('2', '2%'),
        ('3', '3%'),
        ('30', '30%'),
    ], string='Withholding Tax Types')
    reference = fields.Char(string='Reference')
    tax_amount = fields.Monetary(string='Tax Amount', currency_field='currency_id')
    date = fields.Date(string='Date')
    before_value = fields.Monetary(string='Before Value', currency_field='currency_id')
    withholding_amount = fields.Monetary(string='Withholding Amount', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='move_id_wh.currency_id')
    entry_id = fields.Many2one('account.move', string='Entry')
    amount_in_words = fields.Char(string='Amount in Words', compute='_compute_amount_in_words')

    @api.depends('before_value', 'currency_id')
    def _compute_amount_in_words(self):
        for rec in self:
            if rec.before_value:
                rec.amount_in_words = num2words(
                    rec.before_value, lang='en'
                ).replace(' and ', ' ').title() + ' ' + (rec.currency_id.name or '')
            else:
                rec.amount_in_words = ''

    def create_withholding_entry(self):
        """Create accounting entry for this withholding record individually"""
        for withholding in self:
            if withholding.entry_id:
                continue  # Skip if entry already exists

            # Get the parent invoice/account move
            parent_move_obj = withholding.move_id_wh

            # Determine accounts based on invoice type
            if parent_move_obj and parent_move_obj.move_type in ('in_invoice', 'in_refund', 'in_receipt'):
                # Vendor Bill: Withholding Tax is a liability
                tax_account = self.env['account.account'].search([('code', '=', '216001')], limit=1)
                counterpart_account = parent_move_obj.partner_id.property_account_payable_id
                debit_val = 0.0
                credit_val = withholding.withholding_amount
                cp_debit_val = withholding.withholding_amount
                cp_credit_val = 0.0
            else:
                # Customer Invoice: Withholding Tax is an asset
                tax_account = self.env['account.account'].search([('code', '=', '116002')], limit=1)
                counterpart_account = parent_move_obj.partner_id.property_account_receivable_id if parent_move_obj else self._get_withholding_payable_account()
                debit_val = withholding.withholding_amount
                credit_val = 0.0
                cp_debit_val = 0.0
                cp_credit_val = withholding.withholding_amount

            # Create withholding journal entry
            move_vals = {
                'move_type': 'entry',  # or 'withholding' depending on your setup
                'date': withholding.date or fields.Date.context_today(withholding),
                'partner_id': parent_move_obj.partner_id.id if parent_move_obj else False,
                'journal_id': self._get_withholding_journal().id,
                'line_ids': [
                    (0, 0, {
                        'name': f'Withholding Tax - {withholding.reference or parent_move_obj.name or ""}',
                        'account_id': tax_account.id if tax_account else counterpart_account.id,
                        'debit': debit_val,
                        'credit': credit_val,
                        'partner_id': parent_move_obj.partner_id.id if parent_move_obj else False,
                    }),
                    (0, 0, {
                        'name': f'Trade Settlement - {withholding.reference or parent_move_obj.name or ""}',
                        'account_id': counterpart_account.id if counterpart_account else tax_account.id,
                        'debit': cp_debit_val,
                        'credit': cp_credit_val,
                        'partner_id': parent_move_obj.partner_id.id if parent_move_obj else False,
                    }),
                ],
                'ref': f'WH-{withholding.reference or withholding.id}',
            }

            # Create the move
            move = self.env['account.move'].create(move_vals)

            # Link the withholding to the created entry
            withholding.entry_id = move.id

        return {
            'type': 'ir.actions.act_window',
            'name': 'Withholding Entry',
            'res_model': 'account.move',
            'res_id': withholding.entry_id.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_move_type': 'entry'},
        }

    def action_view_entry(self):
        """View the created journal entry"""
        self.ensure_one()
        if self.entry_id:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Journal Entry',
                'res_model': 'account.move',
                'res_id': self.entry_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def _get_withholding_journal(self):
        """Get the withholding journal"""
        journal = self.env['account.journal'].search([
            ('code', '=', 'WH'),
            ('type', '=', 'general')
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].create({
                'name': 'Withholding Journal',
                'code': 'WH',
                'type': 'general',
            })
        return journal

    def _get_withholding_account(self):
        """Get withholding receivable account"""
        # Get the account from settings or configuration
        account = self.env['account.account'].search([
            ('code', '=', '116002')  # Based on your screenshot: Withholding Tax Receivables-Clients
        ], limit=1)
        return account

    def _get_withholding_payable_account(self):
        """Get withholding payable account"""
        account = self.env['account.account'].search([
            ('code', '=', '216001')  # Withholding Tax Payable account
        ], limit=1)
        return account
    def action_report(self):
        """Action to trigger the withholding report."""
        return self.env.ref('Yohannes_sales_person_target_management.action_report_withholding').report_action(self)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    #lot_id = fields.Many2one('stock.lot', string='Lot/Serial Number', domain="[('product_id', '=', product_id)]",
           #                  help='Lot/Serial number associated with the product.')
    #expiration_date = fields.Datetime(string='Expiration Date', related='lot_id.expiration_date', store=True,
            #                          help='Expiration date of the lot/serial number.')
    
    withholding_amount = fields.Float(string='Withholding Amount')
    withholding_ref = fields.Char(string='Withholding Reference')


class TransactionType(models.Model):
    _name = 'transaction.type'
    _description = 'Transaction Type'
    _order = 'short_code, name'
    _rec_name = 'name'

    name = fields.Char(string='Transaction Type', required=True, translate=True)
    short_code = fields.Char(string='Short Code', required=True,)
    assignment = fields.Selection([
        ('automatic', 'Automatic'),
        ('manual', 'Manual'),
    ], string='Assignment', required=True)

    # Posting Configuration
    sequence_ids = fields.One2many('transaction.type.sequence', 'transaction_type_id',string='Fiscal Year Sequences')
    company_id = fields.Many2one('res.company', string='Company',default=lambda self: self.env.company)
    active = fields.Boolean(string='Active', default=True)
    description = fields.Text(string='Description')
    payment_method = fields.Selection([
        ('bank', 'Bank'),
        ('cash', 'Cash'),
        ('miscellaneous', 'Miscellaneous'),
    ], string='Payment Method')
    transaction_type = fields.Selection([
        ('payment', 'Payment'),
        ('receipt', 'Receipt'),
        ('miscellaneous', 'Miscellaneous'),
    ], string='Transaction Type ')
    _sql_constraints = [
        ('short_code_uniq', 'unique(short_code, company_id)', 'Short Code must be unique per company!'),
        ('name_uniq', 'unique(name, company_id)', 'Transaction Type name must be unique per company!'),
    ]

    def name_get(self):
        """Display name with short code"""
        result = []
        for record in self:
            name = record.name
            if record.short_code:
                name = f"[{record.short_code}] {record.name}"
            result.append((record.id, name))
        return result

    @api.model
    def _get_next_sequence(self, short_code, fiscal_year=None):
        """Get next sequence number for transaction type"""
        domain = [('transaction_type_id.short_code', '=', short_code)]
        if fiscal_year:
            domain.append(('fiscal_year', '=', fiscal_year))
        sequence = self.env['transaction.type.sequence'].search(domain, limit=1)
        if sequence:
            return sequence.next_sequence_number()
        return False


class UpdateAccountingDateWizard(models.TransientModel):
    _name = 'update.accounting.date.wizard'
    _description = 'Update Accounting Date Wizard'

    move_id = fields.Many2one('account.move', string='Invoice', required=True)
    accounting_date = fields.Date(string='New Accounting Date', required=True, default=fields.Date.context_today)

    def action_update_date(self):
        for wizard in self:
            if wizard.move_id and wizard.move_id.state == 'draft':
                wizard.move_id.write({'date': wizard.accounting_date})
            elif wizard.move_id:
                try:
                    wizard.move_id.button_draft()
                    wizard.move_id.write({'date': wizard.accounting_date})
                    wizard.move_id.action_post()
                except Exception as e:
                    raise UserError(str(e))



class TransactionTypeSequence(models.Model):
    _name = 'transaction.type.sequence'
    _description = 'Transaction Type Sequence'
    _order = 'fiscal_year desc'

    # Relationship
    transaction_type_id = fields.Many2one('transaction.type', string='Transaction Type', required=True, ondelete='cascade')
    fiscal_year = fields.Char(string='Fiscal Year', required=True,
                              help='Fiscal year label, e.g. 2024/2025')
    sequence_name = fields.Many2one('ir.sequence', string='Sequence Name', required=True)

