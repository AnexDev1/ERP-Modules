from odoo import models, fields, api, _

class YohannesInventoryDateChange(models.Model):
    _name = 'yohannes.inventory.date.change'
    _description = 'Inventory Date Change'

    picking_id = fields.Many2one('stock.picking', string='Reference')
    date_from = fields.Datetime(string='From date', related='picking_id.date_done', readonly=True, store=True)
    date_to = fields.Date(string='Transaction date correct')
    state = fields.Selection([('draft', 'Draft'), ('processed', 'Processed')], string='Status', default='draft')

    @api.onchange('picking_id')
    def _onchange_picking_id(self):
        pass

    def action_change_date(self):
        for rec in self:
            if not rec.picking_id or not rec.date_to:
                continue
            
            # Use sudo to bypass restrictions on date/create_date
            new_datetime = fields.Datetime.to_datetime(rec.date_to)
            
            # Update Picking
            rec.picking_id.sudo().write({
                'date_done': new_datetime,
                'scheduled_date': new_datetime
            })
            
            # Update Moves
            moves = self.env['stock.move'].sudo().search([('picking_id', '=', rec.picking_id.id)])
            moves.write({'date': new_datetime})
            
            # Update Move Lines
            move_lines = self.env['stock.move.line'].sudo().search([('picking_id', '=', rec.picking_id.id)])
            move_lines.write({'date': new_datetime})

            # Update Linked Journal Entries
            for move in moves:
                if move.account_move_id:
                    move.account_move_id.sudo().write({'date': rec.date_to})
            
            rec.state = 'processed'
