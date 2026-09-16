from odoo import models, fields

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    consignment_request_id = fields.Many2one(
        'consignment.request',
        string='Consignment Request',
        ondelete='set null',
        index=True,
        copy=False,
    )
