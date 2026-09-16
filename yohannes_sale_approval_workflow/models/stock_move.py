from odoo import models

class StockMove(models.Model):
    _inherit = 'stock.move'

    def _update_reserved_quantity_vals(self, need, location_id, lot_id=None, package_id=None, owner_id=None, strict=True):
        # If this move comes from a sale order line that specifically requested a lot, force reservation for that lot
        if not lot_id and self.sale_line_id and self.sale_line_id.lot_id:
            lot_id = self.sale_line_id.lot_id
            
        return super()._update_reserved_quantity_vals(
            need, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict
        )
