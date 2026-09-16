# -*- coding: utf-8 -*-

def migrate(cr, version):
    if not version:
        return

    # 1. Move non-manual invoices currently using 00001-00100 to 00102+ to free up range for manual invoices
    cr.execute("""
        SELECT id, name FROM account_move 
        WHERE (is_manual_invoice IS NOT True) AND name LIKE 'INV/2026/000%' 
        ORDER BY id ASC
    """)
    old_non_manual = cr.fetchall()
    for idx, (m_id, m_name) in enumerate(old_non_manual, start=102):
        cr.execute("UPDATE account_move SET name = %s WHERE id = %s", (f"TEMP_{m_id}", m_id))

    # 2. Set manual invoices to temp names to avoid unique constraint collisions
    cr.execute("""
        SELECT id, name FROM account_move 
        WHERE is_manual_invoice = True 
        ORDER BY create_date ASC, id ASC
    """)
    manual_moves = cr.fetchall()
    for m_id, m_name in manual_moves:
        cr.execute("UPDATE account_move SET name = %s WHERE id = %s", (f"MAN_TEMP_{m_id}", m_id))

    # 3. Resequence manual invoices strictly 1, 2, 3, 4...
    for idx, (m_id, m_name) in enumerate(manual_moves, start=1):
        new_name = f"INV/2026/{idx:05d}"
        cr.execute("UPDATE account_move SET name = %s WHERE id = %s", (new_name, m_id))

    # 4. Assign new names to shifted non-manual moves
    for idx, (m_id, m_name) in enumerate(old_non_manual, start=102):
        new_name = f"INV/2026/{idx:05d}"
        cr.execute("UPDATE account_move SET name = %s WHERE id = %s", (new_name, m_id))
