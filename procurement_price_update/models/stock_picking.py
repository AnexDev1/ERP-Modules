# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    price_update_line_ids = fields.One2many(
        'procurement.price.update.line',
        'picking_id',
        string='Price Update Lines',
        copy=False
    )
    prices_approved = fields.Boolean(string='Prices Approved', default=False, copy=False)

    def action_generate_price_lines(self):
        self.ensure_one()
        if self.picking_type_code != 'incoming':
            return
            
        po = self.purchase_id
        if not po:
            raise UserError(_("Cannot generate price update lines without an associated Purchase Order."))
            
        company_currency = self.company_id.currency_id
        po_currency = po.currency_id

        # Determine default margins based on PO type
        if po.request_type == 'local':
            wholesale_margin_percent = self.company_id.local_wholesale_margin
            retail_margin_percent = self.company_id.local_retail_margin
        elif po.request_type == 'foreign':
            wholesale_margin_percent = self.company_id.foreign_wholesale_margin
            retail_margin_percent = self.company_id.foreign_retail_margin
        else:
            wholesale_margin_percent = 0.0
            retail_margin_percent = 0.0

        # Remove existing lines to avoid duplicates
        self.price_update_line_ids.unlink()

        # Collect moves grouped by product to avoid duplicate price lines
        # (e.g. when a single product has multiple split moves on the same picking)
        product_data = {}  # product_id -> best cost_price
        for move in self.move_ids.filtered(lambda m: m.state not in ('draft', 'cancel')):
            po_line = po.order_line.filtered(lambda l: l.product_id == move.product_id)
            if not po_line:
                continue
            po_line = po_line[0]

            # Use the actual move's price_unit (reflects the real received cost, including
            # any adjustments). Fall back to PO line price if move price_unit is 0.
            raw_cost = move.price_unit if move.price_unit else po_line.price_unit

            # Convert price to company currency
            cost_price = raw_cost
            if po_currency != company_currency:
                cost_price = po_currency._convert(
                    raw_cost, company_currency, self.company_id, self.date_done or fields.Date.today()
                )

            pid = move.product_id.id
            # If the same product appears in multiple moves, keep the highest cost
            if pid not in product_data or cost_price > product_data[pid]['cost_price']:
                product_data[pid] = {
                    'product_id': pid,
                    'cost_price': cost_price,
                    'current_wholesale_price': move.product_id.wholesale_price,
                    'wholesale_margin_percent': wholesale_margin_percent,
                    'new_wholesale_price': cost_price * (1 + (wholesale_margin_percent / 100.0)),
                    'current_retail_price': move.product_id.retail_price,
                    'retail_margin_percent': retail_margin_percent,
                    'new_retail_price': cost_price * (1 + (retail_margin_percent / 100.0)),
                }

        lines = [(0, 0, vals) for vals in product_data.values()]
        if lines:
            self.write({'price_update_line_ids': lines})

    def action_approve_prices(self):
        self.ensure_one()
        if not self.price_update_line_ids:
            raise UserError(_("There are no price update lines to approve."))

        for line in self.price_update_line_ids:
            if line.new_wholesale_price <= line.cost_price:
                raise UserError(_("Wholesale price for %s cannot be less than or equal to its cost price (%.2f).") % (line.product_id.display_name, line.cost_price))
            if line.new_retail_price <= line.cost_price:
                raise UserError(_("Retail price for %s cannot be less than or equal to its cost price (%.2f).") % (line.product_id.display_name, line.cost_price))
            
            # Update the wholesale and retail prices on the template
            line.product_id.product_tmpl_id.write({
                'wholesale_price': line.new_wholesale_price,
                'retail_price': line.new_retail_price,
            })

        self.prices_approved = True
        self.message_post(body=_("Selling prices (Wholesale and Retail) were updated and approved by %s.") % self.env.user.name)

    def button_validate(self):
        # Call super() first so moves transition to 'done' state and date_done is set.
        # This ensures price_unit on moves reflects actual received cost and currency
        # conversion uses the correct date.
        res = super(StockPicking, self).button_validate()
        # If super() returned a wizard action dict (e.g. backorder dialog), the picking
        # hasn't been validated yet — skip generation until the wizard is confirmed.
        if isinstance(res, dict):
            return res
        for picking in self:
            if picking.picking_type_code == 'incoming' and picking.purchase_id:
                # Only generate if no lines exist yet — preserve any manual edits
                if not picking.price_update_line_ids and not picking.prices_approved:
                    picking.action_generate_price_lines()
        return res

    def action_approve(self):
        for picking in self:
            if picking.picking_type_code == 'incoming' and picking.purchase_id:
                if not picking.price_update_line_ids:
                    raise UserError(_("You must generate and verify Price Update lines before approving this receipt!"))
                if not picking.prices_approved:
                    picking.action_approve_prices()
        
        try:
            return super(StockPicking, self).action_approve()
        except AttributeError:
            pass
