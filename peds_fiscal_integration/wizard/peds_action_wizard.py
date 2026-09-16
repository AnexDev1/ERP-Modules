from odoo import models, fields, api, _

class PedsActionWizard(models.TransientModel):
    _name = 'peds.action.wizard'
    _description = 'PEDS Fiscal Printer Operations'

    action_type = fields.Selection([
        # Reports → route to /pedsfpsrv/api/reportsprinting/<endpoint>
        ('printzreport', 'Z-Daily Sales Report'),
        ('printzdailyclosingreport', 'Daily Closing Report'),
        ('printclerkreport', 'Clerk Report'),
        ('printxdailysalesreport', 'X-Daily Sales Report'),
        ('printzaccumulatedreport', 'Z Accumulated Sales Report'),
        ('printxaccumulatedreport', 'X Accumulated Sales Report'),
        ('printfullfiscalreportbyz', 'Full Fiscal Report By Z'),
        ('printfullfiscalreportbydate', 'Full Fiscal Report By Date'),
        ('printsummaryfiscalreportbyz', 'Summary Fiscal Report By Z'),
        ('printsummaryfiscalreportbydate', 'Summary Fiscal Report By Date'),
        # Invoice ops → route to /pedsfpsrv/api/SalesInvoice/<endpoint>
        ('GetInvoicePrintStatus', 'Get Invoice Print Status'),
        ('SetInvoiceAsPrinted', 'Set Invoice As Printed'),
    ], string='Operation', required=True, default='printzreport')

    from_z = fields.Integer(string='From Z Number')
    to_z = fields.Integer(string='To Z Number')
    
    date_from = fields.Date(string='Start Date')
    date_to = fields.Date(string='End Date')

    move_id = fields.Many2one('account.move', string='Invoice', domain="[('move_type', 'in', ('out_invoice', 'out_refund'))]")
    transaction_id = fields.Char(string='Transaction ID')
    fp_machine_id = fields.Char(string='FP Machine ID')
    fs_invoice_number = fields.Char(string='FS Invoice Number')
    ej_number = fields.Char(string='EJ Number')
    date_printed = fields.Datetime(string='Date Printed')

    @api.onchange('move_id')
    def _onchange_move_id(self):
        if self.move_id:
            self.transaction_id = str(self.move_id.id)
            self.fp_machine_id = self.move_id.peds_fp_machine_id or ""
            self.fs_invoice_number = self.move_id.peds_fs_invoice_number or ""
            self.ej_number = self.move_id.peds_ej_number or ""
            self.date_printed = self.move_id.peds_time_stamp or fields.Datetime.now()

    # Report-type operations that use /pedsfpsrv/api/reportsprinting/ base path
    _REPORT_ACTION_TYPES = [
        'printzreport', 'printzdailyclosingreport', 'printclerkreport',
        'printxdailysalesreport', 'printzaccumulatedreport', 'printxaccumulatedreport',
        'printfullfiscalreportbyz', 'printfullfiscalreportbydate',
        'printsummaryfiscalreportbyz', 'printsummaryfiscalreportbydate',
    ]

    def action_execute(self):
        self.ensure_one()
        import re
        # Strip down to host:port — JS will build the full API path
        raw_url = self.env.company.peds_api_url or 'http://localhost:8545'
        base_url = re.sub(r'(/pedsfpsrv.*)$', '', raw_url.rstrip('/'))

        is_report = self.action_type in self._REPORT_ACTION_TYPES

        return {
            'type': 'ir.actions.client',
            'tag': 'peds_fiscal_print',
            'params': {
                'base_url': base_url,
                'is_wizard': True,
                'is_report': is_report,
                'action_type': self.action_type,
                'from_z': self.from_z,
                'to_z': self.to_z,
                'date_from': self.date_from.strftime('%Y-%m-%d') if self.date_from else '',
                'date_to': self.date_to.strftime('%Y-%m-%d') if self.date_to else '',
                'transaction_id': self.transaction_id or "",
                'fp_machine_id': self.fp_machine_id or "",
                'fs_invoice_number': self.fs_invoice_number or "",
                'ej_number': self.ej_number or "",
                'date_printed': self.date_printed.strftime("%Y-%m-%d %H:%M:%S") if self.date_printed else "",
                'tenant_id': self.env.company.name or "",
                'api_key': self.env.company.peds_api_key or "",
                'auth_license_key': self.env.company.peds_license_keys or self.env.company.peds_api_key or "",
            }
        }

import logging
_logger = logging.getLogger(__name__)

class PedsLicenseWizard(models.TransientModel):
    _name = 'peds.license.wizard'
    _description = 'PEDS License Registration'

    def _default_license_keys(self):
        return self.env.company.peds_license_keys

    license_keys = fields.Char(string='License Keys', required=True, default=_default_license_keys, help='Comma separated keys e.g. Key1, Key2')

    def action_execute(self):
        self.ensure_one()
        api_url = self.env.company.peds_api_url or 'http://localhost:8545/pedsfpsrv/api/SalesInvoice'
        if api_url.endswith('/'):
            api_url = api_url[:-1]

        return {
            'type': 'ir.actions.client',
            'tag': 'peds_fiscal_print',
            'params': {
                'api_url': api_url,
                'is_wizard': True,
                'action_type': 'RegisterLicenseKeys',
                'license_keys': self.license_keys,
                'api_key': self.env.company.peds_api_key or "",
                'auth_license_key': self.env.company.peds_license_keys or self.env.company.peds_api_key or "",
            }
        }
