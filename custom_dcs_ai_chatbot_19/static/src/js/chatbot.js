/** @odoo-module **/

import { Component, useState, useRef, onMounted, markup } from "@odoo/owl";
import { registry } from "@web/core/registry";

// ============================================================
//  QUICK ACTION DEFINITIONS
// ============================================================
const QUICK_ACTIONS = [
    { label: "📊 Today's Sales", prompt: "What are today's sales orders and their total value?" },
    { label: "⚠️ Overdue Invoices", prompt: "List all overdue invoices that are past their due date and unpaid." },
    { label: "👥 Top Customers", prompt: "Who are the top 10 customers by total sales amount?" },
    { label: "💰 Recent Payslips", prompt: "Show the most recent payslips generated in the system." },
    { label: "📦 Stock Summary", prompt: "What is the current stock summary for the main warehouse?" },
    { label: "📋 Open Tasks", prompt: "List all open project tasks with their deadlines and assigned users." },
];

// ============================================================
//  PANEL SIZE MODES
// ============================================================
const PANEL_SIZES = ['compact', 'broad', 'full'];

// ============================================================
//  MARKDOWN → HTML CONVERTER
// ============================================================
function formatAIResponse(text) {
    if (!text) return '';
    let html = text;

    // Escape HTML entities
    html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    // --- TABLE PARSING ---
    const lines = html.split('\n');
    let inTable = false;
    let tableHtml = [];
    let processedLines = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        const nextLine = (i + 1 < lines.length) ? lines[i + 1].trim() : '';

        if (!inTable && line.startsWith('|') && nextLine.match(/^\|?\s*[:\-|\s]+\s*\|?$/)) {
            inTable = true;
            tableHtml.push('<div class="dcs-cb-table-wrapper"><table class="dcs-cb-table"><thead>');
            const cleanCells = line.split('|').map(c => c.trim()).filter((c, idx, arr) => {
                if (idx === 0 && c === '') return false;
                if (idx === arr.length - 1 && c === '') return false;
                return true;
            });
            tableHtml.push('<tr>');
            cleanCells.forEach(cell => tableHtml.push(`<th>${cell}</th>`));
            tableHtml.push('</tr></thead><tbody>');
            i++;
            continue;
        }

        if (inTable) {
            if (line.startsWith('|')) {
                const cells = line.split('|').map(c => c.trim()).filter((c, idx, arr) => {
                    if (idx === 0 && c === '') return false;
                    if (idx === arr.length - 1 && c === '') return false;
                    return true;
                });
                tableHtml.push('<tr>');
                cells.forEach(cell => tableHtml.push(`<td>${cell}</td>`));
                tableHtml.push('</tr>');
            } else {
                inTable = false;
                tableHtml.push('</tbody></table></div>');
                processedLines.push(tableHtml.join(''));
                tableHtml = [];
                processedLines.push(line);
            }
        } else {
            processedLines.push(line);
        }
    }
    if (inTable) {
        tableHtml.push('</tbody></table></div>');
        processedLines.push(tableHtml.join(''));
    }
    html = processedLines.join('\n');

    // Code blocks
    html = html.replace(/```([\s\S]*?)```/g, '<pre class="dcs-cb-code-block">$1</pre>');
    html = html.replace(/`([^`]+)`/g, '<code class="dcs-cb-inline-code">$1</code>');

    // Bold & Italic
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Lists
    html = html.replace(/^(\d+)\.\s+(.+)$/gm, '<li class="dcs-cb-list-item dcs-cb-list-ordered">$2</li>');
    html = html.replace(/^[-•]\s+(.+)$/gm, '<li class="dcs-cb-list-item dcs-cb-list-bullet">$1</li>');
    html = html.replace(/((?:<li class="dcs-cb-list-item dcs-cb-list-ordered">.*<\/li>\n?)+)/g, '<ol class="dcs-cb-list">$1</ol>');
    html = html.replace(/((?:<li class="dcs-cb-list-item dcs-cb-list-bullet">.*<\/li>\n?)+)/g, '<ul class="dcs-cb-list">$1</ul>');

    // Line breaks
    html = html.replace(/\n(?!(?:<\/div>|<\/table>|<\/thead>|<\/tbody>|<\/tr>|<\/ol>|<\/ul>|<\/pre>))/g, '<br/>');

    return html;
}

// ============================================================
//  OWL COMPONENT
// ============================================================
export class DCSAIChatbot extends Component {
    static template = "custom_dcs_ai_chatbot_19.ChatbotWidget";
    static props = { "*": true };

    setup() {
        this.state = useState({
            hasAccess: false,       // resolved async via RPC
            isOpen: false,
            messages: [],
            inputText: '',
            isLoading: false,
            showQuickActions: true,
            panelSize: 'compact',  // 'compact' | 'broad' | 'full'
            theme: 'dark',          // 'dark' | 'light'
            insights: null,         // { draftOrders, overdueInvoices, openTasks }
            insightsLoading: false,
        });

        this.messagesEndRef = useRef("messagesEnd");
        this.inputRef = useRef("chatInput");
        this.quickActions = QUICK_ACTIONS;

        // Restore theme from localStorage
        try {
            const saved = localStorage.getItem('dcs_cb_theme');
            if (saved === 'light' || saved === 'dark') {
                this.state.theme = saved;
            }
        } catch (e) { /* ignore */ }

        onMounted(async () => {
            // Check group access via a lightweight RPC endpoint
            await this._checkAccess();
            if (!this.state.hasAccess) return;

            const welcomeText = "Hello! 👋 I'm **Droga AI**. I can query your Odoo data in natural language.\n\nTap a quick action below or type your own question!";
            this.state.messages.push({
                id: Date.now(),
                role: 'bot',
                text: welcomeText,
                html: markup(formatAIResponse(welcomeText)),
                time: this._formatTime(),
                hasTable: false,
            });

            // Fetch proactive insights
            this._fetchInsights();
        });
    }

    // ---- Panel Size ----
    cyclePanelSize() {
        const idx = PANEL_SIZES.indexOf(this.state.panelSize);
        this.state.panelSize = PANEL_SIZES[(idx + 1) % PANEL_SIZES.length];
    }

    get panelSizeIcon() {
        const s = this.state.panelSize;
        if (s === 'compact') return 'expand';
        if (s === 'broad') return 'maximize';
        return 'minimize';
    }

    get panelSizeTitle() {
        const s = this.state.panelSize;
        if (s === 'compact') return 'Expand (Broad)';
        if (s === 'broad') return 'Full Page';
        return 'Compact';
    }

    // ---- Theme ----
    toggleTheme() {
        this.state.theme = this.state.theme === 'dark' ? 'light' : 'dark';
        try {
            localStorage.setItem('dcs_cb_theme', this.state.theme);
        } catch (e) { /* ignore */ }
    }

    // ---- Chat Controls ----
    toggleChat() {
        this.state.isOpen = !this.state.isOpen;
        if (this.state.isOpen) {
            setTimeout(() => {
                if (this.inputRef.el) this.inputRef.el.focus();
            }, 300);
        }
    }

    closeChat() {
        this.state.isOpen = false;
        this.state.panelSize = 'compact';
    }

    onInputKeydown(ev) {
        if (ev.key === 'Enter' && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }

    // ---- Quick Actions ----
    onQuickAction(prompt) {
        this.state.inputText = prompt;
        this.sendMessage();
    }

    // ---- Send Message ----
    async sendMessage() {
        const text = this.state.inputText.trim();
        if (!text || this.state.isLoading) return;

        this.state.showQuickActions = false;

        this.state.messages.push({
            id: Date.now(),
            role: 'user',
            text: text,
            html: markup(text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br/>')),
            time: this._formatTime(),
            hasTable: false,
        });
        this.state.inputText = '';
        this.state.isLoading = true;
        this._scrollToBottom();

        try {
            const response = await fetch('/dcs_ai_chatbot/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: { message: text },
                }),
            });

            const data = await response.json();
            if (data.error) {
                throw new Error(data.error.data?.message || data.error.message || 'Server error');
            }

            const result = data.result || {};
            const reply = result.reply || 'No response received.';
            const hasTable = reply.includes('|') && reply.includes('---');

            this.state.messages.push({
                id: Date.now() + 1,
                role: 'bot',
                text: reply,
                html: markup(formatAIResponse(reply)),
                time: this._formatTime(),
                isError: result.status === 'error',
                hasTable: hasTable,
            });
        } catch (err) {
            console.error('DCS AI Chatbot error:', err);
            this.state.messages.push({
                id: Date.now() + 1,
                role: 'bot',
                text: 'Sorry, something went wrong. Please try again.',
                html: markup('<strong>Sorry, something went wrong.</strong> Please try again.'),
                time: this._formatTime(),
                isError: true,
                hasTable: false,
            });
        }

        this.state.isLoading = false;
        this._scrollToBottom();
    }

    // ---- Export CSV ----
    exportCSV(msgId) {
        const msg = this.state.messages.find(m => m.id === msgId);
        if (!msg || !msg.text) return;

        const lines = msg.text.split('\n');
        let csvRows = [];
        let inTable = false;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();
            const nextLine = (i + 1 < lines.length) ? lines[i + 1].trim() : '';

            if (!inTable && line.startsWith('|') && nextLine.match(/^\|?\s*[:\-|\s]+\s*\|?$/)) {
                inTable = true;
                const cells = line.split('|').map(c => c.trim()).filter(c => c !== '');
                csvRows.push(cells.map(c => `"${c.replace(/"/g, '""')}"`).join(','));
                i++;
                continue;
            }

            if (inTable) {
                if (line.startsWith('|')) {
                    const cells = line.split('|').map(c => c.trim()).filter(c => c !== '');
                    csvRows.push(cells.map(c => `"${c.replace(/"/g, '""')}"`).join(','));
                } else {
                    inTable = false;
                }
            }
        }

        if (csvRows.length === 0) return;

        const csvString = csvRows.join('\n');
        const blob = new Blob(['\uFEFF' + csvString], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `droga_ai_export_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // ---- Proactive Insights ----
    async _fetchInsights() {
        this.state.insightsLoading = true;
        try {
            const response = await fetch('/dcs_ai_chatbot/insights', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: {} }),
            });
            const data = await response.json();
            if (data.result && data.result.status === 'ok') {
                this.state.insights = data.result;
            }
        } catch (e) {
            console.warn('DCS Chatbot: Could not fetch insights', e);
        }
        this.state.insightsLoading = false;
    }

    // ---- Clear Chat ----
    clearChat() {
        const resetText = "Chat cleared. How else can I help you today?";
        this.state.messages = [{
            id: Date.now(),
            role: 'bot',
            text: resetText,
            html: markup(formatAIResponse(resetText)),
            time: this._formatTime(),
            hasTable: false,
        }];
        this.state.showQuickActions = true;
    }

    // ---- Access Check ----
    async _checkAccess() {
        try {
            const response = await fetch('/dcs_ai_chatbot/check_access', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: {} }),
            });
            const data = await response.json();
            this.state.hasAccess = !!(data.result && data.result.has_access);
        } catch (e) {
            console.warn('DCS Chatbot: access check failed', e);
            this.state.hasAccess = false;
        }
    }

    // ---- Utilities ----
    _scrollToBottom() {
        setTimeout(() => {
            if (this.messagesEndRef.el) {
                this.messagesEndRef.el.scrollIntoView({ behavior: 'smooth' });
            }
        }, 100);
    }

    _formatTime() {
        return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
}

registry.category("main_components").add("DCSAIChatbot", {
    Component: DCSAIChatbot,
});
