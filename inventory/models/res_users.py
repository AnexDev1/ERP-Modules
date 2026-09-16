from odoo import models, fields, api

class ResUsers(models.Model):
    _inherit = 'res.users'

    allowed_warehouse_ids = fields.Many2many(
        'stock.warehouse',
        'res_users_warehouse_rel',
        'user_id',
        'warehouse_id',
        string='Allowed Warehouses',
        help="Warehouses that this user is allowed to access. If left empty, the user might not be able to see any warehouse records unless they are an Administrator."
    )

    @api.model_create_multi
    def create(self, vals_list):
        users = super(ResUsers, self).create(vals_list)
        for user in users:
            if user.has_group('stock.group_stock_user') and not user.allowed_warehouse_ids:
                warehouses = self.env['stock.warehouse'].search([('company_id', 'in', user.company_ids.ids)])
                if warehouses:
                    user.allowed_warehouse_ids = warehouses
        return users

    def write(self, vals):
        res = super(ResUsers, self).write(vals)
        
        # Invalidate cache so that record rules using user.allowed_warehouse_ids apply instantly
        if 'allowed_warehouse_ids' in vals:
            self.env.registry.clear_cache()
            
        if 'allowed_warehouse_ids' not in vals:
            group_or_company_change = any(
                k.startswith('sel_groups_') or 
                k.startswith('in_group_') or 
                k in ['groups_id', 'company_id', 'company_ids']
                for k in vals
            )
            if group_or_company_change:
                for user in self:
                    if user.has_group('stock.group_stock_user') and not user.allowed_warehouse_ids:
                        warehouses = self.env['stock.warehouse'].search([('company_id', 'in', user.company_ids.ids)])
                        if warehouses:
                            user.allowed_warehouse_ids = warehouses
        return res
