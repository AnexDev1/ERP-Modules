import logging
from odoo import models, fields, api, _
from datetime import datetime, timedelta

# _logger = logging.getLogger(__name__)

class ProductCategory(models.Model):
    _inherit = 'product.category'
    
    batch_expiry_alert_days = fields.Integer(
        string="Batch Expiry Alert (Days)", 
        default=90,
        help="Number of days before expiry to trigger a warning for items in this category."
    )
    available_in_master = fields.Boolean(
        string="Available in Product Master", 
        default=True,
        help="If unchecked, this category and its products will be hidden from selection dropdowns."
    )

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        is_sale_search = any(isinstance(leaf, (list, tuple)) and leaf[0] == 'sale_ok' for leaf in domain)
        if is_sale_search and not self.env.context.get('ignore_availability') and not self.env.su:
            from odoo.osv import expression
            domain = expression.AND([domain, [('available_in_master', '=', True)]])
        return super()._name_search(name, domain, operator, limit, order)

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        is_id_search = False
        is_sale_search = False
        if domain:
            for leaf in domain:
                if isinstance(leaf, (list, tuple)) and leaf[0] == 'id':
                    is_id_search = True
                if isinstance(leaf, (list, tuple)) and leaf[0] == 'sale_ok':
                    is_sale_search = True
        
        if is_sale_search and not is_id_search and not self.env.context.get('ignore_availability') and not self.env.su:
            from odoo.osv import expression
            domain = expression.AND([domain, [('available_in_master', '=', True)]])
        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        is_sale_search = any(isinstance(leaf, (list, tuple)) and leaf[0] == 'sale_ok' for leaf in domain)
        if is_sale_search and not self.env.context.get('ignore_availability') and not self.env.su:
            from odoo.osv import expression
            domain = expression.AND([domain, [('categ_id.available_in_master', '=', True)]])
        return super()._name_search(name, domain, operator, limit, order)
        
    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        is_id_search = False
        is_sale_search = False
        if domain:
            for leaf in domain:
                if isinstance(leaf, (list, tuple)) and leaf[0] == 'id':
                    is_id_search = True
                if isinstance(leaf, (list, tuple)) and leaf[0] == 'sale_ok':
                    is_sale_search = True
        
        if is_sale_search and not is_id_search and not self.env.context.get('ignore_availability') and not self.env.su:
            from odoo.osv import expression
            domain = expression.AND([domain, [('categ_id.available_in_master', '=', True)]])
        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        is_sale_search = any(isinstance(leaf, (list, tuple)) and leaf[0] == 'sale_ok' for leaf in domain)
        if is_sale_search and not self.env.context.get('ignore_availability') and not self.env.su:
            from odoo.osv import expression
            domain = expression.AND([domain, [('categ_id.available_in_master', '=', True)]])
        return super()._name_search(name, domain, operator, limit, order)
        
    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        is_id_search = False
        is_sale_search = False
        if domain:
            for leaf in domain:
                if isinstance(leaf, (list, tuple)) and leaf[0] == 'id':
                    is_id_search = True
                if isinstance(leaf, (list, tuple)) and leaf[0] == 'sale_ok':
                    is_sale_search = True
        
        if is_sale_search and not is_id_search and not self.env.context.get('ignore_availability') and not self.env.su:
            from odoo.osv import expression
            domain = expression.AND([domain, [('categ_id.available_in_master', '=', True)]])
        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)



