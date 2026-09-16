# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError
import base64

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_print_pdf(self):
        """Override Odoo native Print button action to trigger direct attachment printing."""
        return self.action_direct_print_attachments()

    def action_direct_print_attachments(self):
        """Find and direct print all attachments linked to this invoice.
        If no attachment exists, automatically generate and attach the Invoice PDF first."""
        self.ensure_one()
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', self.id)
        ])

        if not attachments:
            # Generate the Invoice PDF attachment dynamically
            report = self.env.ref('account.account_invoices', raise_if_not_found=False)
            if report:
                pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf('account.account_invoices', res_ids=self.ids)
                filename = f"Invoice_{self.name.replace('/', '_')}.pdf"
                attachments = self.env['ir.attachment'].create({
                    'name': filename,
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_content),
                    'res_model': 'account.move',
                    'res_id': self.id,
                    'mimetype': 'application/pdf'
                })

        if not attachments:
            raise UserError(_("No attachment found on this invoice to print."))

        return attachments.action_direct_print()
