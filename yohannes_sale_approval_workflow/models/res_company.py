from odoo import models, fields, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    enable_order_source = fields.Boolean(
        string='Enable Order Source',
        default=True,
        help="Check this box to require and show the Order Source field on Sales Orders."
    )

    use_so_manual_sequence_limit = fields.Boolean(
        string='Use Sales Order Manual Sequence Limit',
        default=False,
        help="When enabled, Sales Order numbers will start after the configured manual limit."
    )
    so_manual_sequence_limit = fields.Integer(
        string='Sales Order Last Manual Limit',
        default=0,
        help="The last manual sales order number. Auto-generated sales orders will start from limit + 1."
    )

    def write(self, vals):
        res = super().write(vals)
        for company in self:
            if company.use_so_manual_sequence_limit and company.so_manual_sequence_limit > 0:
                target_next = company.so_manual_sequence_limit + 1
                seq_ids = self.env['ir.sequence'].sudo().search([
                    ('code', '=', 'sale.order'),
                    ('company_id', 'in', [company.id, False])
                ], order='company_id')
                if seq_ids:
                    seq = seq_ids[0]
                    self.env.cr.execute(f"ALTER SEQUENCE ir_sequence_{seq.id:03d} RESTART WITH {target_next};")
                    seq.sudo().write({'number_next': target_next})
                    seq.invalidate_recordset()
        return res


