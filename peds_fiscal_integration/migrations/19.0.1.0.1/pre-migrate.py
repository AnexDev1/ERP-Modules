def migrate(cr, version):
    cr.execute("ALTER TABLE res_company ADD COLUMN IF NOT EXISTS peds_api_key VARCHAR;")
