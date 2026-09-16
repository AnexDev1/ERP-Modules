from odoo import fields, models

class ResUsers(models.Model):
    _inherit = 'res.users'

    sale_discount_limit = fields.Float(
        string='Maximum Discount Limit (%)',
        config_parameter='yohannes_sale_approval_workflow.sale_discount_limit'
    )