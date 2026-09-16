# models/sale_order.py
from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    daily_sale_id = fields.Many2one('daily.sales', string='Daily Sales Entry',
                                    help='Link to daily sales tracking record')

    daily_sales_amount = fields.Monetary(string='Daily Sales Amount', compute='_compute_daily_sales', store=True,
                                         currency_field='currency_id')
    sale_type = fields.Selection([
        ('cash', 'Cash'),
        ('credit', 'Credit'),
    ], string='Sale Type', required=True, default='cash')

    @api.depends('order_line.price_total')
    def _compute_daily_sales(self):
        for order in self:
            order.daily_sales_amount = sum(order.order_line.mapped('price_total'))

    # def print_daily_sales(self):
    #    self.ensure_one()
    #   return self.env.ref('Yohannes_sales_person_target_management.action_report_daily_sales').report_action(self)

    # def action_print_sale_order(self):
    #   self.ensure_one()
    #  return self.env.ref('Yohannes_sales_person_target_management.action_report_sale_order_custom').report_action(self)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.date_order and record.user_id:
                date_only = record.date_order.date()
                daily_sale = self.env['daily.sales'].search([
                    ('date', '=', date_only),
                    ('salesperson_id', '=', record.user_id.id)
                ], limit=1)
                if not daily_sale:
                    daily_sale = self.env['daily.sales'].create({
                        'date': date_only,
                        'salesperson_id': record.user_id.id,
                    })
                record.daily_sale_id = daily_sale.id
                # Trigger recomputation of totals
                daily_sale._compute_sales_totals()
                if daily_sale.supervisor_daily_sales_id:
                    daily_sale.supervisor_daily_sales_id._compute_sales_totals()
        return records

    def action_print_sale_order(self):
        self.ensure_one()
        return self.env.ref('Yohannes_sales_person_target_management.action_report_sale_order_custom').report_action(self)

    @api.onchange('state')
    def _on_state_change(self):
        for order in self:
            if order.state == 'sale' and not order.daily_sale_id and order.date_order and order.user_id:
                date_only = order.date_order.date()
                daily_sale = self.env['daily.sales'].search([
                    ('date', '=', date_only),
                    ('salesperson_id', '=', order.user_id.id)
                ], limit=1)
                if not daily_sale:
                    daily_sale = self.env['daily.sales'].create({
                        'date': date_only,
                        'salesperson_id': order.user_id.id,
                    })
                order.daily_sale_id = daily_sale.id
                daily_sale._compute_sales_totals()
                if daily_sale.supervisor_daily_sales_id:
                    daily_sale.supervisor_daily_sales_id._compute_sales_totals()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # sale_order_line_id=fields.Many2one('daily.sale.report' ,related='daily.sale.report.id' ,string='sale order line id')
    lot_id = fields.Many2one('stock.lot', string='Batch Number',
                             domain="[('product_id', '=', product_id), ('company_id', '=', company_id)]",
                             help="Select the batch number for this product.")
    expiration_date = fields.Datetime(string='Expiration Date', related='lot_id.expiration_date', store=True,
                                      readonly=True, help="Expiration date of the selected batch.")

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Update domain for lot_id based on selected product."""
        if self.product_id and self.product_id.tracking in ('lot', 'serial'):
            self.lot_id = False  # Reset lot when product changes
            return {'domain': {
                'lot_id': [('product_id', '=', self.product_id.id), ('company_id', '=', self.company_id.id)]}}
        self.lot_id = False
        return {'domain': {'lot_id': []}}
