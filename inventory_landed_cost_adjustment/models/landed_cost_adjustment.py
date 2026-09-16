# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockLandedCostAdjustment(models.Model):
    """
    Landed Cost Retroactive Adjustment

    Allows posting additional valuation and COGS adjustment journal entries
    when extra landed costs are identified after a receipt has been validated.
    Must be used while the fiscal year is still open.

    Two journal entries are created:

      1. Additional Valuation Entry  (for the source receipt)
            DR  Stock Valuation Account
            CR  Stock Variation Account

      2. COGS Adjustment Entry  (for ALL fiscal-year sales of these products,
                                  across ALL receipts/batches — not just this one)
            DR  COGS / Expense Account
            CR  Stock Valuation Account
    """
    _name = 'stock.landed.cost.adjustment'
    _description = 'Landed Cost Retroactive Adjustment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        readonly=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)

    # ── Source & Date ─────────────────────────────────────────────────────────
    date = fields.Date(
        string='Adjustment Date',
        required=True,
        default=fields.Date.context_today,
        readonly=True,
        states={'draft': [('readonly', False)]},
        tracking=True,
    )
    picking_id = fields.Many2one(
        'stock.picking',
        string='Source Receipt',
        required=True,
        domain=[('picking_type_code', '=', 'incoming'), ('state', '=', 'done')],
        readonly=True,
        states={'draft': [('readonly', False)]},
        tracking=True,
        help="The validated receipt whose products carry additional landed costs.",
    )

    # ── Fiscal Year ───────────────────────────────────────────────────────────
    fiscal_year_id = fields.Many2one(
        'account.fiscal.year',
        string='Fiscal Year',
        compute='_compute_fiscal_year',
        store=True,
    )
    fiscal_year_is_open = fields.Boolean(
        string='Fiscal Year Is Open',
        compute='_compute_fiscal_year',
        store=True,
    )

    # ── Lines & Notes ─────────────────────────────────────────────────────────
    line_ids = fields.One2many(
        'stock.landed.cost.adjustment.line',
        'adjustment_id',
        string='Product Adjustment Lines',
        readonly=True,
        states={'draft': [('readonly', False)]},
        copy=True,
    )
    note = fields.Text(string='Internal Notes')

    # ── Resulting Journal Entries ─────────────────────────────────────────────
    valuation_move_id = fields.Many2one(
        'account.move',
        string='Additional Valuation Entry',
        copy=False,
        readonly=True,
    )
    cogs_move_id = fields.Many2one(
        'account.move',
        string='COGS Adjustment Entry',
        copy=False,
        readonly=True,
    )

    # ── Summary Totals ────────────────────────────────────────────────────────
    total_additional_cost = fields.Monetary(
        string='Total Additional Cost',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_cogs_adjustment = fields.Monetary(
        string='Total COGS Adjustment',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_remaining_stock_value = fields.Monetary(
        string='Remaining in Stock Valuation',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
        help="Portion of the additional cost that stays in inventory (unsold units).",
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )

    # ── Fiscal Year Compute ───────────────────────────────────────────────────
    @api.depends('date', 'company_id')
    def _compute_fiscal_year(self):
        FiscalYear = self.env['account.fiscal.year']
        today = fields.Date.context_today(self)
        for rec in self:
            check_date = rec.date or today
            fy = FiscalYear.search([
                ('company_id', '=', rec.company_id.id),
                ('date_from', '<=', check_date),
                ('date_to', '>=', check_date),
            ], limit=1)
            rec.fiscal_year_id = fy
            # Fiscal year is "open" if its end date has not yet passed
            rec.fiscal_year_is_open = bool(fy) and fy.date_to >= today

    # ── Summary Totals Compute ────────────────────────────────────────────────
    @api.depends('line_ids.additional_cost', 'line_ids.cogs_adjustment_amount')
    def _compute_totals(self):
        for rec in self:
            total_add = sum(rec.line_ids.mapped('additional_cost'))
            total_cogs = sum(rec.line_ids.mapped('cogs_adjustment_amount'))
            rec.total_additional_cost = total_add
            rec.total_cogs_adjustment = total_cogs
            rec.total_remaining_stock_value = total_add - total_cogs

    # ── ORM Overrides ─────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('stock.landed.cost.adjustment')
                    or 'New'
                )
        return super().create(vals_list)

    # ── Actions / Buttons ─────────────────────────────────────────────────────
    def action_load_receipt_products(self):
        """
        Populate lines from the validated receipt moves.
        Consolidates multiple moves for the same product into a single line.
        Sold quantities are refreshed automatically after loading.
        """
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_("Please select a Source Receipt first."))
        if self.state != 'draft':
            raise UserError(_("You can only load products in Draft state."))

        self.line_ids.unlink()

        product_data = {}
        for move in self.picking_id.move_ids.filtered(lambda m: m.state == 'done'):
            pid = move.product_id.id
            if pid not in product_data:
                product_data[pid] = {
                    'product_id': pid,
                    'received_qty': 0.0,
                    'additional_cost': 0.0,
                }
            product_data[pid]['received_qty'] += move.product_uom_qty

        if not product_data:
            raise UserError(_(
                "No done stock moves found on receipt '%s'."
            ) % self.picking_id.name)

        self.write({
            'line_ids': [(0, 0, vals) for vals in product_data.values()],
        })
        # Immediately compute sold quantities so the user sees real numbers
        self.action_refresh_sold_quantities()
        return True

    def action_refresh_sold_quantities(self):
        """
        Recompute total_sold_qty on all lines by scanning ALL outgoing stock
        moves for each product within the open fiscal year — regardless of
        which receipt/batch originated the inventory.
        """
        self.ensure_one()
        if not self.fiscal_year_id:
            raise UserError(_(
                "No fiscal year found for date %s. "
                "Please configure a fiscal year first."
            ) % self.date)
        for line in self.line_ids:
            line._refresh_sold_qty()
        return True

    def action_post(self):
        """
        Validate and post both journal entries:
          1. Additional Valuation (additional cost → inventory asset)
          2. COGS Adjustment (cost per unit × total sold qty, all batches)
        """
        self.ensure_one()
        self._check_fiscal_year_open()

        if not self.line_ids:
            raise UserError(_(
                "No adjustment lines found. "
                "Please click 'Load Receipt Products' first."
            ))
        if any(line.additional_cost <= 0.0 for line in self.line_ids):
            raise UserError(_(
                "All lines must have a positive 'Additional Landed Cost' amount."
            ))

        valuation_move = self._post_valuation_entry()
        cogs_move = self._post_cogs_entry()

        self.write({
            'state': 'posted',
            'valuation_move_id': valuation_move.id,
            'cogs_move_id': cogs_move.id if cogs_move else False,
        })

        cogs_name = cogs_move.name if cogs_move else _('N/A (no fiscal-year sales found)')
        self.message_post(body=_(
            "<b>Landed cost adjustment posted by %(user)s.</b><br/>"
            "Additional Valuation Entry: %(val)s<br/>"
            "COGS Adjustment Entry: %(cogs)s"
        ) % {
            'user': self.env.user.name,
            'val': valuation_move.name,
            'cogs': cogs_name,
        })

    def action_cancel(self):
        self.ensure_one()
        if self.state == 'posted':
            raise UserError(_(
                "A posted adjustment cannot be cancelled directly. "
                "Ask your accountant to reverse the journal entries manually, "
                "then reset this record to draft."
            ))
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.ensure_one()
        if self.state == 'posted':
            raise UserError(_("Posted adjustments cannot be reset to draft."))
        self.write({'state': 'draft'})

    def action_view_valuation_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Additional Valuation Entry'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.valuation_move_id.id,
        }

    def action_view_cogs_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('COGS Adjustment Entry'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.cogs_move_id.id,
        }

    # ── Private Helpers ───────────────────────────────────────────────────────
    def _check_fiscal_year_open(self):
        """Raise if no fiscal year found or the year has already closed."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        if not self.fiscal_year_id:
            raise UserError(_(
                "No active fiscal year found for date %s. "
                "Please configure a fiscal year in Accounting → Configuration."
            ) % self.date)
        if self.fiscal_year_id.date_to < today:
            raise UserError(_(
                "The fiscal year '%(fy)s' ended on %(end)s and is now closed. "
                "Retroactive landed cost adjustments can only be posted while "
                "the fiscal year is still open."
            ) % {
                'fy': self.fiscal_year_id.name,
                'end': self.fiscal_year_id.date_to,
            })

    def _get_stock_journal(self):
        """
        Return the stock journal to use:
          1. From the first product category that has one configured.
          2. Fall back to company-level stock journal.
        """
        for line in self.line_ids:
            journal = line.product_id.categ_id.property_stock_journal
            if journal:
                return journal
        journal = self.company_id.account_stock_journal_id
        if not journal:
            raise UserError(_(
                "No stock journal configured. Please set a Stock Journal on the "
                "product category or in Company accounting settings."
            ))
        return journal

    def _post_valuation_entry(self):
        """
        Post an ADDITIONAL (new) stock valuation journal entry.

        For each product line:
            DR  Stock Valuation Account   +additional_cost
            CR  Stock Variation Account   +additional_cost

        This is a *new* entry — the original receipt valuation is NOT touched.
        """
        aml_vals = []
        for line in self.line_ids:
            if line.additional_cost <= 0.0:
                continue
            categ = line.product_id.categ_id
            valuation_acc = categ.property_stock_valuation_account_id
            variation_acc = categ.account_stock_variation_id

            if not valuation_acc or not variation_acc:
                raise UserError(_(
                    "Product '%(prod)s' (category '%(cat)s') is missing the "
                    "Stock Valuation Account or Stock Variation Account. "
                    "Please configure both in the product category before posting."
                ) % {
                    'prod': line.product_id.display_name,
                    'cat': categ.name,
                })

            label = _(
                "Landed Cost Adj. [%(ref)s] – %(prod)s"
            ) % {'ref': self.name, 'prod': line.product_id.display_name}

            aml_vals += [
                # DR Stock Valuation (increase inventory asset)
                {
                    'account_id': valuation_acc.id,
                    'name': label,
                    'debit': line.additional_cost,
                    'credit': 0.0,
                    'product_id': line.product_id.id,
                },
                # CR Stock Variation / Landed Cost clearing
                {
                    'account_id': variation_acc.id,
                    'name': label,
                    'debit': 0.0,
                    'credit': line.additional_cost,
                    'product_id': line.product_id.id,
                },
            ]

        if not aml_vals:
            raise UserError(_("No valid lines found to generate a valuation entry."))

        journal = self._get_stock_journal()
        move = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': self.date,
            'ref': self.name,
            'narration': _(
                "Additional landed cost – Receipt: %(pick)s | Fiscal Year: %(fy)s"
            ) % {
                'pick': self.picking_id.name,
                'fy': self.fiscal_year_id.name if self.fiscal_year_id else '',
            },
            'line_ids': [(0, 0, v) for v in aml_vals],
        })
        move._post()
        _logger.info(
            "Landed cost adjustment %s: posted additional valuation entry %s",
            self.name, move.name,
        )
        return move

    def _post_cogs_entry(self):
        """
        Post a COGS adjustment journal entry.

        For each product, the COGS adjustment covers ALL outgoing deliveries
        (sales) of that product within the current fiscal year — across ALL
        receipts/batches, not just the one listed in picking_id.

        Formula per product:
            cost_per_unit        = additional_cost / received_qty
            total_sold_qty       = sum of all done outgoing moves in FY
            cogs_adjustment      = cost_per_unit × total_sold_qty
                                   (capped at additional_cost)

        Journal:
            DR  COGS / Expense Account    +cogs_adjustment_amount
            CR  Stock Valuation Account   +cogs_adjustment_amount
        """
        aml_vals = []
        for line in self.line_ids:
            if line.cogs_adjustment_amount <= 0.0:
                continue
            categ = line.product_id.categ_id
            valuation_acc = categ.property_stock_valuation_account_id
            expense_acc = categ.property_account_expense_categ_id

            if not valuation_acc or not expense_acc:
                _logger.warning(
                    "Skipping COGS adjustment for product '%s': "
                    "Stock Valuation Account or COGS Account not configured.",
                    line.product_id.display_name,
                )
                continue

            label = _(
                "COGS Adj. (Landed Cost) [%(ref)s] – %(prod)s (all FY sales)"
            ) % {'ref': self.name, 'prod': line.product_id.display_name}

            aml_vals += [
                # DR COGS / Expense (increase cost of goods sold)
                {
                    'account_id': expense_acc.id,
                    'name': label,
                    'debit': line.cogs_adjustment_amount,
                    'credit': 0.0,
                    'product_id': line.product_id.id,
                },
                # CR Stock Valuation (reduce inventory asset for sold portion)
                {
                    'account_id': valuation_acc.id,
                    'name': label,
                    'debit': 0.0,
                    'credit': line.cogs_adjustment_amount,
                    'product_id': line.product_id.id,
                },
            ]

        if not aml_vals:
            _logger.info(
                "Landed cost adjustment %s: no COGS adjustment needed "
                "(no fiscal-year sales found for any adjusted product).",
                self.name,
            )
            return self.env['account.move']

        journal = self._get_stock_journal()
        move = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': self.date,
            'ref': self.name,
            'narration': _(
                "COGS adjustment for all FY sales of landed-cost products "
                "| Adjustment: %(ref)s | Fiscal Year: %(fy)s"
            ) % {
                'ref': self.name,
                'fy': self.fiscal_year_id.name if self.fiscal_year_id else '',
            },
            'line_ids': [(0, 0, v) for v in aml_vals],
        })
        move._post()
        _logger.info(
            "Landed cost adjustment %s: posted COGS adjustment entry %s",
            self.name, move.name,
        )
        return move


# ══════════════════════════════════════════════════════════════════════════════

class StockLandedCostAdjustmentLine(models.Model):
    """
    One line per product inside a Landed Cost Retroactive Adjustment.

    Key fields set by the user:
      - additional_cost   : total additional landed cost for this product
                            on this receipt.

    Computed automatically:
      - cost_per_unit            : additional_cost / received_qty
      - total_sold_qty           : all outgoing stock moves in the fiscal year
                                   for this product (all batches/receipts)
      - cogs_adjustment_amount   : cost_per_unit × total_sold_qty
                                   (capped at additional_cost)
      - remaining_stock_adj      : additional_cost − cogs_adjustment_amount
    """
    _name = 'stock.landed.cost.adjustment.line'
    _description = 'Landed Cost Adjustment Line'

    adjustment_id = fields.Many2one(
        'stock.landed.cost.adjustment',
        string='Adjustment',
        ondelete='cascade',
        required=True,
        index=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain=[('is_storable', '=', True)],
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        related='product_id.uom_id',
        readonly=True,
    )

    # ── Receipt Data (set by action_load_receipt_products) ────────────────────
    received_qty = fields.Float(
        string='Qty Received (this receipt)',
        digits='Product Unit of Measure',
        help="Total quantity of this product received on the source receipt.",
    )

    # ── Cost Input (set by the accountant) ────────────────────────────────────
    additional_cost = fields.Float(
        string='Additional Landed Cost',
        digits='Product Price',
        help="Total extra cost attributed to this product on this receipt "
             "(e.g. freight, customs, insurance).",
    )

    # ── Derived Cost Per Unit ─────────────────────────────────────────────────
    cost_per_unit = fields.Float(
        string='Additional Cost / Unit',
        compute='_compute_cost_per_unit',
        store=True,
        digits='Product Price',
    )

    # ── Sold Qty (all FY deliveries, all batches) ─────────────────────────────
    total_sold_qty = fields.Float(
        string='Total Sold Qty (Fiscal Year, All Batches)',
        digits='Product Unit of Measure',
        readonly=True,
        help="Total quantity of this product sold through ALL deliveries in "
             "the current fiscal year — regardless of which receipt/batch "
             "the inventory came from. Refreshed by the 'Refresh Sold Qty' button.",
    )

    # ── Computed Adjustments ──────────────────────────────────────────────────
    cogs_adjustment_amount = fields.Float(
        string='COGS Adjustment Amount',
        compute='_compute_adjustments',
        store=True,
        digits='Product Price',
        help="= cost_per_unit × total_sold_qty  (capped at additional_cost).\n"
             "This amount is debited to COGS and credited to Stock Valuation.",
    )
    remaining_stock_adjustment = fields.Float(
        string='Remaining in Stock Valuation',
        compute='_compute_adjustments',
        store=True,
        digits='Product Price',
        help="= additional_cost − cogs_adjustment_amount.\n"
             "This portion stays in the inventory asset account (unsold stock).",
    )

    # ── Fiscal Year (read-only, from parent) ──────────────────────────────────
    fiscal_year_id = fields.Many2one(
        'account.fiscal.year',
        related='adjustment_id.fiscal_year_id',
        string='Fiscal Year',
        store=True,
        readonly=True,
    )

    # ── Computes ──────────────────────────────────────────────────────────────
    @api.depends('additional_cost', 'received_qty')
    def _compute_cost_per_unit(self):
        for line in self:
            if line.received_qty:
                line.cost_per_unit = line.additional_cost / line.received_qty
            else:
                line.cost_per_unit = 0.0

    @api.depends('cost_per_unit', 'total_sold_qty', 'additional_cost')
    def _compute_adjustments(self):
        for line in self:
            raw_cogs = line.cost_per_unit * line.total_sold_qty
            # COGS portion cannot exceed the total additional cost posted
            cogs = min(raw_cogs, line.additional_cost)
            line.cogs_adjustment_amount = cogs
            line.remaining_stock_adjustment = line.additional_cost - cogs

    # ── Sold Qty Refresh (called programmatically) ────────────────────────────
    def _refresh_sold_qty(self):
        """
        Scan ALL done outgoing stock moves for this product within the fiscal
        year dates and store the result in total_sold_qty.

        "Outgoing" is identified by the destination location being a customer
        location (usage = 'customer'), covering standard deliveries, dropships,
        consignment shipments, etc.
        """
        for line in self:
            fy = line.fiscal_year_id
            if not fy or not line.product_id:
                line.total_sold_qty = 0.0
                continue

            done_out_moves = self.env['stock.move'].search([
                ('product_id', '=', line.product_id.id),
                ('state', '=', 'done'),
                ('location_dest_id.usage', '=', 'customer'),
                ('date', '>=', fy.date_from),
                ('date', '<=', fy.date_to),
                ('company_id', '=', line.adjustment_id.company_id.id),
            ])
            line.total_sold_qty = sum(done_out_moves.mapped('product_uom_qty'))
