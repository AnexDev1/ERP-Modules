from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
from dateutil import relativedelta
from calendar import monthrange


class WeeklySales(models.Model):
    _name = 'weekly.sales'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Weekly Sales Tracking'
    _rec_name = 'reference'
    _order = 'week_start_date desc'

    reference = fields.Char(string='REFERENCE', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    salesperson_id = fields.Many2one('res.users', string='Salesperson', required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    week_start_date = fields.Date(string='Week Start Date', required=True)
    week_end_date = fields.Date(string='Week End Date', compute='_compute_week_end_date', store=True)
    week_number = fields.Integer(string='Week Number', compute='_compute_week_info', store=True)
    week_name = fields.Char(string='Week Name', compute='_compute_week_info', store=True)

    # Link to monthly record
    monthly_sales_id = fields.Many2one('monthly.sales', string='Monthly Record', readonly=True, ondelete='set null')

    # Related daily records
    target_config_id = fields.Many2one('sales.target.config', string='Target Configuration',
                                       compute='_compute_target_info', store=True)
    daily_sales_ids = fields.One2many('daily.sales', 'weekly_sales_id', string='Daily Sales Records')

    # Weekly totals
    total_cash_sales = fields.Float(string='Total Cash Sales', compute='_compute_totals', store=True)
    total_credit_sales = fields.Float(string='Total Credit Sales', compute='_compute_totals', store=True)
    total_sales = fields.Float(string='Total Weekly Sales', compute='_compute_totals', store=True)

    # Weekly target and achievement
    weekly_target = fields.Float(string='Weekly Target', compute='_compute_weekly_target', store=True)
    # weekly_target = fields.Float(string='Weekly Target', compute='_compute_target', store=True)
    # weekly_target_from_config = fields.Float(string='Target from Config', compute='_compute_weekly_target_from_config', store=True)
    weekly_achievement_percent = fields.Float(string='Weekly Achievement %', compute='_compute_totals', store=True)

    # Performance metrics
    average_daily_sales = fields.Float(string='Average Daily Sales', compute='_compute_totals', store=True)
    best_day_sales = fields.Float(string='Best Day', compute='_compute_performance', store=True)
    worst_day_sales = fields.Float(string='Worst Day', compute='_compute_performance', store=True)
    days_above_target = fields.Integer(string='Days Above Target', compute='_compute_performance', store=True)

    # Daily breakdown
    monday_sales = fields.Float(string='Monday', compute='_compute_daily_breakdown', store=True)
    tuesday_sales = fields.Float(string='Tuesday', compute='_compute_daily_breakdown', store=True)
    wednesday_sales = fields.Float(string='Wednesday', compute='_compute_daily_breakdown', store=True)
    thursday_sales = fields.Float(string='Thursday', compute='_compute_daily_breakdown', store=True)
    friday_sales = fields.Float(string='Friday', compute='_compute_daily_breakdown', store=True)
    saturday_sales = fields.Float(string='Saturday', compute='_compute_daily_breakdown', store=True)
    sunday_sales = fields.Float(string='Sunday', compute='_compute_daily_breakdown', store=True)

    performance_note = fields.Text(string='Weekly Performance Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code('weekly.sales') or _('New')

            # Find or create monthly record
            if vals.get('week_start_date') and vals.get('salesperson_id'):
                monthly_sales = self._find_or_create_monthly_sales(
                    vals['salesperson_id'], vals['week_start_date'])
                if monthly_sales:
                    vals['monthly_sales_id'] = monthly_sales.id
        return super(WeeklySales, self).create(vals_list)

    def write(self, vals):
        result = super(WeeklySales, self).write(vals)

        # Update monthly totals if needed
        if any(field in vals for field in ['week_start_date', 'salesperson_id']):
            for record in self:
                if record.monthly_sales_id:
                    record.monthly_sales_id._compute_totals()

        return result

    # ============================
    # COMPUTE METHODS
    # ============================
    @api.model
    def _get_week_in_month(self, date):
        """Get week number (1-4) within the month"""
        day = date.day
        if day <= 7:
            return 1
        elif day <= 14:
            return 2
        elif day <= 21:
            return 3
        else:
            return 4

    @api.depends('week_start_date')
    def _compute_week_info(self):
        for record in self:
            if record.week_start_date:
                record.week_number = self._get_week_in_month(record.week_start_date)
            else:
                record.week_number = 0

    @api.depends('week_start_date')
    def _compute_week_end_date(self):
        """Automatically calculate week end date (6 days after start date)"""
        for record in self:
            if record.week_start_date:
                # Week end date is 6 days after start date (Monday to Sunday)
                record.week_end_date = record.week_start_date + timedelta(days=6)
            else:
                record.week_end_date = False

    @api.onchange('week_start_date', 'salesperson_id')
    def _onchange_week_start_date(self):
        """Auto-populate week end date, week number, and daily sales"""
        if self.week_start_date:
            # Calculate end date locally to ensure availability for search
            week_end = self.week_start_date + timedelta(days=6)
            self.week_end_date = week_end
            self.week_number = self._get_week_in_month(self.week_start_date)

            if self.salesperson_id:
                daily_sales = self.env['daily.sales'].search([
                    ('salesperson_id', '=', self.salesperson_id.id),
                    ('date', '>=', self.week_start_date),
                    ('date', '<=', week_end)
                ])
                self.daily_sales_ids = [(6, 0, daily_sales.ids)]
            else:
                self.daily_sales_ids = [(5, 0, 0)]
        else:
            self.week_end_date = False
            self.week_number = 0
            self.daily_sales_ids = [(5, 0, 0)]

    def action_fetch_daily_sales(self):
        """Manually fetch and link daily sales records"""
        for record in self:
            record._onchange_week_start_date()
        return True

    @api.depends('salesperson_id', 'week_start_date')
    def _compute_target_info(self):
        """Find the target configuration for the salesperson and month"""
        for record in self:
            if record.salesperson_id and record.week_start_date:
                # Find month of the week
                month_start = record.week_start_date.replace(day=1)
                month_end = month_start + relativedelta.relativedelta(months=1, days=-1)

                # Find active target configuration for this salesperson and month
                target_config = self.env['sales.target.config'].search([
                    ('user_id', '=', record.salesperson_id.id),
                    ('month_start_date', '=', month_start),
                    ('state', '=', 'active')
                ], limit=1)

                record.target_config_id = target_config.id if target_config else False
            else:
                record.target_config_id = False

    @api.depends('salesperson_id', 'week_start_date', 'target_config_id', 'daily_sales_ids.daily_sales_target')
    def _compute_weekly_target(self):
        """Calculate weekly target based on sales target configuration or aggregated daily targets"""
        for record in self:
            if record.daily_sales_ids:
                # Use the sum of daily targets (which are already aggregated if supervisor)
                record.weekly_target = sum(record.daily_sales_ids.mapped('daily_sales_target'))
            elif record.salesperson_id and record.week_start_date:
                # Fallback to config if no daily records linked yet
                week_in_month = self._get_week_in_month(record.week_start_date)
                if record.target_config_id:
                    if week_in_month == 1:
                        record.weekly_target = record.target_config_id.week1_sales_target
                    elif week_in_month == 2:
                        record.weekly_target = record.target_config_id.week2_sales_target
                    elif week_in_month == 3:
                        record.weekly_target = record.target_config_id.week3_sales_target
                    elif week_in_month == 4:
                        record.weekly_target = record.target_config_id.week4_sales_target
                    else:
                        record.weekly_target = 0.0
                else:
                    record.weekly_target = self._get_weekly_target_from_daily_config(record.salesperson_id,
                                                                                     record.week_start_date)
            else:
                record.weekly_target = 0.0

    @api.depends('daily_sales_ids', 'daily_sales_ids.total_sales',
                 'daily_sales_ids.cash_sales', 'daily_sales_ids.credit_sales',
                 'weekly_target')
    def _compute_totals(self):
        for record in self:
            total_cash = sum(record.daily_sales_ids.mapped('cash_sales'))
            total_credit = sum(record.daily_sales_ids.mapped('credit_sales'))
            total_sales = total_cash + total_credit

            record.total_cash_sales = total_cash
            record.total_credit_sales = total_credit
            record.total_sales = total_sales

            # Average daily sales
            days_count = len(record.daily_sales_ids) or 1
            record.average_daily_sales = total_sales / days_count

            # Weekly achievement
            if record.weekly_target > 0:
                record.weekly_achievement_percent = (total_sales / record.weekly_target) * 100
            else:
                record.weekly_achievement_percent = 0.0

    @api.depends('daily_sales_ids', 'daily_sales_ids.total_sales',
                 'daily_sales_ids.daily_sales_target')
    def _compute_performance(self):
        for record in self:
            daily_sales = record.daily_sales_ids

            if daily_sales:
                sales_values = daily_sales.mapped('total_sales')
                record.best_day_sales = max(sales_values) if sales_values else 0.0
                record.worst_day_sales = min(sales_values) if sales_values else 0.0

                # Count days above target
                above_target = 0
                for daily in daily_sales:
                    if daily.total_sales > daily.daily_sales_target:
                        above_target += 1
                record.days_above_target = above_target
            else:
                record.best_day_sales = 0.0
                record.worst_day_sales = 0.0
                record.days_above_target = 0

    @api.depends('daily_sales_ids', 'daily_sales_ids.total_sales', 'daily_sales_ids.date')
    def _compute_daily_breakdown(self):
        for record in self:
            # Initialize to 0
            record.monday_sales = 0.0
            record.tuesday_sales = 0.0
            record.wednesday_sales = 0.0
            record.thursday_sales = 0.0
            record.friday_sales = 0.0
            record.saturday_sales = 0.0
            record.sunday_sales = 0.0

            for daily in record.daily_sales_ids:
                if daily.date:
                    weekday = daily.date.weekday()
                    sales_amount = daily.total_sales

                    if weekday == 0:
                        record.monday_sales += sales_amount
                    elif weekday == 1:
                        record.tuesday_sales += sales_amount
                    elif weekday == 2:
                        record.wednesday_sales += sales_amount
                    elif weekday == 3:
                        record.thursday_sales += sales_amount
                    elif weekday == 4:
                        record.friday_sales += sales_amount
                    elif weekday == 5:
                        record.saturday_sales += sales_amount
                    elif weekday == 6:
                        record.sunday_sales += sales_amount

    # ============================
    # CRUD METHODS
    # ============================

    def write(self, vals):
        result = super(WeeklySales, self).write(vals)

        # Update monthly totals if needed
        if any(field in vals for field in ['state', 'week_start_date', 'salesperson_id']):
            for record in self:
                if record.monthly_sales_id:
                    record.monthly_sales_id._compute_totals()

        return result

    # ============================
    # HELPER METHODS
    # ============================
    def _find_or_create_monthly_sales(self, user_id, date):
        """Find or create monthly sales record"""
        if isinstance(date, str):
            date = fields.Date.from_string(date)

        month_start = date.replace(day=1)
        # month_end = month_start + relativedelta.relativedelta(months=1, days=-1)

        monthly_sales = self.env['monthly.sales'].search([
            ('salesperson_id', '=', user_id),
            ('month_start_date', '=', month_start),
        ], limit=1)

        if not monthly_sales:
            month_end = month_start + relativedelta.relativedelta(months=1, days=-1)
            monthly_vals = {
                'salesperson_id': user_id,
                'month_start_date': month_start,
                'month_end_date': month_end,
            }
            monthly_sales = self.env['monthly.sales'].create(monthly_vals)

        return monthly_sales

    def _get_weekly_target_from_daily_config(self, user_id, start_date):
        """Sum up daily targets for the week as a fallback"""
        if not user_id or not start_date:
            return 0.0

        end_date = start_date + timedelta(days=6)

        # Find all active target lines for this user within the week range
        daily_targets = self.env['sales.target.config.line'].search([
            ('target_config_id.user_id', '=', user_id.id),
            ('date', '>=', start_date),
            ('date', '<=', end_date),
            ('target_config_id.state', '=', 'active')
        ])

        return sum(daily_targets.mapped('daily_sales_target'))

    # ============================
    # BUSINESS METHODS
    # ============================
    def action_view_daily_sales(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Daily Sales',
            'res_model': 'daily.sales',
            'view_mode': 'list,form',
            'domain': [('weekly_sales_id', '=', self.id)],
            'context': {'create': False}
        }

    def action_view_monthly_record(self):
        self.ensure_one()
        if self.monthly_sales_id:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Monthly Sales',
                'res_model': 'monthly.sales',
                'view_mode': 'form',
                'res_id': self.monthly_sales_id.id,
                'target': 'current'
            }
        else:
            raise UserError(_('No monthly record found for this weekly sales entry.'))

    def action_complete_week(self):
        for record in self:
            record.state = 'completed'
            # Update monthly totals
            if record.monthly_sales_id:
                record.monthly_sales_id._compute_totals()

    def action_cancel_week(self):
        for record in self:
            record.state = 'canceled'
            # Update monthly totals
            if record.monthly_sales_id:
                record.monthly_sales_id._compute_totals()

    @api.model
    def _cron_check_week_status(self):
        """Automatically update week status based on dates"""
        today = fields.Date.today()

        # Update week statuses
        in_progress_weeks = self.search([
            ('week_start_date', '<=', today),
            ('week_end_date', '>=', today),
            ('state', '=', 'draft')
        ])
        in_progress_weeks.write({'state': 'in_progress'})

        completed_weeks = self.search([
            ('week_end_date', '<', today),
            ('state', 'in', ['draft', 'in_progress'])
        ])
        completed_weeks.write({'state': 'completed'})

        # Update monthly totals for affected weeks
        for week in in_progress_weeks + completed_weeks:
            if week.monthly_sales_id:
                week.monthly_sales_id._compute_totals()

        return True
