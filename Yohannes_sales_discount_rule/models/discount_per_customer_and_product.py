from odoo import _, fields, models, api
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class DiscountPerCustomerAndProduct(models.Model):
    _name = 'discount.per.customer.and.product'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Discount per customer and product'
    _rec_name = 'DPCP_reference'

    DPCP_reference = fields.Char(' Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company,
                                 index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True, index=True, ondelete='cascade')
    #partner_id = fields.Many2one('res.partner', string='Customer', required=True, index=True,
     #                            domain=[('type', '=', 'contact'), ('is_company', '=', False)], ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, index=True, ondelete='cascade')
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Term',
                                      help="If set, this rule only applies when the sales order uses this payment term.")
    percentage = fields.Float(string='Percentage (+ve = discount, -ve = surcharge)', digits=(16, 4), default=0.0)
    submitted_by = fields.Many2one('res.users', string='Submitted By', readonly=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    # state = fields.Selection([
    # ('active', 'Active'),
    # ('inactive', 'Inactive')
    # ], string='Status',default='active',required=True,tracking=True)
    display_name = fields.Char(compute='_compute_display_name', store=True, index=True)

    @api.depends('partner_id', 'product_id', 'percentage')
    def _compute_display_name(self):
        for rec in self:
            partner_name = rec.partner_id.name or _('New Customer')
            product_name = rec.product_id.name or _('New Product')
            perc_str = f"{rec.percentage:+.2f}%" if rec.percentage != 0 else "0%"
            rec.display_name = f"{partner_name} - {product_name} → {perc_str}"

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('cancel', 'Cancel')
    ], string='State', required=True, default='draft')

    def action_submit(self):
        self.ensure_one()
        if not self.submitted_by:
            self.write({'submitted_by': self.env.user.id})
        self.write({'state': 'submitted'})

    def action_approved(self):
        self.ensure_one()
        if not self.approved_by:
            self.write({'approved_by': self.env.user.id})
        self.write({'state': 'approved'})

    def action_reject(self):
        self.write({'state': 'cancel'})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('DPCP_reference', _('New')) == _('New'):
                vals['DPCP_reference'] = self.env['ir.sequence'].next_by_code(
                    'discount.per.customer.and.product.seq') or _(
                    'New')
        record = super().create(vals_list)
        return record

    @api.constrains('partner_id', 'product_id', 'payment_term_id', 'company_id')
    def _check_unique_rule(self):
        for rec in self:
            domain = [
                ('id', '!=', rec.id),
                ('partner_id', '=', rec.partner_id.id),
                ('product_id', '=', rec.product_id.id),
                ('payment_term_id', '=', rec.payment_term_id.id or False),
                ('company_id', '=', rec.company_id.id),
                ('state', '=', 'active'),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    _("Duplicate rule detected: same customer + product + payment term already exists.")
                )
