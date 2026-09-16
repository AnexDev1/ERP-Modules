# sale_order_inherit.py
from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    free_sample_request_id = fields.Many2one('free.sample.request', string='free Sample Request', readonly=True, copy=False)
    return_sample_request_id = fields.Many2one('return.sample.request', string='return Sample Request', readonly=True,
                                             copy=False)




class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    free_sample_request_line_id = fields.Many2one('free.sample.request.line', string='Free Sample Request Line', readonly=True,
                                             copy=False)
    return_sample_request_line_id = fields.Many2one('return.sample.request.line', string='Return Sample Request Line', readonly=True,
                                             copy=False)