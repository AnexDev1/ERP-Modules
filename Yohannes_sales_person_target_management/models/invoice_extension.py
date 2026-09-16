from odoo import models, fields, api

class YohannesInvoiceExtension(models.Model):
    _name = 'yohannes.invoice.extension'
    _description = 'Invoice Date Extension'

    move_id = fields.Many2one('account.move', string='Invoice', domain=[('move_type', '=', 'out_invoice')])
    extension_days = fields.Integer(string='Extension Days')
    new_due_date = fields.Date(string='New Due Date')

    @api.onchange('move_id', 'extension_days')
    def _onchange_invoice_extension(self):
        if self.move_id and self.move_id.invoice_date_due and self.extension_days:
            # Optional: auto-compute new due date? 
            # In the screenshot it seems manually entered or computed elsewhere.
            # For now, we'll leave it as manual as per typical request patterns.
            pass
