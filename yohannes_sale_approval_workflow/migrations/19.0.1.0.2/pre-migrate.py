import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # View-only change: customer_rank and supplier_rank made visible and editable
    # on the res.partner form for both customer and vendor contexts.
    # No schema or data changes required — Odoo will reload the views automatically
    # when the module version is bumped.
    _logger.info(
        "yohannes_sale_approval_workflow %s → 19.0.1.0.2: "
        "Applying partner form view update (customer_rank / supplier_rank visibility).",
        version,
    )
