from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.depends('partner_id')
    def _compute_note(self):
        super()._compute_note()
        for order in self:
            if not order.note and order.company_id and order.company_id.proforma_remarks:
                order.note = order.company_id.proforma_remarks

    def _prepare_invoice(self):
        """Prevent Sales Order notes (proforma remarks) from carrying over to Invoice"""
        invoice_vals = super()._prepare_invoice()
        # Always clear the narration so it doesn't appear on the invoice form
        if 'narration' in invoice_vals:
            invoice_vals['narration'] = False
        return invoice_vals
