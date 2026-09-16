from odoo import api, fields, models

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    available_lot_ids = fields.Many2many('stock.lot', compute='_compute_available_lot_ids')
    
    lot_id = fields.Many2one(
        'stock.lot', 
        string='Lot/Serial Number', 
        domain="[('id', 'in', available_lot_ids)]"
    )
    expiry_date = fields.Datetime(
        string='Expiry Date', 
        related='lot_id.expiration_date', 
        store=True, 
        readonly=False
    )

    @api.depends('product_id', 'order_id.warehouse_id')
    def _compute_available_lot_ids(self):
        for line in self:
            if not line.product_id:
                line.available_lot_ids = False
                continue
            
            domain = [
                ('product_id', '=', line.product_id.id),
                ('location_id.usage', '=', 'internal'),
                ('quantity', '>', 0),
                ('lot_id', '!=', False)
            ]
            if line.order_id and line.order_id.warehouse_id:
                domain.append(('location_id', 'child_of', line.order_id.warehouse_id.view_location_id.id))
            
            quants = self.env['stock.quant'].search(domain)
            quants = quants.filtered(lambda q: q.quantity > q.reserved_quantity)
            line.available_lot_ids = quants.mapped('lot_id').ids

    @api.onchange('product_id')
    def _onchange_product_id_set_lot(self):
        for line in self:
            if line.product_id:
                domain = [
                    ('product_id', '=', line.product_id.id),
                    ('location_id.usage', '=', 'internal'),
                    ('quantity', '>', 0),
                    ('lot_id', '!=', False)
                ]
                if line.order_id.warehouse_id:
                    domain.append(('location_id', 'child_of', line.order_id.warehouse_id.view_location_id.id))
                
                quants = self.env['stock.quant'].search(domain)
                # Filter out fully reserved quants
                quants = quants.filtered(lambda q: q.quantity > q.reserved_quantity)
                if quants:
                    lots = quants.mapped('lot_id').filtered(lambda l: l.id)
                    lots_with_expiry = lots.filtered(lambda l: l.expiration_date)
                    if lots_with_expiry:
                        line.lot_id = min(lots_with_expiry, key=lambda l: l.expiration_date)
                    elif lots:
                        line.lot_id = lots[0]

    @api.depends('order_id.warehouse_id', 'order_id.warehouse_id.analytic_account_id')
    def _compute_analytic_distribution(self):
        super()._compute_analytic_distribution()
        for line in self:
            warehouse_analytic = line.order_id.warehouse_id.analytic_account_id
            if warehouse_analytic:
                line.analytic_distribution = {str(warehouse_analytic.id): 100}
