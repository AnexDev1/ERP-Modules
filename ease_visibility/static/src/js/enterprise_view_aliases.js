/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";

const viewRegistry = registry.category("views");
const aliases = [
    "gantt",
    "map",
    "grid",
    "cohort",
    "stock_map",
    "work_entries_gantt",
    "hr_holidays_gantt",
    "hr_holidays_gantt_manager",
    "hr_holidays_gantt_manager_hr_leave",
    "hr_holidays_payslip_list",
    "analytic_line_grid",
];
for (const type of aliases) {
    if (!viewRegistry.contains(type)) {
        viewRegistry.add(type, {...listView, type});
    }
}
