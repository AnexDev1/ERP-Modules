from odoo import _, fields, models, api
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class DiscountPerSalesAmount(models.Model):
    _name = 'discount.per.sales.amount'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Discount per sales amount'
    _rec_name = 'DPA_reference'

    DPA_reference = fields.Char(' Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Term',
                                      help="Optional: Link this discount slab to a specific payment term")
    from_amount = fields.Monetary(string='From Amount', required=True, default=0.0, currency_field='currency_id')
    to_amount = fields.Monetary(string='To Amount', default=0.0, currency_field='currency_id',
                                help="Leave 0 or empty for no upper limit (∞)")
    percentage = fields.Float(string='Percentage (+ve or -ve)', digits=(16, 4), default=0.0,
                              help="Positive = discount, Negative = surcharge/markup")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True, string='Currency')
    core = fields.Selection(
        [('core_product', 'Core Product'),
         ('non_core_product', 'None Core Product'),
         ('all', 'All')
         ], string='Core?', default=''
    )
    submitted_by = fields.Many2one('res.users', string='Submitted By', readonly=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    # state = fields.Selection([
    #   ('active', 'Active'),
    #  ('inactive', 'Inactive'),
    # ], string='Status', default='active', required=True, tracking=True)
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
            if vals.get('DPA_reference', _('New')) == _('New'):
                vals['DPA_reference'] = self.env['ir.sequence'].next_by_code('discount.per.sales.amount.seq') or _('New')
        record = super().create(vals_list)
        return record

    @api.depends('from_amount', 'to_amount', 'percentage', 'core')
    def _compute_display_name(self):
        for rec in self:
            to_amount_str = f"{rec.to_amount:,.2f}" if rec.to_amount else "∞"
            range_str = f"{rec.from_amount:,.2f} - {to_amount_str}"
            perc_str = f"{rec.percentage:+.2f}%" if rec.percentage != 0 else "0%"
            core_str = f" ({rec.core})" if rec.core and rec.core != 'all' else ""
            rec.display_name = f"{range_str} → {perc_str}{core_str}"