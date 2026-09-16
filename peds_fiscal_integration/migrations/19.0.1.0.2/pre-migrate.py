def migrate(cr, version):
    if not version:
        return

    # 1. Safely add columns to res_company if missing
    cr.execute("""
        ALTER TABLE res_company 
        ADD COLUMN IF NOT EXISTS peds_api_key VARCHAR,
        ADD COLUMN IF NOT EXISTS peds_license_keys VARCHAR,
        ADD COLUMN IF NOT EXISTS peds_tenant_id VARCHAR,
        ADD COLUMN IF NOT EXISTS peds_api_url VARCHAR;
    """)

    # 2. Populate default URL and API Key for companies if NULL or empty
    cr.execute("""
        UPDATE res_company 
        SET peds_api_key = 'a00d2fb00aa04fa7a4e9966c6f955b40'
        WHERE peds_api_key IS NULL OR peds_api_key = '';

        UPDATE res_company 
        SET peds_api_url = 'http://localhost:8545/pedsfpsrv/api/SalesInvoice'
        WHERE peds_api_url IS NULL OR peds_api_url = '';
    """)

    # 3. Safely add columns to account_move if missing
    cr.execute("""
        ALTER TABLE account_move 
        ADD COLUMN IF NOT EXISTS peds_printed BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS peds_fp_machine_id VARCHAR,
        ADD COLUMN IF NOT EXISTS peds_fs_invoice_number VARCHAR,
        ADD COLUMN IF NOT EXISTS peds_ej_number VARCHAR,
        ADD COLUMN IF NOT EXISTS peds_time_stamp TIMESTAMP,
        ADD COLUMN IF NOT EXISTS is_manual_invoice BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS manual_receipt_reference VARCHAR;
    """)

    # 4. Reset stuck module states before upgrade steps
    cr.execute("""
        UPDATE ir_module_module 
        SET state = 'installed' 
        WHERE state IN ('to upgrade', 'to install', 'to remove', 'upgrading');
    """)
