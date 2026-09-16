from odoo import api, fields, models, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'




    default_code = fields.Char(string="Item Code")

    product_type = fields.Selection([
        ('import', 'Import Item'),
        ('wholesale', 'Wholesale Item'),
        ('both', 'Both (Import & Wholesale)')
    ], string="Product Type", default='import', company_dependent=True)



    default_warehouse_id = fields.Many2one('stock.warehouse', string="Default Warehouse", 
                                          company_dependent=True)
    

    manufacturer_origin = fields.Char(string="Manufacturer")
    origin_country_id = fields.Many2one('res.country', string="Origin Country")
    active_ingredient = fields.Char(string="General Name")
    
    specification = fields.Text(string="Product Specification", company_dependent=True, 
                               help="Specific notes/details for this product within this company.")

    storage_condition = fields.Selection([
        ('ambient', 'Ambient (15-25°C)'),
        ('cold_chain', 'Cold Chain (2-8°C)'),
        ('narcotic', 'Narcotic/Controlled')
    ], string="Storage Condition", default='ambient', company_dependent=True)


    avg_monthly_consumption = fields.Float(string="Average Monthly Consumption", company_dependent=True)
    
    stock_status = fields.Selection([
        ('under', 'Understock'),
        ('healthy', 'Healthy'),
        ('over', 'Overstock'),
        ('none', 'No Consumption Data')
    ], string="Stock Coverage Status", compute="_compute_stock_status", search="_search_stock_status")

    emergency_order_point = fields.Float(string="Emergency Order Point (Months)", company_dependent=True, default=4.0,
                                        help="Safety stock target in months. Alert triggered below this.")
    max_stock_level = fields.Float(string="Maximum Stock Level (Months)", company_dependent=True, default=6.0,
                                    help="Inventory target in months. Automated orders fill up to this.")
    
    pharmacy_list_price = fields.Float(string="Sales Price Pharmacy", company_dependent=True)
    
    expiry_status = fields.Selection([
        ('valid', 'Valid'),
        ('near', 'Near Expiry (30-90 Days)'),
        ('expired', 'Expired')
    ], string="Expiry Status", compute="_compute_expiry_status", search="_search_expiry_status")

    procurement_source = fields.Selection([
        ('local', 'Local Only'),
        ('foreign', 'Foreign Only'),
        ('both', 'Both (Local & Foreign)')
    ], string="Sourcing Strategy", default='local', company_dependent=True)

    @api.constrains('product_type')
    def _check_product_type(self):
        for record in self:
            if not record.product_type:
                raise UserError(_("You must select a product type (Import, Wholesale, or Both)."))

    preferred_source = fields.Selection([
        ('local', 'Local'),
        ('foreign', 'Foreign')
    ], string="Preferred Source", default='local', company_dependent=True,
       help="If 'Both' is selected, which requisition should be auto-generated first?")

    is_consignment_item = fields.Boolean(string="Consignment Item", company_dependent=True)
    old_reference = fields.Char(string="Old Reference")

    allowed_wh_types = fields.Json(compute="_compute_allowed_wh_types")

    @api.depends('product_type')
    def _compute_allowed_wh_types(self):
        for rec in self:
            types = []
            if rec.product_type in ['import', 'both']:
                types.append('import')
            if rec.product_type in ['wholesale', 'both']:
                types.append('wholesale')
            rec.allowed_wh_types = types



    company_is_pharmacy = fields.Boolean(compute="_compute_company_type")
    company_is_pharma = fields.Boolean(compute="_compute_company_type")

    def _compute_company_type(self):
        pharmacy_ids = [2] 
        for record in self:
            record.company_is_pharmacy = self.env.company.id in pharmacy_ids
            record.company_is_pharma = not record.company_is_pharmacy

    @api.depends('qty_available', 'avg_monthly_consumption')
    def _compute_stock_status(self):
        for record in self:
            amc = record.avg_monthly_consumption
            
            if amc <= 0:
                record.stock_status = 'none'
                continue
            
            coverage_months = record.qty_available / amc
            
            if coverage_months < record.emergency_order_point:
                record.stock_status = 'under'
            elif coverage_months > record.max_stock_level:
                record.stock_status = 'over'
            else:
                record.stock_status = 'healthy'

    def _create_understock_activity(self):
        """ Automatically alert the Warehouse Manager when stock hits critical level """
        manager_group = self.env.ref('stock.group_stock_manager').user_ids
        for manager in manager_group[:1]: 
            existing = self.env['mail.activity'].search([
                ('res_id', '=', self.id),
                ('res_model_id', '=', self.env.ref('product.model_product_template').id),
                ('summary', 'like', 'Understock Alert')
            ])
            if not existing:
                amc_value = self.avg_monthly_consumption
                self.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=_('Understock Alert: %s') % self.name,
                    note=_('Stock has fallen below %s months coverage. Current AMC is %s.') % (self.emergency_order_point, amc_value),
                    user_id=manager.id
                )

    def _initiate_rfq_draft(self):
        """ Automatically initiate a Local or Foreign Draft RFQ based on is_bought_locally. """
        if 'purchase.order' not in self.env:
            return
        local_purchase_exists = 'local.purchase.requisition' in self.env
        foreign_purchase_exists = 'foreign.purchase.requisition' in self.env
        if not local_purchase_exists and not foreign_purchase_exists:
            return

        analytic_cat = self.env['budget.lines'].sudo().search([('company_id', '=', self.env.company.id)], limit=1)
        if not analytic_cat:
            _logger.warning("No budget.line found for company %s.", self.env.company.name)

        for record in self:
            amc = record.avg_monthly_consumption
            target_qty = amc * (record.max_stock_level or 6.0)
            needed_qty = target_qty - record.qty_available

            if needed_qty <= 0:
                continue

            today = fields.Date.today()
            
            should_do_local = False
            should_do_foreign = False

            source_type = record.procurement_source
            if source_type == 'local':
                should_do_local = True
            elif source_type == 'foreign':
                should_do_foreign = True
            elif source_type == 'both':
                if record.preferred_source == 'local':
                    should_do_local = True
                else:
                    should_do_foreign = True

            if should_do_local and local_purchase_exists:
                existing_request = self.env['local.purchase.requisition.line'].sudo().search([
                    ('product_id', '=', record.product_variant_id.id),
                    ('requisition_id.company_id', '=', self.env.company.id),
                    ('requisition_id.state', 'in', ['draft', 'submitted', 'verified', 'budget_approved', 'pr_manager_approved', 'ceo_approved'])
                ], limit=1)

                if existing_request:
                    continue

                req_name = f'AUTO/LOCAL/{today.strftime("%Y/%m/%d")}'
                
                requisition = self.env['local.purchase.requisition'].sudo().search([
                    ('company_id', '=', self.env.company.id),
                    ('date_requisition', '>=', today),
                    ('state', '=', 'draft'),
                    ('name', '=', req_name)
                ], limit=1)

                if not requisition:
                    requisition = self.env['local.purchase.requisition'].sudo().create({
                        'name': req_name,
                        'company_id': self.env.company.id,
                        'date_requisition': today,
                        'state': 'draft',
                        'procurement_method': 'rfq',
                        'purchase_type': 'goods'
                    })

                self.env['local.purchase.requisition.line'].sudo().create({
                    'requisition_id': requisition.id,
                    'product_id': record.product_variant_id.id,
                    'quantity': needed_qty,
                    'budget_category_id': analytic_cat.id if analytic_cat else False
                })

            elif should_do_foreign and foreign_purchase_exists:
                existing_request = self.env['foreign.purchase.requisition.line'].sudo().search([
                    ('product_id', '=', record.product_variant_id.id),
                    ('requisition_id.company_id', '=', self.env.company.id),
                    ('requisition_id.state', 'in', ['draft', 'submitted', 'verified', 'budget_approved'])
                ], limit=1)

                if existing_request:
                    continue

                req_name = f'AUTO/FOREIGN/{today.strftime("%Y/%m/%d")}'
                
                requisition = self.env['foreign.purchase.requisition'].sudo().search([
                    ('company_id', '=', self.env.company.id),
                    ('date_requisition', '>=', today),
                    ('state', '=', 'draft'),
                    ('name', '=', req_name)
                ], limit=1)

                if not requisition:
                    requisition = self.env['foreign.purchase.requisition'].sudo().create({
                        'name': req_name,
                        'company_id': self.env.company.id,
                        'date_requisition': today,
                        'state': 'draft'
                    })

                self.env['foreign.purchase.requisition.line'].sudo().create({
                    'requisition_id': requisition.id,
                    'product_id': record.product_variant_id.id,
                    'quantity': needed_qty,
                    'budget_category_id': analytic_cat.id if analytic_cat else False
                })

    def _compute_amc_values(self):
        one_year_ago = fields.Datetime.now() - relativedelta(years=1)
        current_company_id = self.env.company.id

        for product in self:
            product.avg_monthly_consumption = 0.0

        if not self:
            return

        moves = self.env['stock.move']._read_group(
            domain=[
                ('product_id.product_tmpl_id', 'in', self.ids),
                ('company_id', '=', current_company_id),
                ('state', '=', 'done'),
                ('date', '>=', one_year_ago),
                ('location_id.usage', '=', 'internal'),
                '|',
                    ('location_dest_id.usage', '!=', 'internal'),
                    ('location_dest_id.company_id', '!=', current_company_id)
            ],
            groupby=['product_id.product_tmpl_id'],
            aggregates=['product_qty:sum'],
        )

        product_id_map = {product.id: product for product in self}

        for product_tmpl, total_qty in moves:
            if product_tmpl.id in product_id_map:
                product_id_map[product_tmpl.id].avg_monthly_consumption = total_qty / 12.0

    @api.model
    def cron_recompute_amc(self):
        companies = self.env['res.company'].search([])
        for company in companies:
            products = self.with_company(company).search([])
            products.with_company(company)._compute_amc_values()
        return True

    @api.depends('qty_available', 'categ_id.batch_expiry_alert_days')
    def _compute_expiry_status(self):
        today = fields.Date.today()
        for record in self:
            quants = self.env['stock.quant'].search([
                ('product_id.product_tmpl_id', '=', record.id),
                ('lot_id.expiration_date', '!=', False),
                ('quantity', '>', 0)
            ])
            if not quants:
                record.expiry_status = 'valid'
                continue
            
            exp_dates = quants.mapped('lot_id.expiration_date')
            nearest_exp = min(exp_dates).date()
            delta = (nearest_exp - today).days
            
            alert_days = record.categ_id.batch_expiry_alert_days or 90
            
            if delta < 0:
                record.expiry_status = 'expired'
            elif delta <= alert_days:
                record.expiry_status = 'near'
            else:
                record.expiry_status = 'valid'

    def _search_stock_status(self, operator, value):
        recs = self.search([]).filtered(lambda x: x.stock_status == value)
        return [('id', 'in', recs.ids)]

    def _search_expiry_status(self, operator, value):
        recs = self.search([]).filtered(lambda x: x.expiry_status == value)
        return [('id', 'in', recs.ids)]

    def action_view_near_expiry_lots(self):
        self.ensure_one()
        today = fields.Date.today()
        alert_days = self.categ_id.batch_expiry_alert_days or 90
        limit_date = today + relativedelta(days=alert_days)
        
        quants = self.env['stock.quant'].search([
            ('product_id.product_tmpl_id', '=', self.id),
            ('lot_id.expiration_date', '!=', False),
            ('lot_id.expiration_date', '<=', limit_date),
            ('quantity', '>', 0)
        ])
        lot_ids = quants.mapped('lot_id').ids
        
        return {
            'name': _('Near Expiry Batches'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.production.lot',
            'view_mode': 'list,form',
            'domain': [('id', 'in', lot_ids)],
            'context': {
                'default_product_id': self.product_variant_id.id,
                'search_default_group_by_product': 1
            },
        }

    def action_update_reordering_rules(self):
        for record in self:
            amc_to_use = record.avg_monthly_consumption
            
            min_qty = amc_to_use * record.emergency_order_point
            max_qty = amc_to_use * record.max_stock_level
            
            if max_qty < min_qty:
                max_qty = min_qty * 1.5

            if min_qty <= 0 and max_qty <= 0:
                continue
            
            warehouse_id = record.default_warehouse_id.id or self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1).id
            if not warehouse_id:
                continue

            rule = self.env['stock.warehouse.orderpoint'].search([
                ('product_id.product_tmpl_id', '=', record.id),
                ('warehouse_id', '=', warehouse_id),
                ('company_id', '=', self.env.company.id)
            ], limit=1)
            
            if rule:
                rule.write({'product_min_qty': min_qty, 'product_max_qty': max_qty})
            else:
                self.env['stock.warehouse.orderpoint'].create({
                    'product_id': record.product_variant_id.id,
                    'warehouse_id': warehouse_id,
                    'product_min_qty': min_qty,
                    'product_max_qty': max_qty,
                    'company_id': self.env.company.id,
                })
                
            coverage_months = record.qty_available / amc_to_use if amc_to_use > 0 else 0
            if coverage_months < record.emergency_order_point:
                record._create_understock_activity()
                record._initiate_rfq_draft()
                
        return True

    @api.model
    def cron_update_reordering_rules(self):
        """ Background task: Automatically adjust Min/Max for ALL products based on latest AMC """
        products = self.search([
            ('product_type', 'in', ['import', 'wholesale', 'both'])
        ])
        for product in products:
            try:
                product.action_update_reordering_rules()
            except Exception:
                continue
        return True

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, **kwargs):
        # Allow dynamic sorting by qty_available
        if order and 'qty_available' in order:
            is_desc = 'desc' in order.lower()
            records = self.search(domain)
            records = records.sorted(key=lambda r: r.qty_available, reverse=is_desc)
            if offset:
                records = records[offset:]
            if limit:
                records = records[:limit]
            res = records.read(fields, **kwargs)
            res_dict = {d['id']: d for d in res}
            return [res_dict[r.id] for r in records if r.id in res_dict]
        return super().search_read(domain=domain, fields=fields, offset=offset, limit=limit, order=order, **kwargs)

    @api.model
    def web_search_read(self, domain=None, specification=None, offset=0, limit=None, order=None, count_limit=None, **kwargs):
        if order and 'qty_available' in order:
            is_desc = 'desc' in order.lower()
            records = self.search(domain)
            length = len(records)
            records = records.sorted(key=lambda r: r.qty_available, reverse=is_desc)
            if offset:
                records = records[offset:]
            if limit:
                records = records[:limit]
            
            if hasattr(records, 'web_read'):
                res = records.web_read(specification)
                res_dict = {d['id']: d for d in res}
                ordered_res = [res_dict[r.id] for r in records if r.id in res_dict]
                return {'length': length, 'records': ordered_res}
            else:
                fields = kwargs.get('fields') or (specification if isinstance(specification, list) else [])
                res = records.read(fields)
                res_dict = {d['id']: d for d in res}
                ordered_res = [res_dict[r.id] for r in records if r.id in res_dict]
                return {'length': length, 'records': ordered_res}
        
        if hasattr(super(), 'web_search_read'):
            return super().web_search_read(domain=domain, specification=specification, offset=offset, limit=limit, order=order, count_limit=count_limit, **kwargs)
        records_data = super().search_read(domain=domain, fields=kwargs.get('fields') or (specification if isinstance(specification, list) else []), offset=offset, limit=limit, order=order, **kwargs)
        return {'length': len(records_data), 'records': records_data}

class ProductProduct(models.Model):
    _inherit = 'product.product'

    default_code = fields.Char(string="Item Code")

    def _compute_quantities(self):
        """Override to exclude suspense locations (allow_negative_stock=True) from qty_available.
        This ensures Sales always sees only the real, sellable stock — not items parked in suspense."""
        super()._compute_quantities()

        # Safety check: field only exists if deltatech_stock_negative module is installed
        if 'allow_negative_stock' not in self.env['stock.location']._fields:
            return

        # Find suspense locations (allow_negative_stock = True)
        suspense_locations = self.env['stock.location'].search([
            ('allow_negative_stock', '=', True),
            ('usage', '=', 'internal'),
        ])

        if not suspense_locations:
            return

        # Get qty sitting in suspense locations per product (batch query)
        quant_data = self.env['stock.quant']._read_group(
            [
                ('product_id', 'in', self.ids),
                ('location_id', 'in', suspense_locations.ids),
            ],
            groupby=['product_id'],
            aggregates=['quantity:sum'],
        )
        suspense_qty_map = {product.id: qty for product, qty in quant_data}

        for product in self:
            suspense_qty = suspense_qty_map.get(product.id, 0.0)
            if suspense_qty:
                product.qty_available = max(0.0, product.qty_available - suspense_qty)



    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, **kwargs):
        # Allow dynamic sorting by qty_available
        if order and 'qty_available' in order:
            is_desc = 'desc' in order.lower()
            records = self.search(domain)
            records = records.sorted(key=lambda r: r.qty_available, reverse=is_desc)
            if offset:
                records = records[offset:]
            if limit:
                records = records[:limit]
            res = records.read(fields, **kwargs)
            res_dict = {d['id']: d for d in res}
            return [res_dict[r.id] for r in records if r.id in res_dict]
        return super().search_read(domain=domain, fields=fields, offset=offset, limit=limit, order=order, **kwargs)

    @api.model
    def web_search_read(self, domain=None, specification=None, offset=0, limit=None, order=None, count_limit=None, **kwargs):
        if order and 'qty_available' in order:
            is_desc = 'desc' in order.lower()
            records = self.search(domain)
            length = len(records)
            records = records.sorted(key=lambda r: r.qty_available, reverse=is_desc)
            if offset:
                records = records[offset:]
            if limit:
                records = records[:limit]
            
            if hasattr(records, 'web_read'):
                res = records.web_read(specification)
                res_dict = {d['id']: d for d in res}
                ordered_res = [res_dict[r.id] for r in records if r.id in res_dict]
                return {'length': length, 'records': ordered_res}
            else:
                fields = kwargs.get('fields') or (specification if isinstance(specification, list) else [])
                res = records.read(fields)
                res_dict = {d['id']: d for d in res}
                ordered_res = [res_dict[r.id] for r in records if r.id in res_dict]
                return {'length': length, 'records': ordered_res}
        
        if hasattr(super(), 'web_search_read'):
            return super().web_search_read(domain=domain, specification=specification, offset=offset, limit=limit, order=order, count_limit=count_limit, **kwargs)
        records_data = super().search_read(domain=domain, fields=kwargs.get('fields') or (specification if isinstance(specification, list) else []), offset=offset, limit=limit, order=order, **kwargs)
        return {'length': len(records_data), 'records': records_data}

def post_init_hook(env):
    # Check if the old columns exist before attempting migration
    env.cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'product_template'
          AND column_name IN ('is_import', 'is_wholesale')
    """)
    columns = [r[0] for r in env.cr.fetchall()]
    if 'is_import' in columns and 'is_wholesale' in columns:
        # Move boolean values into product_type before the fields are dropped
        env.cr.execute("""
            UPDATE product_template
            SET product_type = CASE
                WHEN is_import AND is_wholesale THEN 'both'
                WHEN is_import THEN 'import'
                WHEN is_wholesale THEN 'wholesale'
                ELSE 'import'
            END
            WHERE is_import IS NOT NULL OR is_wholesale IS NOT NULL;
        """)
