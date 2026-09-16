from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enable_order_source = fields.Boolean(
        related='company_id.enable_order_source',
        readonly=False,
        string="Enable Order Source"
    )


    use_so_manual_sequence_limit = fields.Boolean(
        related='company_id.use_so_manual_sequence_limit',
        readonly=False,
        string="Use Sales Order Manual Sequence Limit"
    )

    so_manual_sequence_limit = fields.Integer(
        related='company_id.so_manual_sequence_limit',
        readonly=False,
        string="Sales Order Last Manual Limit"
    )

    group_allow_manual_discount = fields.Boolean(

        string="Enable Manual Discounts",
        implied_group='yohannes_sale_approval_workflow.group_allow_manual_discount'
    )
