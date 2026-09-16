from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def _get_bank_statements_available_sources(self):
        sources = list(super()._get_bank_statements_available_sources() or [])
        if not any(code == 'manual' for code, _label in sources):
            sources.append(('manual', 'Manual'))
        return sources
