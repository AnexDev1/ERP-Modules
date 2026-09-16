# sale_order_inherit.py
from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    #consignment_request_id = fields.Many2one('consignment.request', string='Consignment Request', readonly=True, copy=False)
    consignment_request_id = fields.Many2one(
        'consignment.request',
        string='Consignment Request',
        ondelete='set null',
        index=True,
        copy=False,
    )




class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    consignment_request_line_id = fields.Many2one('consignment.request.line', string='Sample Request Line', readonly=True,
                                             copy=False)