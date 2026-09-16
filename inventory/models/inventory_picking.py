from odoo import api, fields, models, _
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        for picking in self:
            if picking.picking_type_code == 'incoming':
                for move in picking.move_ids:
                    if move.product_id.tracking != 'none':
                        for line in move.move_line_ids:
                            if not line.lot_id and not line.lot_name:
                                raise UserError(_(
                                    "Lot/Batch number is mandatory for product: %s"
                                ) % move.product_id.display_name)

                            lot = line.lot_id
                            if lot and not lot.expiration_date:
                                raise UserError(_(
                                    "Expiration Date is mandatory for Lot: %s of product: %s"
                                ) % (lot.name, move.product_id.display_name))
        
        res = super(StockPicking, self).button_validate()
        
        for picking in self:
            if picking.state == 'done':
                products = picking.move_ids.mapped('product_id.product_tmpl_id')
                if products:
                    products._compute_amc_values()
                    products.action_update_reordering_rules()
        
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                picking_type = self.env['stock.picking.type'].browse(vals.get('picking_type_id'))
                warehouse = picking_type.warehouse_id
                
                type_code = picking_type.code.upper() if picking_type.code else 'PICK'
                division = (warehouse.wh_type or 'GEN').upper() if hasattr(warehouse, 'wh_type') else 'GEN'
                year = fields.Date.today().year
                
                seq_code = 'stock.picking.sequence'
                serial = self.env['ir.sequence'].next_by_code(seq_code) or '00001'
                
                vals['name'] = f"{type_code}/{division}/{year}/{serial}"
                
        return super(StockPicking, self).create(vals_list)
