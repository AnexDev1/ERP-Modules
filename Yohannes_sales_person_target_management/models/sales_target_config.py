from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
from dateutil import relativedelta


class SalesTargetConfig(models.Model):
    _name = 'sales.target.config'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Sales Target Configuration'
    _rec_name = 'reference'

    reference = fields.Char(string='REFERENCE', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    user_id = fields.Many2one('res.users', string='Salesperson', required=True, )
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    daily_sale_ids = fields.One2many('sales.target.config.line', 'target_config_id', string='Daily Sales Entries')
    active = fields.Boolean(default=True)
    date = fields.Date(string='Target Date', default=fields.Date.today, required=True,
                       help='The date for which this sales target applies')
    week1_sales_target = fields.Float(string='Week 1 Sales Target', compute='_compute_weekly_sales_target', store=True)
    week2_sales_target = fields.Float(string='Week 2 Sales Target', compute='_compute_weekly_sales_target', store=True)
    week3_sales_target = fields.Float(string='Week 3 Sales Target', compute='_compute_weekly_sales_target', store=True)
    week4_sales_target = fields.Float(string='Week 4 Sales Target', compute='_compute_weekly_sales_target', store=True)
    month_start_date = fields.Date(string='Month Start Date', default=lambda self: fields.Date.today().replace(day=1),
                                   required=True)
    month_end_date = fields.Date(string='Month End Date', compute='_compute_month_end_date', store=True)
    daily_sales_target = fields.Float(string='Daily Sales Target')
    monthly_sales_target = fields.Float(string='Monthly Sales Target', compute='_compute_monthly_sales_target',
                                        store=True, readonly=True)
    month_name = fields.Char(string='Month', compute='_compute_month_name', store=True)

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('active', 'active'),
            ('expire', 'Expire'),

        ], string='Status', default='draft', tracking=True,
    )

    # def action_active(self):
    # self.write({'state': 'active'})
    def action_active(self):
        """Activate the sales target with validation for unique monthly target per salesperson"""
        for record in self:
            # Check if there's already an active target for the same salesperson in the same month
            if record.month_start_date and record.user_id:
                # Find the month start and end dates
                month_start = record.month_start_date.replace(day=1)
                month_end = month_start + relativedelta.relativedelta(months=1, days=-1)

                # Search for existing active targets for the same user in the same month
                existing_active_targets = self.search([
                    ('user_id', '=', record.user_id.id),
                    ('month_start_date', '=', month_start),
                    ('state', '=', 'active'),
                    ('id', '!=', record.id),
                ])

                if existing_active_targets:
                    raise ValidationError(
                        f"Salesperson {record.user_id.name} already has an active sales target for {month_start.strftime('%B %Y')}. "
                        f"You cannot activate another target for the same month."
                    )

            # If validation passes, activate the record
            record.write({'state': 'active'})

    def action_expire(self):
        """Manually expire the target"""
        self.write({'state': 'expire'})

    def expire_past_targets(self):
        """Automatically expire targets whose month has passed"""
        today = fields.Date.today()
        # Find all active targets where month_end_date is in the past
        expired_targets = self.search([
            ('state', '=', 'active'),
            ('month_end_date', '<', today),
        ])

        if expired_targets:
            expired_targets.write({'state': 'expire'})
            return f"Expired {len(expired_targets)} target(s)"
        return "No targets to expire"

    def action_reset_to_draft(self):
        """Reset expired target back to draft"""
        self.write({'state': 'draft'})

    @api.depends('month_start_date', 'month_end_date')
    def _compute_month_name(self):
        for record in self:
            if record.month_start_date:
                # Example: January 2025
                record.month_name = record.month_start_date.strftime('%B %Y')
            else:
                record.month_name = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code('sales.target.config') or _('New')
        return super(SalesTargetConfig, self).create(vals_list)

    @api.depends('month_start_date')
    def _compute_month_end_date(self):
        """Compute last day of the given month"""
        for record in self:
            if record.month_start_date:
                record.month_end_date = record.month_start_date + relativedelta.relativedelta(months=1, days=-1)
            else:
                record.month_end_date = False

    # @api.depends('week_start_date')
    # def _compute_week_end_date(self):
    #   for record in self:
    #      if record.week_start_date:
    #         record.week_end_date = record.week_start_date + relativedelta.relativedelta(days=6)
    #    else:
    #       record.week_end_date = False
    @api.constrains('daily_sales_target')
    def _check_positive_target(self):
        for record in self:
            if record.daily_sales_target < 0:
                raise ValidationError("Daily sales target cannot be negative.")

    @api.constrains('user_id', 'date')
    def _check_unique_target_per_user_per_day(self):
        for record in self:
            existing = self.search([
                ('user_id', '=', record.user_id.id),
                ('date', '=', record.date),
                ('id', '!=', record.id),
            ])
            if existing:
                raise ValidationError(
                    f"A sales target already exists for {record.user_id.name} on {record.date}."
                )

    @api.depends('daily_sale_ids.daily_sales_target', 'daily_sale_ids.date', 'month_start_date', 'month_end_date')
    def _compute_weekly_sales_target(self):
        """Divide sales target into Week1-Week4 based on month ranges"""
        for record in self:
            w1, w2, w3, w4 = 0.0, 0.0, 0.0, 0.0
            if record.month_start_date and record.month_end_date:
                # Define week ranges from month start
                start_date = record.month_start_date
                week1_end = start_date + relativedelta.relativedelta(days=6)
                week2_end = week1_end + relativedelta.relativedelta(days=7)
                week3_end = week2_end + relativedelta.relativedelta(days=7)
                week4_end = record.month_end_date  # up to end of month

                for line in record.daily_sale_ids:
                    if line.date:
                        if start_date <= line.date <= week1_end:
                            w1 += line.daily_sales_target
                        elif week1_end < line.date <= week2_end:
                            w2 += line.daily_sales_target
                        elif week2_end < line.date <= week3_end:
                            w3 += line.daily_sales_target
                        elif week3_end < line.date <= week4_end:
                            w4 += line.daily_sales_target

            record.week1_sales_target = w1
            record.week2_sales_target = w2
            record.week3_sales_target = w3
            record.week4_sales_target = w4

    @api.depends('daily_sale_ids.daily_sales_target', 'month_start_date')
    def _compute_monthly_sales_target(self):
        """Sum all daily sales targets for the configured month"""
        for record in self:
            record.monthly_sales_target = sum(record.daily_sale_ids.mapped('daily_sales_target'))

    def action_set_and_distribute_monthly_target(self, amount):
        """Sets the monthly target and distributes it equally across all daily lines."""
        self.ensure_one()
        if not self.daily_sale_ids:
            self._onchange_month_start_date()  # Populate lines if missing

        num_days = len(self.daily_sale_ids)
        if num_days > 0:
            daily_target = amount / num_days
            self.daily_sale_ids.write({'daily_sales_target': daily_target})
            # Ensure the config is activated
            if self.state == 'draft':
                self.action_active()
        return True

    @api.onchange('month_start_date')
    def _onchange_month_start_date(self):
        """Auto-populate daily sales lines for the selected month"""
        if self.month_start_date:
            # Ensure start date is the first of the month
            start_date = self.month_start_date.replace(day=1)
            # Find last day of the month
            end_date = start_date + relativedelta.relativedelta(months=1, days=-1)

            # Prepare list of dates
            lines = []
            current_date = start_date
            while current_date <= end_date:
                lines.append((0, 0, {
                    'date': current_date,
                    'daily_sales_target': 0.0,
                }))
                current_date += relativedelta.relativedelta(days=1)

            # Reset the lines
            self.daily_sale_ids = [(5, 0, 0)] + lines


class SalesTargetConfigline(models.Model):
    _name = 'sales.target.config.line'
    _description = 'Sales Target Configuration Line'

    date = fields.Date(string='Target Date', required=True,
                       help='The date for which this sales target applies')
    monthly_sales_target = fields.Float(string='Monthly Target')
    target_config_id = fields.Many2one('sales.target.config', string='Target Configuration', required=True,
                                       ondelete='cascade')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    daily_sales_target = fields.Float(string='Daily Sales Target', required=True)
    daily_sales_id = fields.One2many('daily.sales', 'sales_target_id', string='Daily Sales Entries')

    @api.model
    def get_target_for_date_salesperson(self, date, salesperson_id):
        """Get daily sales target for specific date and salesperson"""
        target_line = self.search([
            ('date', '=', date),
            ('target_config_id.user_id', '=', salesperson_id),
            ('target_config_id.state', '=', 'active')
        ], limit=1)

        return target_line.daily_sales_target if target_line else 0.0

    @api.model
    def get_target_line_for_date_salesperson(self, date, salesperson_id):
        """Get target line for specific date and salesperson"""
        return self.search([
            ('date', '=', date),
            ('target_config_id.user_id', '=', salesperson_id),
            ('target_config_id.state', '=', 'active')
        ], limit=1)

    def validate_for_daily_sales(self, daily_sales_record):
        """Validate if this target line can be used for the daily sales record"""
        if self.date != daily_sales_record.date:
            return False
        if self.target_config_id.user_id.id != daily_sales_record.salesperson_id.id:
            return False
        if self.target_config_id.state != 'active':
            return False
        return True

    @api.constrains('date', 'target_config_id')
    def _check_date_within_month(self):
        for line in self:
            if line.target_config_id:
                start_date = line.target_config_id.month_start_date
                end_date = line.target_config_id.month_end_date
                if line.date and (line.date < start_date or line.date > end_date):
                    raise ValidationError(
                        f"The daily sales target date {line.date} must be within the month: {start_date} to {end_date}."
                    )

    @api.constrains('daily_sales_target')
    def _check_positive_target(self):
        for record in self:
            if record.daily_sales_target < 0:
                raise ValidationError("Daily sales target in line cannot be negative.")
