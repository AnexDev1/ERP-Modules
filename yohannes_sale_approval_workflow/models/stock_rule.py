from odoo import models, fields

import logging

_logger = logging.getLogger(__name__)

# cons_sample_type was removed — it was part of the deprecated yohannes_inventory
# module routing logic. Standard Odoo warehouse routes are used instead.
