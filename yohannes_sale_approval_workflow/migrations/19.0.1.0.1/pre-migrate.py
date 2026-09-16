def migrate(cr, version):
    if not version:
        return

    # 1. Safely add columns to sale_order if missing
    cr.execute("""
        ALTER TABLE sale_order 
        ADD COLUMN IF NOT EXISTS is_manual_sale BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS manual_sale_reference VARCHAR;
    """)

    # 2. Safely add columns to res_company if missing
    cr.execute("""
        ALTER TABLE res_company 
        ADD COLUMN IF NOT EXISTS use_so_manual_sequence_limit BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS so_manual_sequence_limit INTEGER DEFAULT 0;
    """)

    # 3. Safely add columns to account_journal if missing
    cr.execute("""
        ALTER TABLE account_journal 
        ADD COLUMN IF NOT EXISTS use_manual_sequence_limit BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS manual_sequence_limit INTEGER DEFAULT 0;
    """)

    # 4. Clean up any stale view overrides referencing _setup_picking_reports
    cr.execute("""
        DELETE FROM ir_ui_view WHERE arch_db::text LIKE '%_setup_picking_reports%';
    """)


    # 5. Reset stuck module states before upgrade steps
    cr.execute("""
        UPDATE ir_module_module 
        SET state = 'installed' 
        WHERE state IN ('to upgrade', 'to install', 'to remove', 'upgrading');
    """)
