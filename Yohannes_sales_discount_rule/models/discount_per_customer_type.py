from odoo import _, fields, models, api
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class DiscountPerCustomerType(models.Model):
    _name = 'discount.per.customer.type'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Discount per customer Type'
    _rec_name = 'DPC_reference'

    DPC_reference = fields.Char(' Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True, readonly=True)
    category_id = fields.Many2one('res.partner.category', string='Customer Tag', required=True)
    product_category_id = fields.Many2one('product.category', string='Product Category')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True)
    percentage = fields.Float(string='Percentage (+ve or -ve)', digits=(16, 6), default=0.0,
                              help="Positive = discount, Negative = markup/surcharge")
    core = fields.Selection(
        [('core_product', 'Core Product'),
         ('non_core_product', 'None Core Product'),
         ('all', 'All')
         ], string='Core?', default=''
    )
    submitted_by = fields.Many2one('res.users', string='Submitted By', readonly=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('cancel', 'Cancel')
    ], string='State', required=True, default='draft')

    # state = fields.Selection([
    #   ('active', 'Active'),
    #  ('inactive', 'Inactive'),
    # ], string='Status', default='active', required=True)
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
            if vals.get('DPC_reference', _('New')) == _('New'):
                vals['DPC_reference'] = self.env['ir.sequence'].next_by_code('discount.per.customer.type.seq') or _(
                    'New')
        record = super().create(vals_list)
        return record

    @api.depends('category_id', 'product_category_id', 'percentage')
    def _compute_display_name(self):
        for rec in self:
            parts = []
            if rec.category_id:
                parts.append(rec.category_id.name)
            if rec.product_category_id:
                parts.append(rec.product_category_id.name)
            if rec.percentage != 0.0:
                sign = '+' if rec.percentage > 0 else '-'
                parts.append(f"{sign}{abs(rec.percentage)}%")
            rec.display_name = ' / '.join(parts) or _('New Discount Rule')


