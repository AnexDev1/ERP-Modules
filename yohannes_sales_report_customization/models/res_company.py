from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    stamp_signature = fields.Image(string="Company Stamp/Signature")
    proforma_remarks = fields.Html(string="Default Pro-Forma Remarks")
