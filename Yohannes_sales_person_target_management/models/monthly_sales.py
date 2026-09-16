from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
from dateutil import relativedelta
from calendar import monthrange


class MonthlySales(models.Model):
    _name = 'monthly.sales'
    _description = 'Monthly Sales Tracking'
    _rec_name = 'reference'
    _order = 'month_start_date desc'

    reference = fields.Char(string='REFERENCE', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    salesperson_id = fields.Many2one('res.users', string='Salesperson', required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    month_start_date = fields.Date(string='Month Start Date', required=True)
    month_end_date = fields.Date(string='Month End Date', required=True)
    month_name = fields.Char(string='Month', compute='_compute_month_info', store=True)
    year = fields.Integer(string='Year', compute='_compute_month_info', store=True)

    # Related records
    weekly_sales_ids = fields.One2many('weekly.sales', 'monthly_sales_id', string='Weekly Sales Records')
    daily_sales_ids = fields.One2many('daily.sales', 'monthly_sales_id', string='Daily Sales Records')
    sales_target_config_id = fields.Many2one('sales.target.config', string='Sales Target Configuration',compute='_compute_sales_target', store=True)

    # Monthly totals
    total_cash_sales = fields.Float(string='Total Cash Sales', compute='_compute_totals', store=True)
    total_credit_sales = fields.Float(string='Total Credit Sales', compute='_compute_totals', store=True)
    total_sales = fields.Float(string='Total Monthly Sales', compute='_compute_totals', store=True)
    monthly_target = fields.Float(string='Monthly Target', compute='_compute_target', store=True)
    monthly_achievement_percent = fields.Float(string='Monthly Achievement %', compute='_compute_totals', store=True)

    average_weekly_sales = fields.Float(string='Average Weekly Sales', compute='_compute_totals', store=True)
    average_daily_sales = fields.Float(string='Average Daily Sales', compute='_compute_totals', store=True)
    best_week_sales = fields.Float(string='Best Week', compute='_compute_performance', store=True)
    worst_week_sales = fields.Float(string='Worst Week', compute='_compute_performance', store=True)
    weeks_above_target = fields.Integer(string='Weeks Above Target', compute='_compute_performance', store=True)
    days_above_target = fields.Integer(string='Days Above Target', compute='_compute_performance', store=True)

    # Weekly breakdown (for charts/reports)
    week_1_sales = fields.Float(string='Week 1', compute='_compute_weekly_breakdown', store=True)
    week_2_sales = fields.Float(string='Week 2', compute='_compute_weekly_breakdown', store=True)
    week_3_sales = fields.Float(string='Week 3', compute='_compute_weekly_breakdown', store=True)
    week_4_sales = fields.Float(string='Week 4', compute='_compute_weekly_breakdown', store=True)
    week_5_sales = fields.Float(string='Week 5', compute='_compute_weekly_breakdown', store=True)


    performance_note = fields.Text(string='Monthly Performance Notes')

    @api.onchange('month_start_date')
    def _onchange_month_start_date(self):
        """Auto-calculate month end date"""
        if self.month_start_date:
            # First day of next month - 1 day = Last day of current month
            next_month = self.month_start_date.replace(day=28) + relativedelta.relativedelta(days=4)
            last_day = next_month - relativedelta.relativedelta(days=next_month.day)
            self.month_end_date = last_day


    @api.depends('salesperson_id', 'month_start_date')
    def _compute_sales_target(self):
        for record in self:
            if record.salesperson_id and record.month_start_date:
                month_start = record.month_start_date.replace(day=1)
                config = self.env['sales.target.config'].search([
                    ('user_id', '=', record.salesperson_id.id),
                    ('month_start_date', '=', month_start),
                    ('state', '=', 'active')
                ], limit=1)
                record.sales_target_config_id = config.id
            else:
                record.sales_target_config_id = False

    @api.depends('month_start_date')
    def _compute_month_info(self):
        for record in self:
            if record.month_start_date:
                record.month_name = record.month_start_date.strftime('%B')
                record.year = record.month_start_date.year
            else:
                record.month_name = False
                record.year = 0

    @api.depends('weekly_sales_ids', 'weekly_sales_ids.total_sales',
                 'weekly_sales_ids.total_cash_sales', 'weekly_sales_ids.total_credit_sales',
                 'monthly_target')
    def _compute_totals(self):
        for record in self:
            total_cash = sum(record.weekly_sales_ids.mapped('total_cash_sales'))
            total_credit = sum(record.weekly_sales_ids.mapped('total_credit_sales'))
            total_sales = total_cash + total_credit

            record.total_cash_sales = total_cash
            record.total_credit_sales = total_credit
            record.total_sales = total_sales

            # Averages
            weeks_count = len(record.weekly_sales_ids) or 1
            days_count = len(record.daily_sales_ids) or 1

            record.average_weekly_sales = total_sales / weeks_count
            record.average_daily_sales = total_sales / days_count

            # Monthly achievement
            if record.monthly_target > 0:
                record.monthly_achievement_percent = (total_sales / record.monthly_target) * 100
            else:
                record.monthly_achievement_percent = 0.0

    @api.depends('sales_target_config_id', 'sales_target_config_id.monthly_sales_target')
    def _compute_target(self):
        for record in self:
            if record.sales_target_config_id:
                record.monthly_target = record.sales_target_config_id.monthly_sales_target
            else:
                record.monthly_target = 0.0

    @api.depends('weekly_sales_ids', 'weekly_sales_ids.total_sales',
                 'weekly_sales_ids.weekly_target',
                 'daily_sales_ids', 'daily_sales_ids.total_sales',
                 'daily_sales_ids.daily_sales_target')
    def _compute_performance(self):
        for record in self:
            active_weeks = record.weekly_sales_ids
            active_days = record.daily_sales_ids

            # Weekly performance
            if active_weeks:
                week_sales = active_weeks.mapped('total_sales')
                record.best_week_sales = max(week_sales) if week_sales else 0.0
                record.worst_week_sales = min(week_sales) if week_sales else 0.0

                # Count weeks above target
                weeks_above = 0
                for week in active_weeks:
                    if week.total_sales > week.weekly_target:
                        weeks_above += 1
                record.weeks_above_target = weeks_above
            else:
                record.best_week_sales = 0.0
                record.worst_week_sales = 0.0
                record.weeks_above_target = 0

            # Days above target
            if active_days:
                days_above = 0
                for day in active_days:
                    if day.total_sales > day.daily_sales_target:
                        days_above += 1
                record.days_above_target = days_above
            else:
                record.days_above_target = 0

    @api.depends('weekly_sales_ids', 'weekly_sales_ids.total_sales', 'weekly_sales_ids.week_number')
    def _compute_weekly_breakdown(self):
        for record in self:
            # Initialize to 0
            record.week_1_sales = 0.0
            record.week_2_sales = 0.0
            record.week_3_sales = 0.0
            record.week_4_sales = 0.0
            record.week_5_sales = 0.0

            if not record.month_start_date:
                continue

            # Group by week number relative to month
            for weekly in record.weekly_sales_ids:
                week_in_month = self._get_week_in_month(weekly.week_start_date, record.month_start_date)
                sales_amount = weekly.total_sales

                if week_in_month == 1:
                    record.week_1_sales += sales_amount
                elif week_in_month == 2:
                    record.week_2_sales += sales_amount
                elif week_in_month == 3:
                    record.week_3_sales += sales_amount
                elif week_in_month == 4:
                    record.week_4_sales += sales_amount
                elif week_in_month == 5:
                    record.week_5_sales += sales_amount

    def _get_week_in_month(self, date, month_start):
        """Calculate which week of the month a date falls in (1-5)"""
        if isinstance(date, str):
            date = fields.Date.from_string(date)

        # Calculate days from month start
        days_from_start = (date - month_start).days

        # Calculate week number (1-5)
        week_number = (days_from_start // 7) + 1

        return min(week_number, 5)  # Cap at 5 weeks
