from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta

class CustomerCredit(models.Model):
    _name = 'customer.credit'
    _description = 'Customer Credit'
    _inherit = ['mail.thread', 'mail.activity.mixin']



    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, store=True)
    partner_id = fields.Many2one('res.partner', string="Customer", required=True )
    tin_no = fields.Char(string="Tin No", related='partner_id.vat', readonly=True)
    city_sub_city = fields.Char(string="City/sub-city", related='partner_id.city', readonly=True)
    maximum_credit = fields.Monetary(string="Credit limit", currency_field="currency_id")
    credit = fields.Monetary(string="Unsettled amount",compute='_compute_unsettled_amount',store=True,currency_field="currency_id")
    matured_amount = fields.Monetary(string="Credit balance", compute="_compute_matured_amount",store=True,currency_field="currency_id" )
    currency_id = fields.Many2one('res.currency',string="Currency",related='partner_id.currency_id',readonly=True)
    payment_term_credit = fields.Many2one('account.payment.term',string="Payment Term Credit")
    due_date = fields.Date(string="Due Date")
    payment_date = fields.Date(string="Payment Date",compute="_compute_payment_date",store=True)
    notification_sent = fields.Boolean(string="Notification Sent",default=False )
    sale_order_ids = fields.One2many('sale.order', 'customer_credit_id', string='Sales Orders')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('validated', 'Validated'),
    ], string='Status', default='draft', tracking=True)


    @api.depends('partner_id', 'partner_id.credit')
    def _compute_unsettled_amount(self):
        for record in self:
            record.credit = record.partner_id.credit or 0.0

    @api.depends('credit', 'maximum_credit')
    def _compute_matured_amount(self):
        for record in self:
            record.matured_amount = record.maximum_credit - record.credit

    @api.depends('payment_term_credit', 'partner_id')
    def _compute_payment_date(self):
        for record in self:
            if record.payment_term_credit:
                sale_order = self.env['sale.order'].search([
                    ('partner_id', '=', record.partner_id.id),
                    ('state', 'in', ['sale', 'done']),
                    ('sale_type', '=', 'credit')
                ], limit=1, order='date_order desc')
                if sale_order and sale_order.date_order:
                    order_date = sale_order.date_order.date()
                    days = record.payment_term_credit.line_ids[0].nb_days if record.payment_term_credit.line_ids else 0
                    record.payment_date = order_date + timedelta(days=days)
                    if record.payment_date:
                        record.due_date = record.payment_date - timedelta(days=3)
                else:
                    record.payment_date = False
                    record.due_date = False
            else:
                record.payment_date = False
                record.due_date = False

    def _check_payment_warning(self):
        today = fields.Date.today()
        for record in self:
            if (record.credit > 0 and record.due_date and record.payment_date and
                    today >= record.due_date and today <= record.payment_date and
                    not record.notification_sent):
                self._send_payment_warning_notification(record)
                record.notification_sent = True

    def _send_payment_warning_notification(self, record):
        # 1. Get latest credit sale order
        sale_order = self.env['sale.order'].search([
            ('partner_id', '=', record.partner_id.id),
            ('state', 'in', ['sale', 'done']),
            ('sale_type', '=', 'credit')
        ], limit=1, order='date_order desc')

        sales_officer = sale_order.user_id if sale_order else False
        customer = record.partner_id

        # Message content (used for both email and internal activity)
        subject = f"Payment Warning for {customer.name}"
        message_body = f"""
    Dear {sales_officer.name if sales_officer else 'Salesperson'},

    This is a reminder that the customer <b>{customer.name}</b> has an unsettled credit balance of 
    <b>{record.credit} {record.currency_id.name}</b>.

    The payment is due by <b>{record.payment_date}</b> with a follow-up deadline (due date) of <b>{record.due_date}</b>.

    Please ensure timely follow-up with the customer.
    """

        # 2. Send internal notification (activity) to sales officer
        if sales_officer:
            record.activity_schedule(
                activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,
                user_id=sales_officer.id,
                summary=subject,
                note=message_body,
                date_deadline=record.due_date or fields.Date.today(),
            )

        # 3. Send email to customer (if email exists)
        if customer.email:
            email_body = f"""
            <p>Dear {customer.name},</p>

            <p>This is a reminder that your account has an unsettled balance of 
            <strong>{record.credit} {record.currency_id.name}</strong>.</p>

            <p>The payment is expected by <strong>{record.payment_date}</strong>.
            Please ensure payment is made before the due date of <strong>{record.due_date}</strong>.</p>

            <p>Thank you,<br/>
            Your Accounts Receivable Team</p>
            """

            record.message_post(
                body=email_body,
                subject=f"Credit Payment Reminder - {customer.name}",
                partner_ids=[customer.id],
                message_type='email',
                subtype_xmlid='mail.mt_comment',
            )

    #def _send_payment_warning_notification(self, record):
     #   sale_order = self.env['sale.order'].search([
      #      ('partner_id', '=', record.partner_id.id),
       #     ('state', 'in', ['sale', 'done']),
        #    ('sale_type', '=', 'credit')
       # ], limit=1, order='date_order desc')
       # sales_officer = sale_order.user_id if sale_order else False
       # if sales_officer and sales_officer.email:
        #    subject = f"Payment Warning for {record.partner_id.name}"
         #   body = f"""
          #  Dear {sales_officer.name},

           # This is a warning that the customer {record.partner_id.name} has an unsettled amount of 
            #{record.credit} {record.currency_id.name}. The payment is due by {record.payment_date}. 
            #Please follow up to ensure payment is received before the due date of {record.due_date}.
           # """
           # self.env['mail.mail'].sudo().create({
           #     'subject': subject,
            #    'body_html': body,
             #   'email_to': sales_officer.email,
              #  'state': 'outgoing',
            #}).send()

    @api.constrains('credit', 'maximum_credit')
    def _validate_credit_limit(self):
        for record in self:
            if record.company_id and record.company_id.bypass_credit_limit_check:
                continue
            if record.credit > record.maximum_credit:
                raise UserError(
                    f"The unsettled amount ({record.credit} {record.currency_id.name}) "
                    f"exceeds the credit limit ({record.maximum_credit} {record.currency_id.name}) for customer {record.partner_id.name}."
                )

    @api.model
    def _cron_check_payment_warnings(self):
        records = self.search([('credit', '>', 0), ('due_date', '!=', False)])
        records._check_payment_warning()

    _sql_constraints = [
        ('unique_partner_credit', 'unique(partner_id, company_id)', 'Only one credit record is allowed per customer per company.')
    ]
