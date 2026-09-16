from odoo import _, fields, models, api
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class DiscountPerQuantityOrder(models.Model):
    _name = 'discount.per.quantity.order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Discount per Quantity Order'
    _rec_name = 'DPQ_reference'

    DPQ_reference = fields.Char(' Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Term',
                                      help="Optional: This discount applies only when this payment term is selected")
    product_id = fields.Many2one('product.product', string='Product', required=True, index=True)
    from_quantity = fields.Float(string='From Quantity', required=True, default=0.0, digits='Product Unit of Measure')
    to_quantity = fields.Float(string='To Quantity', default=0.0, digits='Product Unit of Measure',
                               help="Leave 0 for no upper limit (applies to ∞ and above)")
    percentage = fields.Float(string='Percentage (+ve or -ve)', digits=(16, 4), default=0.0,
                              help="Positive value = discount, Negative = surcharge/markup")
    # state = fields.Selection([
    #   ('active', 'Active'),
    #  ('inactive', 'Inactive'),
    # ], string='Status', default='active', required=True, tracking=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    core = fields.Selection(
        [('core_product', 'Core Product'),
         ('non_core_product', 'None Core Product'),
         ('all', 'All')
         ], string='Core?', default='all'
    )
    submitted_by = fields.Many2one('res.users', string='Submitted By', readonly=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
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
            if vals.get('DPQ_reference', _('New')) == _('New'):
                vals['DPQ_reference'] = self.env['ir.sequence'].next_by_code('discount.per.order.quantity.seq') or _('New')
        record = super().create(vals_list)
        return record

    # Optional: domain / constraint to avoid overlapping ranges per product
    @api.constrains('product_id', 'from_quantity', 'to_quantity')
    def _check_ranges(self):
        for rec in self:
            if rec.to_quantity > 0 and rec.to_quantity <= rec.from_quantity:
                raise ValidationError(_("To Quantity must be greater than From Quantity (or 0)."))

            # Prevent overlapping ranges for same product & company & payment term
            overlapping = self.search([
                ('id', '!=', rec.id),
                ('product_id', '=', rec.product_id.id),
                ('company_id', '=', rec.company_id.id),
                ('payment_term_id', '=', rec.payment_term_id.id or False),
                '|',
                ('from_quantity', '<=', rec.to_quantity or 999999999),
                ('to_quantity', '>=', rec.from_quantity),
                '|',
                ('to_quantity', '=', 0),
                ('to_quantity', '>=', rec.from_quantity),
            ])
            if overlapping:
                raise ValidationError(_("Overlapping quantity ranges detected for this product."))