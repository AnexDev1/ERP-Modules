/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState, useRef, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { rpc } from "@web/core/network/rpc";

export class ProcurementDashboard extends Component {
    static template = "procurement_dashboard.DashboardMain";
    static props = ["*"];

    setup() {
        this.actionService = useService("action");

        // Canvas references
        this.spendingCanvasRef  = useRef("spendingCanvas");
        this.poStatusCanvasRef  = useRef("poStatusCanvas");
        this.vendorSpendCanvasRef = useRef("vendorSpendCanvas");
        this.deptCanvasRef      = useRef("deptCanvas");

        // Chart instances
        this.spendingChart    = null;
        this.poStatusChart    = null;
        this.vendorSpendChart = null;
        this.deptChart        = null;

        // Default: last 30 days
        const now      = new Date();
        const from     = new Date(now);
        from.setDate(from.getDate() - 29);

        this.state = useState({
            loading: true,
            preset: 'last30',
            dateFrom: from.toISOString().slice(0, 10),
            dateTo:   now.toISOString().slice(0, 10),
            lastUpdated: this._fmtDatetime(now),
            stats: {
                po_total_amount:   0, po_total_change:   0,
                po_count:          0, po_count_change:   0,
                avg_order_value:   0, avg_order_change:  0,
                pr_count:          0, pr_count_change:   0,
                shortage_count:    0,
                local_po_amount:   0, foreign_po_amount:  0,
                local_rfq_count:   0, local_rfq_pending:  0, local_rfq_po_amount:  0,
                foreign_rfq_count: 0, foreign_rfq_pending: 0, foreign_rfq_po_amount: 0,
                lc_need_count:           0,
                expired_lc_count:        0,
                progress_currency_count: 0,
            },
            charts: {
                spending:    { labels: [], local: [], foreign: [] },
                po_status:   { labels: [], values: [] },
                vendor_spend:{ labels: [], values: [] },
                department:  { labels: [], local: [], foreign: [] },
            },
            top_vendors:        [],
            departmentBreakdown: [],
            pendingRequisitions: [],
            recentPOs:           [],
            shortageItems:       [],
        });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.loadData();
        });

        useEffect(() => {
            if (!this.state.loading) {
                this.renderCharts();
            }
            return () => {
                this._destroyCharts();
            };
        }, () => [this.state.loading, this.state.charts]);

        onWillUnmount(() => {
            this._destroyCharts();
        });
    }

    get expiredLCDomain() {
        const todayStr = new Date().toISOString().split('T')[0];
        return ['|', ['state', '=', 'expired'], '&', ['expiry_date', '<', todayStr], ['state', 'in', ['active', 'issued', 'amended']]];
    }

    async loadData() {
        this.state.loading = true;
        try {
            console.log("ProcurementDashboard: Fetching data...");
            const data = await rpc("/procurement_dashboard/data", {
                date_from: this.state.dateFrom,
                date_to:   this.state.dateTo,
            });
            console.log("ProcurementDashboard: Received data from controller:", data);
            
            Object.assign(this.state.stats, data.stats);
            this.state.charts               = data.charts;
            this.state.top_vendors          = data.top_vendors          || [];
            this.state.departmentBreakdown  = data.department_breakdown || [];
            this.state.pendingRequisitions  = data.pending_requisitions || [];
            this.state.recentPOs            = data.recent_pos           || [];
            this.state.shortageItems        = data.shortage_items       || [];
            this.state.lastUpdated          = this._fmtDatetime(new Date());
            
            console.log("ProcurementDashboard: State stats and charts updated successfully.");
        } catch (error) {
            console.error("ProcurementDashboard: Failed to load dashboard data", error);
        } finally {
            this.state.loading = false;
        }
    }

    async applyDateFilter()  { await this.loadData(); }
    async refreshDashboard() { await this.loadData(); }

    // Preset date ranges
    async setPreset(preset) {
        const now  = new Date();
        let from   = new Date(now);
        this.state.preset = preset;
        if (preset === 'last30') {
            from.setDate(from.getDate() - 29);
        } else if (preset === 'thisMonth') {
            from = new Date(now.getFullYear(), now.getMonth(), 1);
        } else if (preset === 'last3') {
            from.setMonth(from.getMonth() - 3);
        }
        this.state.dateFrom = from.toISOString().slice(0, 10);
        this.state.dateTo   = now.toISOString().slice(0, 10);
        await this.loadData();
    }

    // ── Charts ────────────────────────────────────────────────────────────
    renderCharts() {
        console.log("ProcurementDashboard: renderCharts() called.");
        console.log("Canvas elements:", {
            spending: this.spendingCanvasRef.el,
            poStatus: this.poStatusCanvasRef.el,
            vendorSpend: this.vendorSpendCanvasRef.el,
            dept: this.deptCanvasRef.el
        });
        this._destroyCharts();
        try { this._renderSpendingChart();   } catch (e) { console.error("Spending chart error:", e); }
        try { this._renderPOStatusChart();   } catch (e) { console.error("PO status chart error:", e); }
        try { this._renderVendorSpendChart();} catch (e) { console.error("Vendor chart error:", e); }
        try { this._renderDeptChart();       } catch (e) { console.error("Dept chart error:", e); }
    }

    _destroyCharts() {
        ['spendingChart','poStatusChart','vendorSpendChart','deptChart'].forEach(k => {
            if (this[k]) { this[k].destroy(); this[k] = null; }
        });
    }

    _renderSpendingChart() {
        const ctx = this.spendingCanvasRef.el?.getContext("2d");
        if (!ctx) return;
        this.spendingChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: this.state.charts.spending.labels,
                datasets: [
                    {
                        label: 'Confirmed Orders',
                        data:  this.state.charts.spending.local,
                        borderColor: '#6366f1',
                        backgroundColor: 'rgba(99,102,241,0.08)',
                        borderWidth: 2.5, fill: true, tension: 0.4,
                        pointBackgroundColor: '#6366f1', pointRadius: 3,
                    },
                    {
                        label: 'RFQs',
                        data:  this.state.charts.spending.foreign,
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245,158,11,0.06)',
                        borderWidth: 2, fill: true, tension: 0.4,
                        borderDash: [5, 3],
                        pointBackgroundColor: '#f59e0b', pointRadius: 3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: true, position: 'top', labels: { boxWidth: 10, padding: 12, font: { size: 11 } } },
                    tooltip: { callbacks: { label: (c) => `  ${c.dataset.label}: ${this.formatCurrency(c.raw)}` } },
                },
                scales: {
                    y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.04)' }, ticks: { callback: v => this.formatCompact(v), font: { size: 10 } } },
                    x: { grid: { display: false }, ticks: { font: { size: 10 } } },
                },
            },
        });
    }

    _renderPOStatusChart() {
        const ctx = this.poStatusCanvasRef.el?.getContext("2d");
        if (!ctx) return;
        this.poStatusChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: this.state.charts.po_status.labels,
                datasets: [{
                    data: this.state.charts.po_status.values,
                    backgroundColor: ['#6366f1','#10b981','#f59e0b','#8b5cf6','#ef4444','#3b82f6','#6b7280','#ec4899'],
                    borderWidth: 2,
                    borderColor: '#fff',
                    hoverOffset: 6,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { boxWidth: 10, padding: 8, font: { size: 10 },
                            generateLabels: (chart) => {
                                const data = chart.data;
                                const total = data.datasets[0].data.reduce((a,b) => a+b, 0);
                                return data.labels.map((label, i) => {
                                    const val = data.datasets[0].data[i];
                                    const pct = total ? ((val/total)*100).toFixed(1) : 0;
                                    return {
                                        text: `${label}  ${val} (${pct}%)`,
                                        fillStyle: data.datasets[0].backgroundColor[i],
                                        hidden: false,
                                        index: i,
                                    };
                                });
                            }
                        },
                    },
                },
                cutout: '62%',
            },
        });
    }

    _renderVendorSpendChart() {
        const ctx = this.vendorSpendCanvasRef.el?.getContext("2d");
        if (!ctx) return;
        const colors = ['#3b82f6','#10b981','#f59e0b','#8b5cf6','#ef4444'];
        this.vendorSpendChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: this.state.charts.vendor_spend.labels,
                datasets: [{
                    label: 'Total Spend (ETB)',
                    data: this.state.charts.vendor_spend.values,
                    backgroundColor: this.state.charts.vendor_spend.labels.map((_, i) => colors[i % colors.length]),
                    borderRadius: 4,
                    barThickness: 14,
                }],
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (c) => ` Spend: ${this.formatCurrency(c.raw)}` } },
                },
                scales: {
                    x: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.04)' }, ticks: { callback: v => this.formatCompact(v), font: { size: 10 } } },
                    y: { grid: { display: false }, ticks: { font: { size: 10 } } },
                },
            },
        });
    }

    _renderDeptChart() {
        const ctx = this.deptCanvasRef.el?.getContext("2d");
        if (!ctx) return;
        const dept = this.state.charts.department;
        this.deptChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: dept.labels,
                datasets: [
                    { label: 'Local PR Amount',   data: dept.local,   backgroundColor: 'rgba(99,102,241,0.8)',  borderRadius: 3 },
                    { label: 'Foreign PR Amount', data: dept.foreign, backgroundColor: 'rgba(245,158,11,0.8)', borderRadius: 3 },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { position: 'top', labels: { boxWidth: 10, padding: 12, font: { size: 11 } } },
                    tooltip: { callbacks: { label: (c) => `  ${c.dataset.label}: ${this.formatCurrency(c.raw)}` } },
                },
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 30 } },
                    y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.04)' }, ticks: { callback: v => this.formatCompact(v), font: { size: 10 } } },
                },
            },
        });
    }

    // ── Navigation ────────────────────────────────────────────────────────
    openRecord(model, id) {
        this.actionService.doAction({ type: "ir.actions.act_window", res_model: model, res_id: id, views: [[false,"form"]], target: "current" });
    }

    openListView(model, domain = [], name = "Records") {
        this.actionService.doAction({ type: "ir.actions.act_window", name, res_model: model, domain, views: [[false,"list"],[false,"form"]], target: "current" });
    }

    // ── Formatters ────────────────────────────────────────────────────────
    formatCurrency(value) {
        if (!value) return 'ETB 0';
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'ETB', maximumFractionDigits: 0 }).format(value);
    }

    formatCompact(value) {
        if (value >= 1_000_000) return (value / 1_000_000).toFixed(1) + 'M';
        if (value >= 1_000)     return (value / 1_000).toFixed(0) + 'K';
        return value;
    }

    _fmtDatetime(d) {
        return d.toLocaleString('en-US', { month: 'short', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    }
}

registry.category("actions").add("procurement_dashboard.dashboard_view", ProcurementDashboard);
