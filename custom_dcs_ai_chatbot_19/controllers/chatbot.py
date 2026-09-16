import json
import logging
import requests

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)

# Timeout for the n8n webhook call (seconds)
N8N_TIMEOUT = 120


class DCSAIChatbotController(http.Controller):
    """Proxy controller that forwards chat messages to the n8n AI Agent."""

    @http.route(
        '/dcs_ai_chatbot/send',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True,
    )
    def send_message(self, message, **kwargs):
        """
        Receive a chat message from the OWL frontend and forward it
        to the n8n webhook. Returns the AI agent's reply.
        """
        # --- Group access check ---
        if not request.env.user.has_group(
            'custom_dcs_ai_chatbot_19.group_dcs_ai_chatbot_user'
        ):
            return {
                'status': 'error',
                'reply': 'Access denied. You do not have permission to use the AI chatbot.',
            }

        if not message or not message.strip():
            return {'status': 'error', 'reply': 'Please enter a message.'}

        # --- Get webhook URL from system parameter ---
        webhook_url = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('dcs_ai_chatbot.n8n_webhook_url', default='')
        )
        if not webhook_url:
            _logger.error("DCS AI Chatbot: n8n webhook URL is not configured.")
            return {
                'status': 'error',
                'reply': (
                    'The AI assistant is not configured yet. '
                    'Please ask your administrator to set the webhook URL '
                    'in Settings → Technical → System Parameters '
                    '(key: dcs_ai_chatbot.n8n_webhook_url).'
                ),
            }

        # --- Build the session ID from the current Odoo user ---
        user = request.env.user
        session_id = f"odoo-user-{user.id}-{user.login}"

        # --- Call the n8n webhook ---
        payload = {
            'chatInput': message.strip(),
            'sessionId': session_id,
        }

        try:
            _logger.info(
                "DCS AI Chatbot: Sending message from user %s (session: %s)",
                user.login,
                session_id,
            )
            resp = requests.post(
                webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=N8N_TIMEOUT,
            )
            resp.raise_for_status()

            data = resp.json()

            if isinstance(data, list) and len(data) > 0:
                ai_reply = data[0].get('output', data[0].get('text', str(data[0])))
            elif isinstance(data, dict):
                ai_reply = data.get('output', data.get('text', str(data)))
            else:
                ai_reply = str(data)

            return {'status': 'ok', 'reply': ai_reply}

        except requests.exceptions.Timeout:
            _logger.warning("DCS AI Chatbot: n8n webhook timed out.")
            return {
                'status': 'error',
                'reply': (
                    'The AI assistant took too long to respond. '
                    'Please try again or simplify your question.'
                ),
            }
        except requests.exceptions.ConnectionError:
            _logger.error("DCS AI Chatbot: Cannot reach n8n at %s", webhook_url)
            return {
                'status': 'error',
                'reply': (
                    'Cannot connect to the AI assistant service. '
                    'Please try again later or contact your administrator.'
                ),
            }
        except Exception as e:
            _logger.exception("DCS AI Chatbot: Unexpected error: %s", e)
            return {
                'status': 'error',
                'reply': f'An unexpected error occurred: {str(e)}',
            }

    # =========================================================
    #  ACCESS CHECK — Called by the OWL widget on mount
    # =========================================================
    @http.route(
        '/dcs_ai_chatbot/check_access',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True,
    )
    def check_access(self, **kwargs):
        """Return whether the current user belongs to the chatbot group."""
        has_access = request.env.user.has_group(
            'custom_dcs_ai_chatbot_19.group_dcs_ai_chatbot_user'
        )
        return {'has_access': has_access}

    # =========================================================
    #  PROACTIVE INSIGHTS — Live Odoo Stats
    # =========================================================
    @http.route(
        '/dcs_ai_chatbot/insights',
        type='json',
        auth='user',
        methods=['POST'],
        csrf=True,
    )
    def get_insights(self, **kwargs):
        """
        Returns a quick summary of key business metrics from Odoo.
        Called when the chatbot panel opens for the first time.
        """
        # --- Group access check ---
        if not request.env.user.has_group(
            'custom_dcs_ai_chatbot_19.group_dcs_ai_chatbot_user'
        ):
            return {'status': 'error'}
        
        try:    
            env = request.env

            # Count draft sale orders
            draft_orders = 0
            try:
                draft_orders = env['sale.order'].sudo().search_count([
                    ('state', 'in', ['draft', 'sent']),
                ])
            except Exception:
                pass  # Module may not be installed

            # Count overdue invoices (past due date, not fully paid)
            overdue_invoices = 0
            try:
                today = fields.Date.today()
                overdue_invoices = env['account.move'].sudo().search_count([
                    ('move_type', '=', 'out_invoice'),
                    ('payment_state', 'not in', ['paid', 'in_payment']),
                    ('state', '=', 'posted'),
                    ('invoice_date_due', '<', today),
                ])
            except Exception:
                pass  # Module may not be installed

            # Count open project tasks
            open_tasks = 0
            try:
                open_tasks = env['project.task'].sudo().search_count([
                    ('stage_id.fold', '=', False),
                ])
            except Exception:
                pass  # Module may not be installed

            return {
                'status': 'ok',
                'draftOrders': draft_orders,
                'overdueInvoices': overdue_invoices,
                'openTasks': open_tasks,
            }

        except Exception as e:
            _logger.exception("DCS AI Chatbot Insights error: %s", e)
            return {'status': 'error'}
