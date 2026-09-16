#!/bin/bash
set -euo pipefail
DEST=/opt/odoo/instances/odoo19/addons
SRC=/tmp/odoo-replacements
cd /opt/odoo/instances/odoo19
cp -a "$SRC"/. "$DEST"/
chmod -R a+rX "$DEST"/payroll "$DEST"/web_gantt "$DEST"/web_grid "$DEST"/web_map "$DEST"/web_cohort \
  "$DEST"/sale_enterprise "$DEST"/stock_enterprise "$DEST"/hr_work_entry_enterprise \
  "$DEST"/hr_work_entry_holidays_enterprise "$DEST"/hr_gantt "$DEST"/hr_holidays_gantt \
  "$DEST"/contacts_enterprise "$DEST"/analytic_enterprise "$DEST"/currency_rate_live \
  "$DEST"/iap_extract "$DEST"/product_barcodelookup "$DEST"/ai_auto_install
docker compose exec -T db psql -U odoo -d ease_community <<'SQL'
UPDATE ir_ui_view
   SET type = 'list'
 WHERE type IN ('gantt', 'map', 'grid', 'cohort');

UPDATE ir_act_window
   SET view_mode = trim(both ',' FROM regexp_replace(
         regexp_replace(
           regexp_replace(
             regexp_replace(view_mode, '(^|,)gantt(,|$)', '\1list\2', 'g'),
           '(^|,)map(,|$)', '\1list\2', 'g'),
         '(^|,)grid(,|$)', '\1list\2', 'g'),
       '(^|,)cohort(,|$)', '\1list\2', 'g'))
 WHERE view_mode ~ '(gantt|map|grid|cohort)';

UPDATE ir_act_window
   SET view_mode = regexp_replace(view_mode, '(list,){2,}', 'list,', 'g')
 WHERE view_mode LIKE '%list,list%';
SQL
docker compose restart odoo
sleep 10
docker compose logs --tail=25 odoo
