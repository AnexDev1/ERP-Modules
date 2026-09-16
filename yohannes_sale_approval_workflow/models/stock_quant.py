from odoo import models, fields, api
from datetime import timedelta

class IrActions(models.Model):
    _inherit = 'ir.actions.actions'

    @api.model
    def get_bindings(self, model_name):
        res = super(IrActions, self).get_bindings(model_name)
        if model_name == 'stock.quant' and self.env.context.get('hide_standard_actions'):
            if 'action' in res:
                res['action'] = []
            if 'report' in res:
                res['report'] = [r for r in res['report'] if 'Products Printout' in r.get('name', '')]
        return res

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    expiry_state = fields.Selection([
        ('expired', 'Expired'),
        ('expiring_soon', 'Expiring Soon'),
        ('valid', 'Valid')
    ], string='Expiry Status', compute='_compute_expiry_state', store=False)
    
    expiration_date = fields.Datetime(related='lot_id.expiration_date', string='Expiration Date', store=False)

    expired_quantity = fields.Float(
        string='Expired Quantity',
        compute='_compute_expired_quantity',
        store=False
    )
    
    item_code = fields.Char(related='product_id.default_code', string='Item Code', store=False)
    wholesale_price = fields.Float(related='product_id.product_tmpl_id.wholesale_price', string='Wholesale Price', store=False, group_operator=False)
    retail_price = fields.Float(related='product_id.product_tmpl_id.retail_price', string='Retail Price', store=False, group_operator=False)
    currency_id = fields.Many2one(related='product_id.currency_id', string='Currency', store=False)

    @api.depends('quantity', 'expiry_state')
    def _compute_expired_quantity(self):
        for quant in self:
            if quant.expiry_state == 'expired':
                quant.expired_quantity = quant.quantity
            else:
                quant.expired_quantity = 0.0

    @api.depends('lot_id.expiration_date')
    def _compute_expiry_state(self):
        today = fields.Date.context_today(self)
        warning_date = today + timedelta(days=30)
        
        for quant in self:
            if not quant.lot_id or not quant.lot_id.expiration_date:
                quant.expiry_state = False
                continue
                
            exp_date = quant.lot_id.expiration_date.date()
            if exp_date < today:
                quant.expiry_state = 'expired'
            elif exp_date <= warning_date:
                quant.expiry_state = 'expiring_soon'
            else:
                quant.expiry_state = 'valid'
