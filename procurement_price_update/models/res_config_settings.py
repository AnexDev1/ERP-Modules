# -*- coding: utf-8 -*-
from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    local_wholesale_margin = fields.Float(
        string='Local Wholesale Margin (%)',
        default=0.0
    )
    local_retail_margin = fields.Float(
        string='Local Retail Margin (%)',
        default=0.0
    )
    foreign_wholesale_margin = fields.Float(
        string='Foreign Wholesale Margin (%)',
        default=0.0
    )
    foreign_retail_margin = fields.Float(
        string='Foreign Retail Margin (%)',
        default=0.0
    )

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    local_wholesale_margin = fields.Float(
        related='company_id.local_wholesale_margin',
        readonly=False,
        string='Local Wholesale Margin (%)'
    )
    local_retail_margin = fields.Float(
        related='company_id.local_retail_margin',
        readonly=False,
        string='Local Retail Margin (%)'
    )
    foreign_wholesale_margin = fields.Float(
        related='company_id.foreign_wholesale_margin',
        readonly=False,
        string='Foreign Wholesale Margin (%)'
    )
    foreign_retail_margin = fields.Float(
        related='company_id.foreign_retail_margin',
        readonly=False,
        string='Foreign Retail Margin (%)'
    )
