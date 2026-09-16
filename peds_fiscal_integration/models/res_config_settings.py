from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    peds_api_url = fields.Char(
        related='company_id.peds_api_url', 
        readonly=False,
        string='PEDS API URL',
        help="The local URL of the PEDS Fiscal Printer Service."
    )
    peds_license_keys = fields.Char(
        related='company_id.peds_license_keys',
        readonly=False,
        string='PEDS License Keys',
        help="Registered License Keys for the Fiscal Printer."
    )
    peds_api_key = fields.Char(
        related='company_id.peds_api_key',
        readonly=False,
        string='PEDS API Key',
        help="API Key for the PEDS Fiscal Printer Service."
    )
