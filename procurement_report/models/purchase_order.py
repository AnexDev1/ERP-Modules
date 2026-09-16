from odoo import models, fields, api

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    proforma_invoice_no_report = fields.Char(related='foreign_rfq_id.proforma_invoice_no', string="PI Number", store=False)
    proforma_invoice_date_report = fields.Date(related='foreign_rfq_id.proforma_invoice_date', string="PI Date", store=False)
    date_rfq_report = fields.Date(related='foreign_rfq_id.date_rfq', string="RFQ Date", store=False)
    
    lc_number_report = fields.Char(string="LC Number", compute='_compute_lc_info_report')
    lc_issue_date_report = fields.Date(string="LC Issue Date", compute='_compute_lc_info_report')
    lc_status_report = fields.Selection([
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('active', 'Active'),
        ('amended', 'Amended'),
        ('expired', 'Expired'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], string="LC Status", compute='_compute_lc_info_report')

    requested_by_report = fields.Char(string="Requested By", compute='_compute_requested_by_report')

    def _compute_lc_info_report(self):
        for rec in self:
            lc = rec.lc_ids[:1]
            if lc:
                rec.lc_number_report = lc.lc_number
                rec.lc_issue_date_report = lc.issue_date
                rec.lc_status_report = lc.state
            else:
                rec.lc_number_report = False
                rec.lc_issue_date_report = False
                rec.lc_status_report = False

    def _compute_requested_by_report(self):
        for rec in self:
            res = False
            if rec.foreign_purchase_request_id:
                res = rec.foreign_purchase_request_id.requested_by.name
            elif rec.foreign_rfq_id and rec.foreign_rfq_id.requisition_id:
                res = rec.foreign_rfq_id.requisition_id.requested_by.name
            elif rec.local_purchase_request_id:
                res = rec.local_purchase_request_id.requested_by.name
            rec.requested_by_report = res
