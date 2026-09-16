from odoo import models, fields, api
from odoo.orm.domains import Domain

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def default_get(self, fields_list):
        res = super(ProductTemplate, self).default_get(fields_list)
        if 'taxes_id' in fields_list:
            res['taxes_id'] = False
        if 'supplier_taxes_id' in fields_list:
            res['supplier_taxes_id'] = False
        return res
    @api.model
    def _order_field_to_sql(self, alias, field_name, direction, nulls, query):
        if field_name == 'qty_available':
            try:
                from odoo.tools.sql import SQL
                
                location = self.env.context.get('location') or self.env.context.get('location_id')
                warehouse = self.env.context.get('warehouse') or self.env.context.get('warehouse_id')
                
                target_locations = self.env['stock.location']
                if location:
                    if isinstance(location, (int, str)):
                        location = [int(location)]
                    target_locations |= self.env['stock.location'].browse(location)
                elif warehouse:
                    if isinstance(warehouse, (int, str)):
                        warehouse = [int(warehouse)]
                    warehouses = self.env['stock.warehouse'].browse(warehouse)
                    target_locations |= warehouses.mapped('view_location_id')
                
                context_filter = SQL("")
                if target_locations:
                    path_filters = []
                    for loc in target_locations.sudo():
                        if loc.parent_path:
                            path_filters.append(SQL("sl.parent_path LIKE %s", loc.parent_path + '%'))
                    if path_filters:
                        context_filter = SQL(" AND (%s)", SQL(" OR ").join(path_filters))

                sql_field = SQL("""
                    COALESCE((
                        SELECT SUM(sq.quantity)
                        FROM stock_quant sq
                        JOIN stock_location sl ON sl.id = sq.location_id
                        JOIN product_product pp ON pp.id = sq.product_id
                        WHERE pp.product_tmpl_id = %s
                          AND sl.usage = 'internal'
                          %s
                    ), 0.0)
                """, SQL.identifier(alias, 'id'), context_filter)
                query._order_groupby.append(sql_field)
                return SQL("%s %s %s", sql_field, direction, nulls)
            except Exception:
                pass
        return super()._order_field_to_sql(alias, field_name, direction, nulls, query)

    # which this module depends on. No need to redefine it here.

    wholesale_price = fields.Float(
        string='Wholesale Price',
        digits='Product Price',
        help="Sales price for Wholesale customers. This replaces the standard Sales Price."
    )
    retail_price = fields.Float(
        string='Retail Price',
        digits='Product Price',
        help="Sales price for Retail customers."
    )

    is_sales_price_updator = fields.Boolean(
        compute='_compute_is_sales_price_updator',
        string="Is Sales Price Updator"
    )



    def _compute_is_sales_price_updator(self):
        has_group = self.env.user.has_group('yohannes_sale_approval_workflow.group_sales_price_updator')
        for record in self:
            record.is_sales_price_updator = has_group

    @api.onchange('wholesale_price')
    def _onchange_wholesale_price(self):
        """Keep list_price in sync with wholesale_price (Odoo uses list_price internally)."""
        if self.wholesale_price:
            self.list_price = self.wholesale_price

    def write(self, vals):
        """Keep list_price in sync when wholesale_price is saved, and log price changes in chatter."""
        if 'wholesale_price' in vals and vals['wholesale_price']:
            vals['list_price'] = vals['wholesale_price']

        # Log price changes in chatter before saving
        price_fields = {
            'wholesale_price': 'Wholesale Price',
            'retail_price': 'Retail Price',
        }
        for record in self:
            messages = []
            for field_name, label in price_fields.items():
                if field_name in vals:
                    old_val = getattr(record, field_name, 0.0) or 0.0
                    new_val = float(vals[field_name] or 0.0)
                    if abs(old_val - new_val) > 0.0001:
                        messages.append(f"<b>{label}</b>: {old_val:,.2f} &#8594; {new_val:,.2f}")
            if messages:
                body = "Price updated:<br/>" + "<br/>".join(messages)
                record.message_post(body=body)

        return super().write(vals)

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=100, order=None, **kwargs):
        customer_type = self._context.get('customer_type')
        domain = Domain(domain or [])
        if customer_type == 'wholesale':
            domain &= Domain('wholesale_price', '>', 0)
        elif customer_type == 'retail':
            domain &= Domain('retail_price', '>', 0)

        if self._context.get('is_sale_order_line'):
            order_source = self._context.get('order_source')
            enable_order_source = self._context.get('enable_order_source', True)
            
            warehouse_id = self._context.get('warehouse_id')
            if warehouse_id:
                self = self.with_context(warehouse=warehouse_id)
            elif order_source:
                warehouses = self.env['stock.warehouse'].search([('wh_type', '=', order_source)])
                if warehouses:
                    self = self.with_context(warehouse=warehouses.ids)
                    
            if not enable_order_source or order_source == 'import':
                domain &= Domain('qty_available', '>', 0)
        return super()._name_search(name, domain=domain, operator=operator, limit=limit, order=order, **kwargs)

    @api.model
    def _search(self, domain, *args, **kwargs):
        customer_type = self._context.get('customer_type')
        domain = Domain(domain or [])
        if customer_type == 'wholesale':
            domain &= Domain('wholesale_price', '>', 0)
        elif customer_type == 'retail':
            domain &= Domain('retail_price', '>', 0)

        if self._context.get('is_sale_order_line'):
            order_source = self._context.get('order_source')
            enable_order_source = self._context.get('enable_order_source', True)
            
            warehouse_id = self._context.get('warehouse_id')
            if warehouse_id:
                self = self.with_context(warehouse=warehouse_id)
            elif order_source:
                warehouses = self.env['stock.warehouse'].search([('wh_type', '=', order_source)])
                if warehouses:
                    self = self.with_context(warehouse=warehouses.ids)
                    
            if not enable_order_source or order_source == 'import':
                domain &= Domain('qty_available', '>', 0)
                
        return super()._search(domain, *args, **kwargs)

class ProductProduct(models.Model):
    _inherit = 'product.product'



    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=100, order=None, **kwargs):
        customer_type = self._context.get('customer_type')
        domain = Domain(domain or [])
        if customer_type == 'wholesale':
            domain &= Domain('wholesale_price', '>', 0)
        elif customer_type == 'retail':
            domain &= Domain('retail_price', '>', 0)

        if self._context.get('is_sale_order_line'):
            order_source = self._context.get('order_source')
            enable_order_source = self._context.get('enable_order_source', True)
            
            warehouse_id = self._context.get('warehouse_id')
            if warehouse_id:
                self = self.with_context(warehouse=warehouse_id)
            elif order_source:
                warehouses = self.env['stock.warehouse'].search([('wh_type', '=', order_source)])
                if warehouses:
                    self = self.with_context(warehouse=warehouses.ids)
                    
            if not enable_order_source or order_source == 'import':
                domain &= Domain('qty_available', '>', 0)
        return super()._name_search(name, domain=domain, operator=operator, limit=limit, order=order, **kwargs)
    @api.model
    def _order_field_to_sql(self, alias, field_name, direction, nulls, query):
        if field_name == 'qty_available':
            try:
                from odoo.tools.sql import SQL
                
                location = self.env.context.get('location') or self.env.context.get('location_id')
                warehouse = self.env.context.get('warehouse') or self.env.context.get('warehouse_id')
                
                target_locations = self.env['stock.location']
                if location:
                    if isinstance(location, (int, str)):
                        location = [int(location)]
                    target_locations |= self.env['stock.location'].browse(location)
                elif warehouse:
                    if isinstance(warehouse, (int, str)):
                        warehouse = [int(warehouse)]
                    warehouses = self.env['stock.warehouse'].browse(warehouse)
                    target_locations |= warehouses.mapped('view_location_id')
                
                context_filter = SQL("")
                if target_locations:
                    path_filters = []
                    for loc in target_locations.sudo():
                        if loc.parent_path:
                            path_filters.append(SQL("sl.parent_path LIKE %s", loc.parent_path + '%'))
                    if path_filters:
                        context_filter = SQL(" AND (%s)", SQL(" OR ").join(path_filters))

                sql_field = SQL("""
                    COALESCE((
                        SELECT SUM(sq.quantity)
                        FROM stock_quant sq
                        JOIN stock_location sl ON sl.id = sq.location_id
                        WHERE sq.product_id = %s
                          AND sl.usage = 'internal'
                          %s
                    ), 0.0)
                """, SQL.identifier(alias, 'id'), context_filter)
                query._order_groupby.append(sql_field)
                return SQL("%s %s %s", sql_field, direction, nulls)
            except Exception:
                pass
        return super()._order_field_to_sql(alias, field_name, direction, nulls, query)

    @api.model
    def _search(self, domain, *args, **kwargs):
        customer_type = self._context.get('customer_type')
        domain = Domain(domain or [])
        if customer_type == 'wholesale':
            domain &= Domain('wholesale_price', '>', 0)
        elif customer_type == 'retail':
            domain &= Domain('retail_price', '>', 0)

        if self._context.get('is_sale_order_line'):
            order_source = self._context.get('order_source')
            enable_order_source = self._context.get('enable_order_source', True)
            
            warehouse_id = self._context.get('warehouse_id')
            if warehouse_id:
                self = self.with_context(warehouse=warehouse_id)
            elif order_source:
                warehouses = self.env['stock.warehouse'].search([('wh_type', '=', order_source)])
                if warehouses:
                    self = self.with_context(warehouse=warehouses.ids)
                    
            if not enable_order_source or order_source == 'import':
                domain &= Domain('qty_available', '>', 0)
                
        return super()._search(domain, *args, **kwargs)
