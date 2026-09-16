from odoo import models, fields, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    peds_api_url = fields.Char(
        string='PEDS API URL', 
        default='http://localhost:8545/pedsfpsrv/api/SalesInvoice',
        help="Local URL where the PEDS Fiscal Printer Service is running."
    )
    peds_license_keys = fields.Char(
        string='PEDS License Keys',
        help="Registered License Keys for the Fiscal Printer."
    )
    peds_api_key = fields.Char(
        string='PEDS API Key',
        default='a00d2fb00aa04fa7a4e9966c6f955b40',
        help="API Key for the PEDS Fiscal Printer Service."
    )
    peds_tenant_id = fields.Char(
        string='PEDS Tenant ID',
        help="Tenant ID registered in the PEDS Fiscal Printer Service. Defaults to the company name if left empty."
    )


    @api.model
    def save_peds_license(self, keys):
        # We need to save this on the current user's company
        self.env.company.sudo().write({'peds_license_keys': keys})
        return True
