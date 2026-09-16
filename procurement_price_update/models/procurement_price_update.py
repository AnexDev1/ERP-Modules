# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ProcurementPriceUpdateLine(models.Model):
    _name = 'procurement.price.update.line'
    _description = 'Procurement Price Update Line'

    picking_id = fields.Many2one('stock.picking', string='Receipt', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', related='product_id.uom_id', readonly=True)
    
    cost_price = fields.Float(string='Cost Price (Company Currency)', required=True, digits='Product Price')
    
    current_wholesale_price = fields.Float(string='Current Wholesale Price', readonly=True, digits='Product Price')
    wholesale_margin_percent = fields.Float(string='Wholesale Margin (%)', digits=(16, 2))
    new_wholesale_price = fields.Float(string='New Wholesale Price', digits='Product Price')
    
    current_retail_price = fields.Float(string='Current Retail Price', readonly=True, digits='Product Price')
    retail_margin_percent = fields.Float(string='Retail Margin (%)', digits=(16, 2))
    new_retail_price = fields.Float(string='New Retail Price', digits='Product Price')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.current_wholesale_price = self.product_id.wholesale_price
            self.current_retail_price = self.product_id.retail_price
            
            # Fetch default margins based on PO type
            company = self.picking_id.company_id or self.env.company
            po = self.picking_id.purchase_id
            
            if po and po.request_type == 'local':
                self.wholesale_margin_percent = company.local_wholesale_margin
                self.retail_margin_percent = company.local_retail_margin
            elif po and po.request_type == 'foreign':
                self.wholesale_margin_percent = company.foreign_wholesale_margin
                self.retail_margin_percent = company.foreign_retail_margin
            else:
                self.wholesale_margin_percent = 0.0
                self.retail_margin_percent = 0.0
                
            self.new_wholesale_price = self.cost_price * (1 + (self.wholesale_margin_percent / 100.0))
            self.new_retail_price = self.cost_price * (1 + (self.retail_margin_percent / 100.0))

    @api.onchange('wholesale_margin_percent', 'cost_price')
    def _onchange_wholesale_margin_percent(self):
        for rec in self:
            rec.new_wholesale_price = rec.cost_price * (1 + (rec.wholesale_margin_percent / 100.0))

    @api.onchange('new_wholesale_price')
    def _onchange_new_wholesale_price(self):
        for rec in self:
            if rec.cost_price > 0:
                rec.wholesale_margin_percent = ((rec.new_wholesale_price - rec.cost_price) / rec.cost_price) * 100.0
            else:
                rec.wholesale_margin_percent = 0.0

    @api.onchange('retail_margin_percent', 'cost_price')
    def _onchange_retail_margin_percent(self):
        for rec in self:
            rec.new_retail_price = rec.cost_price * (1 + (rec.retail_margin_percent / 100.0))

    @api.onchange('new_retail_price')
    def _onchange_new_retail_price(self):
        for rec in self:
            if rec.cost_price > 0:
                rec.retail_margin_percent = ((rec.new_retail_price - rec.cost_price) / rec.cost_price) * 100.0
            else:
                rec.retail_margin_percent = 0.0
