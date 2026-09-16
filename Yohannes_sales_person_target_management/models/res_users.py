from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    daily_sales_target = fields.Float(
        string='Daily Sales Target',
        compute='_compute_current_targets',
        help="Today's sales target, aggregated for supervisors."
    )
    current_weekly_target = fields.Float(
        string='Current Weekly Target',
        compute='_compute_current_targets'
    )
    current_monthly_target = fields.Float(
        string='Current Monthly Target',
        compute='_compute_current_targets'
    )
    daily_sales_ids = fields.One2many('daily.sales', 'salesperson_id', string='Daily Sales Entries')
    managed_team_ids = fields.One2many('crm.team', 'user_id', string='Managed Sales Teams')
    is_supervisor = fields.Boolean(string='Is Supervisor', compute='_compute_is_supervisor', store=False)

    @api.depends('managed_team_ids')
    def _compute_is_supervisor(self):
        for user in self:
            user.is_supervisor = bool(user.managed_team_ids)

    def _compute_current_targets(self):
        today = fields.Date.today()
        month_start = today.replace(day=1)
        for user in self:
            # Get managed users if supervisor
            member_ids = user.get_team_managed_users().ids if user.is_supervisor else []
            all_user_ids = [user.id] + member_ids

            # Search for all active configs for self and team
            configs = self.env['sales.target.config'].search([
                ('user_id', 'in', all_user_ids),
                ('month_start_date', '=', month_start),
                ('state', '=', 'active')
            ])

            # Monthly Target
            user.current_monthly_target = sum(configs.mapped('monthly_sales_target'))

            # Daily Target for Today
            target_lines = self.env['sales.target.config.line'].search([
                ('target_config_id', 'in', configs.ids),
                ('date', '=', today)
            ])
            user.daily_sales_target = sum(target_lines.mapped('daily_sales_target'))

            # Weekly Target
            week_num = self.env['weekly.sales']._get_week_in_month(today)
            weekly_sum = 0.0
            for config in configs:
                if week_num == 1:
                    weekly_sum += config.week1_sales_target
                elif week_num == 2:
                    weekly_sum += config.week2_sales_target
                elif week_num == 3:
                    weekly_sum += config.week3_sales_target
                elif week_num == 4:
                    weekly_sum += config.week4_sales_target
            user.current_weekly_target = weekly_sum

    def get_team_managed_users(self):
        """Returns a recordset of all users in teams led by this user."""
        self.ensure_one()
        return self.env['res.users'].search([('sale_team_id', 'in', self.managed_team_ids.ids)])
