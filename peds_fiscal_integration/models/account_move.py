from odoo import models, fields, api, _
from odoo.exceptions import UserError
import datetime

class AccountMove(models.Model):
    _inherit = 'account.move'

    peds_printed = fields.Boolean(
        string='PEDS Printed', 
        default=False,
        copy=False,
        help="Indicates if the fiscal invoice has been printed successfully via PEDS."
    )
    peds_fp_machine_id = fields.Char(string='FP Machine ID', copy=False, readonly=True)
    peds_fs_invoice_number = fields.Char(string='FS Invoice Number', copy=False, readonly=True)
    peds_ej_number = fields.Char(string='EJ Number', copy=False, readonly=True)
    peds_time_stamp = fields.Datetime(string='Fiscal Time Stamp', copy=False, readonly=True)
    is_manual_invoice = fields.Boolean(
        string='Manual Invoice', 
        default=False, 
        copy=False,
        help="Check this if this invoice does not need to be printed via the PEDS fiscal printer."
    )
    manual_receipt_reference = fields.Char(
        string='Manual Receipt Reference',
        copy=False,
        help="The physical receipt number for this manual invoice."
    )

    @api.onchange('fs_no')
    def _onchange_fs_no(self):
        if self.fs_no and not self.manual_receipt_reference:
            self.manual_receipt_reference = self.fs_no

    @api.onchange('manual_receipt_reference')
    def _onchange_manual_receipt_reference(self):
        if self.manual_receipt_reference and hasattr(self, 'fs_no') and not self.fs_no:
            self.fs_no = self.manual_receipt_reference


    def action_post(self):
        for move in self:
            if move.move_type in ('out_invoice', 'out_refund'):
                if not move.is_manual_invoice and not self.env.context.get('auto_post_peds'):
                    raise UserError(_("You cannot manually post a non-manual fiscal invoice. Please use the 'Print Fiscal Invoice' button instead."))
        return super(AccountMove, self).action_post()

    def action_print_peds_fiscal(self):
        self.ensure_one()

        # Validate API key is configured — this is the ONLY thing required to print.
        # License key registration is NOT required (confirmed working via Postman without it).
        api_key = self.company_id.peds_api_key
        if not api_key:
            raise UserError(_(
                "PEDS API Key is not configured for company '%s'.\n"
                "Please go to Settings → Company → PEDS and enter the API Key."
            ) % self.company_id.name)

        if self.state == 'draft':
            self.with_context(auto_post_peds=True).action_post()
        
        # Determine payment type from the invoice's sale_type field
        # ('cash' or 'credit') set by the yohannes_sales_customer_credit_limit module
        payment_type = 'Credit' if self.sale_type == 'credit' else 'Cash'

        # Build invoice header
        license_val = self.company_id.peds_license_keys or api_key
        invoice_data = {
            "TenantId": self.company_id.peds_tenant_id or self.company_id.name or "Odoo",
            "ThirdPartyID": "Odoo",
            "TransactionID": str(self.id),
            "ReferenceNumber": self.name or "",
            "PaymentType": payment_type,
            "PaidVia": payment_type,
            "PaymentReferenceNumber": self.payment_reference or self.name or "",
            "BuyerName": self.partner_id.name or "Cash Customer",
            "BuyerTaxIdNumber": self.partner_id.vat or "",
            "AddOnType": "percentage",
            "AddOnValue": 0,
            "DiscountType": "fixed",
            "DiscountValue": 0,
            "UserName": self.env.user.name or "",
            "HeaderMemo": "",
            "FooterMemo": "",
            "TimeStamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "LineItem": []
        }

        # Build invoice detail
        index = 1
        # Exclude section and note lines — all other lines are product/service lines
        product_lines = self.invoice_line_ids.filtered(
            lambda l: l.display_type not in ('line_section', 'line_note')
        )
        for line in product_lines:
            item_id = line.product_id.default_code or line.product_id.name or "ITEM"
            short_name = (line.product_id.name or line.name or "ITEM")[:30]

            tax_rate = 0.0
            if line.tax_ids:
                tax_rate = line.tax_ids[0].amount

            qty = float(line.quantity if hasattr(line, 'quantity') else line.product_uom_qty or 1)

            line_data = {
                "ItemTransactionId": str(line.id),
                "LineIndex": str(index),
                "ItemID": item_id,
                "ItemShortName": short_name,
                "ItemDescription": line.name or "",
                "UnitName": line.product_uom_id.name if line.product_uom_id else "Pcs",
                "Quantity": qty,
                "UnitPrice": float(line.price_unit),
                "TaxRate": float(tax_rate),
                "AddOnType": "fixed",
                "AddOnValue": 0,
                "DiscountType": "fixed",
                "DiscountValue": 0
            }
            invoice_data["LineItem"].append(line_data)
            index += 1

        api_url = (self.company_id.peds_api_url or 'http://localhost:8545/pedsfpsrv/api/SalesInvoice').strip()
        # Ensure it does not end with a slash or duplicate endpoint
        if api_url.endswith('/'):
            api_url = api_url[:-1]
        if api_url.endswith('/PrintInvoice'):
            api_url = api_url[:-13]

        # Return a client action to execute in the client's browser
        return {
            'type': 'ir.actions.client',
            'tag': 'peds_fiscal_print',
            'params': {
                'api_url': api_url,
                'endpoint': '/PrintInvoice',
                'method': 'POST',
                'payload': invoice_data,
                'api_key': api_key,
                'auth_license_key': license_val,
                'query_params': {'printCopy': 'false'},
                'success_msg': _('Invoice printed successfully!')
            }
        }

    @api.model
    def mark_peds_printed(self, transaction_id, fp_machine_id=False, fs_invoice_number=False, ej_number=False, time_stamp=False):
        # TransactionID is the move id
        try:
            try:
                move_id = int(transaction_id)
            except (ValueError, TypeError):
                return False

            move = self.browse(move_id)
            if move.exists():
                vals = {'peds_printed': True}
                if fp_machine_id:
                    vals['peds_fp_machine_id'] = str(fp_machine_id)
                    if hasattr(move, 'machine_id'):
                        vals['machine_id'] = str(fp_machine_id)
                if fs_invoice_number:
                    vals['peds_fs_invoice_number'] = str(fs_invoice_number)
                    if hasattr(move, 'fs_no'):
                        vals['fs_no'] = str(fs_invoice_number)
                if ej_number:
                    vals['peds_ej_number'] = str(ej_number)
                if time_stamp and isinstance(time_stamp, str):
                    try:
                        clean_ts = time_stamp.replace('T', ' ').split('.')[0]
                        vals['peds_time_stamp'] = clean_ts
                    except Exception:
                        pass
                move.sudo().write(vals)

                return True
        except Exception as e:
            # Fallback sudo write on minimal field if full write failed
            try:
                move = self.sudo().browse(int(transaction_id))
                if move.exists():
                    move.sudo().write({'peds_printed': True})
                    return True
            except Exception:
                pass
        return False
