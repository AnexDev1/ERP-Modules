from odoo import models, fields, api, _

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Check if picking is triggered by consignment/sample request via context or name
            picking_type = self.env['stock.picking.type'].browse(vals.get('picking_type_id'))
            is_consignment = self.env.context.get('is_consignment')
            
            if is_consignment or (picking_type and picking_type.name and any(x in picking_type.name for x in ['Consignment/placement', 'Consignment/sample receive'])):
                # Determine Prefix: Priority to context, fallback to name/code
                prefix = self.env.context.get('consignment_prefix')
                if not prefix:
                    prefix = 'COR' if 'sample receive' in (picking_type.name or '').lower() or picking_type.code == 'incoming' else 'COI'
                
                # Warehouse Short Code
                wh_code = picking_type.warehouse_id.code if picking_type.warehouse_id else 'UNA'
                
                # Year (4 digits) from scheduled date or current date
                sched_date_val = vals.get('scheduled_date') or fields.Datetime.now()
                if isinstance(sched_date_val, str):
                    sched_date = fields.Datetime.from_string(sched_date_val)
                else:
                    sched_date = sched_date_val
                year = str(sched_date.year)
                
                # Dynamic sequence part
                seq_code = 'stock.picking.consignment'
                seq_val = self.env['ir.sequence'].next_by_code(seq_code) or '00000'
                number = seq_val.split('/')[-1]
                
                # Final Name: COI/WH/YYYY/NNNNN
                vals['name'] = f"{prefix}/{wh_code}/{year}/{number}"
                
        return super().create(vals_list)
