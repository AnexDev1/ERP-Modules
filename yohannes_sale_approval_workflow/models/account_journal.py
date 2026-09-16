from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    use_manual_sequence_limit = fields.Boolean(
        string='Use Manual Sequence Limit',
        default=False,
        help=(
            "When enabled, the journal's automatic sequence will be forced to start "
            "from the number AFTER the configured manual receipt limit. "
            "This prevents digital invoice numbers from overlapping with manual receipt books."
        )
    )

    manual_sequence_limit = fields.Integer(
        string='Last Manual Receipt Number',
        default=0,
        help=(
            "The last number used by the physical/manual receipt book (e.g. 100). "
            "The digital sequence for this journal will start from this number + 1. "
            "Leave at 0 to follow Odoo default."
        )
    )

    def action_apply_manual_sequence_now(self):
        """
        Action button to confirm that the manual sequence limit is active for this journal.
        """
        for journal in self:
            if not journal.use_manual_sequence_limit:
                raise UserError(_(
                    "Manual Sequence Limit is not enabled for journal '%s'."
                ) % journal.name)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sequence Limit Configured'),
                'message': _(
                    'The sequence limit for journal "%s" is active. '
                    'Digital invoices will start from %d.'
                ) % (self.name, self.manual_sequence_limit + 1),
                'type': 'success',
            }
        }
