from odoo import models, fields

class LocalPurchaseRequisition(models.Model):
    _inherit = 'local.purchase.requisition'

    consignment_request_id = fields.Many2one(
        'consignment.request',
        string='Consignment Request',
        ondelete='set null',
        index=True,
        copy=False,
    )
