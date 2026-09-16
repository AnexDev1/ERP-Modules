from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
from dateutil import relativedelta
from calendar import monthrange


class DailySales(models.Model):
    _name = 'daily.sales'
    _description = 'Daily Sales Tracking'
    _rec_name = 'reference'

    reference = fields.Char(string='REFERENCE', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    date = fields.Date(string='Date', required=True, default=fields.Date.today)
    salesperson_id = fields.Many2one('res.users', string='Salesperson', required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    monthly_sales_id = fields.Many2one('monthly.sales', string='Monthly Record', readonly=True)
    sales_target_id = fields.Many2one('sales.target.config.line', string='Sales Target')
    cash_sales = fields.Float(string='Cash Sales', compute='_compute_sales_totals', store=True, recursive=True)
    credit_sales = fields.Float(string='Credit Sales', compute='_compute_sales_totals', store=True, recursive=True)
    total_sales = fields.Float(string='Total Sales', compute='_compute_total_sales', store=True)
    achievement_percent = fields.Float(string='Achievement %', compute='_compute_achievement_percent', store=True)
    performance_note = fields.Text(string='Sales Performance Note')

    supervisor_daily_sales_id = fields.Many2one('daily.sales', string='Supervisor Daily Record', ondelete='set null')
    member_daily_sales_ids = fields.One2many('daily.sales', 'supervisor_daily_sales_id',
                                             string='Team Member Daily Records')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code('daily.sales') or _('New')

            # Auto-find target if not provided
            if 'sales_target_id' not in vals and vals.get('date') and vals.get('salesperson_id'):
                target = self._find_sales_target(vals['salesperson_id'], vals['date'])
                if target:
                    vals['sales_target_id'] = target.id

            # Link to supervisor's daily record
            if vals.get('salesperson_id') and vals.get('date'):
                user = self.env['res.users'].browse(vals['salesperson_id'])
                if user.sale_team_id and user.sale_team_id.user_id:
                    supervisor = user.sale_team_id.user_id
                    if supervisor.id != user.id:
                        sup_daily = self.search([
                            ('salesperson_id', '=', supervisor.id),
                            ('date', '=', vals['date'])
                        ], limit=1)
                        if not sup_daily:
                            # Create supervisor record if missing
                            sup_daily = self.env['daily.sales'].create({
                                'date': vals['date'],
                                'salesperson_id': supervisor.id,
                            })
                        vals['supervisor_daily_sales_id'] = sup_daily.id

        return super(DailySales, self).create(vals_list)

    def write(self, vals):
        # If date or salesperson changes, try to find new target
        if 'date' in vals or 'salesperson_id' in vals:
            for record in self:
                new_date = vals.get('date', record.date)
                new_salesperson_id = vals.get('salesperson_id', record.salesperson_id.id)

                if new_date and new_salesperson_id:
                    target = self._find_sales_target(new_salesperson_id, new_date)
                    if target and ('sales_target_id' not in vals or not vals.get('sales_target_id')):
                        vals['sales_target_id'] = target.id

        return super(DailySales, self).write(vals)

    monthly_sales_target = fields.Float(string='Monthly Sales Target', related='sales_target_id.monthly_sales_target',
                                        readonly=True, store=True)
    sale_order_ids = fields.One2many('sale.order', 'daily_sale_id', string='Related Sales Orders')
    daily_sales_target = fields.Float(string='Daily Target', compute='_compute_daily_sales_target', readonly=True,
                                      store=True, recursive=True)
    weekly_sales_id = fields.Many2one('weekly.sales', string='Weekly Record', readonly=True, ondelete='set null')

    @api.depends('sales_target_id', 'sales_target_id.daily_sales_target', 'member_daily_sales_ids.daily_sales_target')
    def _compute_daily_sales_target(self):
        """Compute daily sales target from selected sales target + team members"""
        for record in self:
            own_target = record.sales_target_id.daily_sales_target if record.sales_target_id else 0.0
            team_target = sum(record.member_daily_sales_ids.mapped('daily_sales_target'))
            record.daily_sales_target = own_target + team_target

    @api.depends('cash_sales', 'credit_sales')
    def _compute_total_sales(self):
        """Compute total sales from cash + credit"""
        for record in self:
            record.total_sales = record.cash_sales + record.credit_sales

    def _cron_auto_generate_daily_sales(self):
        """Scheduled action to automatically generate daily sales from targets"""
        today = fields.Date.today()

        # Find all active sales target lines for today
        target_lines = self.env['sales.target.config.line'].search([
            ('date', '=', today),
            ('target_config_id.state', '=', 'active')
        ])

        created_count = 0

        for target_line in target_lines:
            # Check if daily sales record already exists
            existing_record = self.search([
                ('salesperson_id', '=', target_line.target_config_id.user_id.id),
                ('date', '=', today)
            ], limit=1)

            if not existing_record:
                # Create new daily sales record
                self.create({
                    'date': today,
                    'salesperson_id': target_line.target_config_id.user_id.id,
                    'sales_target_id': target_line.id,
                    'state': 'draft',
                })
                created_count += 1

        return f"Auto-generated {created_count} daily sales records for {today}"
        # Auto-find target when date/salesperson changes

    def _find_sales_target(self, user_id, date):
        return self.env['sales.target.config.line'].search([
            ('date', '=', date),
            ('target_config_id.user_id', '=', user_id),
            ('target_config_id.state', '=', 'active')
        ], limit=1)

    @api.onchange('date', 'salesperson_id')
    def _onchange_find_target(self):
        for rec in self:
            if rec.date and rec.salesperson_id:
                target = rec._find_sales_target(rec.salesperson_id.id, rec.date)
                rec.sales_target_id = target.id if target else False

    @api.depends('sale_order_ids', 'sale_order_ids.amount_total', 'sale_order_ids.sale_type', 'sale_order_ids.state',
                 'member_daily_sales_ids', 'member_daily_sales_ids.cash_sales', 'member_daily_sales_ids.credit_sales')
    def _compute_sales_totals(self):
        for record in self:
            # Own sales
            cash_orders = record.sale_order_ids.filtered(
                lambda o: o.state == 'sale' and o.sale_type == 'cash')
            credit_orders = record.sale_order_ids.filtered(
                lambda o: o.state == 'sale' and o.sale_type == 'credit')

            own_cash = sum(cash_orders.mapped('amount_total'))
            own_credit = sum(credit_orders.mapped('amount_total'))

            # Team sales
            team_cash = sum(record.member_daily_sales_ids.mapped('cash_sales'))
            team_credit = sum(record.member_daily_sales_ids.mapped('credit_sales'))

            record.cash_sales = own_cash + team_cash
            record.credit_sales = own_credit + team_credit
            record.total_sales = record.cash_sales + record.credit_sales

    # def action_import_from_orders(self):
    #   """Import sales data from related sale orders"""
    #  for record in self:
    #     if record.sale_order_ids:
    #        cash_orders = record.sale_order_ids.filtered(
    #           lambda o: o.state in ['sale', 'done'] and o.sale_type == 'cash')
    #      credit_orders = record.sale_order_ids.filtered(
    #         lambda o: o.state in ['sale', 'done'] and o.sale_type == 'credit')

    #    record.cash_sales = sum(cash_orders.mapped('amount_total'))
    #   record.credit_sales = sum(credit_orders.mapped('amount_total'))

    def action_view_sales_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sales Orders',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('daily_sale_id', '=', self.id)],
            'context': {'create': False}
        }

    # @api.depends('total_sales', 'daily_sales_target')
    # def _compute_achievement_percent(self):
    #   for record in self:
    #      if record.daily_sales_target > 0:
    #         record.achievement_percent = (record.total_sales / record.daily_sales_target) * 100
    #    else:
    #       record.achievement_percent = 0.0
    @api.depends('total_sales', 'daily_sales_target')
    def _compute_achievement_percent(self):
        for record in self:
            if record.daily_sales_target > 0:
                record.achievement_percent = (
                        record.total_sales / record.daily_sales_target
                )
            else:
                record.achievement_percent = 0.0

    @api.model
    def create_from_sales_orders(self, sale_orders):
        """Create daily sales entries from selected sales orders"""
        if not sale_orders:
            return False

        # Filter sales orders by state='sale'
        sale_orders = sale_orders.filtered(lambda o: o.state == 'sale')

        # Group orders by date and salesperson
        grouped_orders = {}
        for order in sale_orders:
            key = (order.date_order.date(), order.user_id.id)
            if key not in grouped_orders:
                grouped_orders[key] = self.env['sale.order']
            grouped_orders[key] += order

        # Create daily sales entries
        created_entries = self.env['daily.sales']
        for (order_date, user_id), orders in grouped_orders.items():
            # Find the corresponding sales target for the date and salesperson
            target_config = self.env['sales.target.config'].search([
                ('user_id', '=', user_id),
                ('week_start_date', '<=', order_date),
                ('week_start_date', '+', relativedelta(days=6), '>=', order_date)
            ], limit=1)
            target_line = self.env['sales.target.config.line'].search([
                ('target_config_id', '=', target_config.id),
                ('date', '=', order_date)
            ], limit=1) if target_config else False

            daily_sale = self.create({
                'date': order_date,
                'salesperson_id': user_id,
                'sales_target_id': target_line.id if target_line else False,
            })
            orders.write({'daily_sale_id': daily_sale.id})
            created_entries += daily_sale

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'daily.sales',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created_entries.ids)],
        }
