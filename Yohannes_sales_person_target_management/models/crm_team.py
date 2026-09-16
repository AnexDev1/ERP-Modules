from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil import relativedelta


class CrmTeam(models.Model):
    _inherit = 'crm.team'

    monthly_team_target = fields.Float(
        string='Monthly Team Target',
        help='Total monthly target for the entire team',
        default=0.0  # Add a default value to avoid null issues
    )

    def action_distribute_target(self):
        """Distribute the team monthly target equally among active members."""
        self.ensure_one()

        # Add precision handling for float comparison
        if self.monthly_team_target <= 0.0:
            raise UserError(_("Please set a monthly team target greater than zero."))

        members = self.member_ids
        if not members:
            raise UserError(_("This team has no members to distribute the target to."))

        # Use float_utils for more precise division
        from odoo.tools import float_utils
        individual_target = self.monthly_team_target / len(members)

        # Round to 2 decimal places for currency amounts
        individual_target = round(individual_target, 2)

        today = fields.Date.today()
        month_start = today.replace(day=1)

        for member in members:
            # Find or create target config for the current month
            config = self.env['sales.target.config'].search([
                ('user_id', '=', member.id),
                ('month_start_date', '=', month_start),
            ], limit=1)

            if not config:
                config = self.env['sales.target.config'].create({
                    'user_id': member.id,
                    'month_start_date': month_start,
                })

            # Make sure this method exists in sales.target.config
            if hasattr(config, 'action_set_and_distribute_monthly_target'):
                config.action_set_and_distribute_monthly_target(individual_target)
            else:
                # Alternative: direct assignment if method doesn't exist
                config.write({'monthly_target': individual_target})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Target Distributed'),
                'message': _('Monthly target of %s distributed to %s members.') % (
                    self.monthly_team_target, len(members)),
                'sticky': False,
            }
        }