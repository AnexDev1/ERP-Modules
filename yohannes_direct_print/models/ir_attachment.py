# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError

class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    def action_direct_print(self):
        """Action method called from attachment views or backend buttons to trigger client direct print."""
        if not self:
            raise UserError(_("No attachment selected for printing."))

        attachments_data = []
        for att in self:
            attachments_data.append({
                'id': att.id,
                'name': att.name,
                'mimetype': att.mimetype or '',
                'url': f'/web/content/{att.id}?download=false',
            })

        return {
            'type': 'ir.actions.client',
            'tag': 'yohannes_direct_print_action',
            'params': {
                'attachments': attachments_data,
            }
        }
