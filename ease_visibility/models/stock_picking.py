from ast import literal_eval

from odoo import api, models


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    def _without_open_state_filters(self, action):
        ctx = dict(action.get('context') or {})
        if isinstance(ctx, str):
            ctx = dict(literal_eval(ctx))
        for key in list(ctx):
            if key.startswith('search_default_') and key not in {
                'search_default_picking_type_id',
                'search_default_reception',
                'search_default_delivery',
                'search_default_internal',
            }:
                ctx.pop(key, None)
        action['context'] = ctx
        return action

    def _get_action(self, action_xmlid):
        xmlid = action_xmlid
        if action_xmlid in {
            'stock.action_picking_tree_ready',
            'stock.action_picking_tree_waiting',
            'stock.action_picking_tree_late',
            'stock.action_picking_tree_backorder',
        }:
            xmlid = 'stock.stock_picking_action_picking_type'
        return self._without_open_state_filters(super()._get_action(xmlid))

    def get_action_picking_tree_ready(self):
        return self._get_action('stock.stock_picking_action_picking_type')


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _without_open_state_filters(self, action):
        ctx = dict(action.get('context') or {})
        if isinstance(ctx, str):
            ctx = dict(literal_eval(ctx))
        for key in list(ctx):
            if key.startswith('search_default_') and key not in {
                'search_default_picking_type_id',
                'search_default_reception',
                'search_default_delivery',
                'search_default_internal',
            }:
                ctx.pop(key, None)
        action['context'] = ctx
        return action

    def _get_action(self, action_xmlid):
        return self._without_open_state_filters(super()._get_action(action_xmlid))

    @api.model
    def get_action_picking_tree_incoming(self):
        return self._get_action('stock.action_picking_tree_incoming')

    @api.model
    def get_action_picking_tree_outgoing(self):
        return self._get_action('stock.action_picking_tree_outgoing')

    @api.model
    def get_action_picking_tree_internal(self):
        return self._get_action('stock.action_picking_tree_internal')
