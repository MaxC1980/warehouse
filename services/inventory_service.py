from database import get_db_connection
from datetime import date, datetime, timedelta


def _normalize_date(date_str):
    """将日期标准化为YYYYMMDD格式用于排序，兼容 '2026-4-15' 和 '2026-04-15'"""
    if not date_str:
        return '00000000'
    parts = date_str.split('-')
    if len(parts) != 3:
        return '00000000'
    year, month, day = parts
    return f"{year}{int(month):02d}{int(day):02d}"


def _expiry_matches_filter(expiry_date, status):
    """判断物品的过期日期是否符合筛选条件：是否已到或超过指定月份末"""
    if not expiry_date:
        return False
    try:
        if isinstance(expiry_date, str):
            expiry = datetime.strptime(expiry_date, '%Y-%m-%d').date()
        else:
            expiry = expiry_date
    except Exception:
        return False

    today = date.today()

    if status == '过期':
        return expiry < today
    elif status == '本月过期':
        if today.month == 12:
            last_day = today.replace(year=today.year+1, month=1, day=1) - timedelta(days=1)
        else:
            last_day = today.replace(month=today.month+1, day=1) - timedelta(days=1)
        return expiry <= last_day
    elif status == '下月过期':
        if today.month == 12:
            next_month_first = today.replace(year=today.year+1, month=1, day=1)
        else:
            next_month_first = today.replace(month=today.month+1, day=1)
        if next_month_first.month == 12:
            following_month_first = next_month_first.replace(year=next_month_first.year+1, month=1, day=1)
        else:
            following_month_first = next_month_first.replace(month=next_month_first.month+1, day=1)
        last_day = following_month_first - timedelta(days=1)
        return expiry <= last_day
    return False


class InventoryService:
    @staticmethod
    def get_inventory(page=1, per_page=20, keyword=None, summary=False, category_code=None, status=None):
        """Get inventory - summary for material汇总, detail for batch明细"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            offset = (page - 1) * per_page

            where_clauses = ["i.quantity > 0"]
            params = []

            if keyword:
                where_clauses.append("(m.code LIKE ? OR m.name LIKE ? OR m.spec LIKE ? OR m.manufacturer LIKE ?)")
                params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])

            if category_code:
                where_clauses.append("m.category_code LIKE ?")
                params.append(f'{category_code}%')

            if status and not summary:
                from datetime import datetime
                p1 = f"INSTR(i.expiry_date, '-')"
                rest = f"SUBSTR(i.expiry_date, {p1}+1)"
                p2 = f"INSTR({rest}, '-') + {p1}"
                year = f"SUBSTR(i.expiry_date, 1, {p1}-1)"
                month = f"SUBSTR(i.expiry_date, {p1}+1, {p2}-{p1}-1)"
                day = f"SUBSTR(i.expiry_date, {p2}+1)"
                ymd_expr = f"{year} || PRINTF('%02d', CAST({month} AS INTEGER)) || PRINTF('%02d', CAST({day} AS INTEGER))"
                today_ymd = datetime.now().strftime('%Y%m%d')
                if status == '正常':
                    where_clauses.append(f"(i.expiry_date IS NULL OR {ymd_expr} >= '{today_ymd}')")
                elif status == '过期':
                    where_clauses.append(f"{ymd_expr} < '{today_ymd}'")
                elif status == '本月过期':
                    from datetime import timedelta
                    first_day = datetime.now().replace(day=1)
                    if datetime.now().month == 12:
                        next_month = first_day.replace(year=datetime.now().year+1, month=1, day=1)
                    else:
                        next_month = first_day.replace(month=datetime.now().month+1, day=1)
                    last_day = (next_month - timedelta(days=1)).strftime('%Y%m%d')
                    where_clauses.append(f"(i.expiry_date IS NOT NULL AND {ymd_expr} <= '{last_day}')")
                elif status == '下月过期':
                    from datetime import timedelta
                    if datetime.now().month == 12:
                        next_month_first = datetime.now().replace(year=datetime.now().year+1, month=1, day=1)
                    else:
                        next_month_first = datetime.now().replace(month=datetime.now().month+1, day=1)
                    if next_month_first.month == 12:
                        following_month_first = next_month_first.replace(year=next_month_first.year+1, month=1, day=1)
                    else:
                        following_month_first = next_month_first.replace(month=next_month_first.month+1, day=1)
                    first_day = next_month_first.strftime('%Y%m%d')
                    last_day = (following_month_first - timedelta(days=1)).strftime('%Y%m%d')
                    where_clauses.append(f"(i.expiry_date IS NOT NULL AND {ymd_expr} <= '{last_day}')")

            where_sql = "WHERE " + " AND ".join(where_clauses)

            total_quantity = InventoryService.get_inventory_totals(cursor, where_sql, params, summary)

            if summary:
                cursor.execute("""
                    SELECT DISTINCT m.id
                    FROM inventory i
                    JOIN material m ON i.material_id = m.id
                    {where_sql}
                """.format(where_sql=where_sql), params)
                material_ids_with_stock = [row['id'] for row in cursor.fetchall()]

                pending_only_items = []
                pending_only_params = []
                pending_only_where = "WHERE io.status = 'pending'"
                if category_code:
                    pending_only_where += " AND m.category_code LIKE ?"
                    pending_only_params.append(f'{category_code}%')
                cursor.execute(f"""
                    SELECT m.id as material_id, m.code as material_code, m.name as material_name,
                        m.spec, m.unit, m.manufacturer,
                        SUM(ioi.quantity) as pending_in_total
                    FROM in_order_item ioi
                    JOIN in_order io ON ioi.order_id = io.id
                    JOIN material m ON ioi.material_id = m.id
                    {pending_only_where}
                    GROUP BY m.id, m.code, m.name, m.spec, m.unit, m.manufacturer
                """, pending_only_params)
                for row in cursor.fetchall():
                    if row['material_id'] not in material_ids_with_stock:
                        item = dict(row)
                        item['quantity'] = 0
                        item['status'] = '正常'
                        item['pending_in'] = row['pending_in_total']
                        item['pending_out'] = 0
                        item['updated_at'] = ''
                        pending_only_items.append(item)

                all_items = []

                cursor.execute("""
                    SELECT
                        m.id as material_id, m.code as material_code, m.name as material_name,
                        m.spec, m.unit, m.manufacturer,
                        SUM(i.quantity) as quantity,
                        MAX(i.updated_at) as updated_at
                    FROM inventory i
                    JOIN material m ON i.material_id = m.id
                    {where_sql}
                    GROUP BY m.id, m.code, m.name, m.spec, m.unit, m.manufacturer
                """.format(where_sql=where_sql), params)
                for row in cursor.fetchall():
                    item = dict(row)
                    item['status'] = '正常'
                    item['pending_in'] = 0
                    item['pending_out'] = 0
                    all_items.append(item)

                all_items.extend(pending_only_items)
                all_items.sort(key=lambda x: x['material_code'])

                total = len(all_items)
                inventory = all_items[offset:offset + per_page]
                material_ids_in_summary = [item['material_id'] for item in inventory]

                if material_ids_in_summary:
                    mid_placeholders = ','.join(['?'] * len(material_ids_in_summary))
                    pending_in_params = material_ids_in_summary + [f'{category_code}%'] if category_code else material_ids_in_summary
                    pending_in_where = f"AND m.category_code LIKE ?" if category_code else ""
                    cursor.execute(f"""
                        SELECT ioi.material_id, SUM(ioi.quantity) as total
                        FROM in_order_item ioi
                        JOIN in_order io ON ioi.order_id = io.id
                        JOIN material m ON ioi.material_id = m.id
                        WHERE io.status = 'pending' AND ioi.material_id IN ({mid_placeholders}) {pending_in_where}
                        GROUP BY ioi.material_id
                    """, pending_in_params)
                    for row in cursor.fetchall():
                        for item in inventory:
                            if item['material_id'] == row['material_id']:
                                item['pending_in'] = row['total']
                                break

                    cursor.execute(f"""
                        SELECT ooi.material_id, SUM(ooi.actual_quantity) as total
                        FROM out_order_item ooi
                        JOIN out_order oo ON ooi.order_id = oo.id
                        WHERE oo.status = 'pending' AND ooi.material_id IN ({mid_placeholders})
                        GROUP BY ooi.material_id
                    """, material_ids_in_summary)
                    for row in cursor.fetchall():
                        for item in inventory:
                            if item['material_id'] == row['material_id']:
                                item['pending_out'] = row['total']
                                break

                return inventory, total, total_quantity
            else:
                cursor.execute(f"""
                    SELECT DISTINCT i.material_id, i.batch_no
                    FROM inventory i
                    JOIN material m ON i.material_id = m.id
                    {where_sql}
                """, params)
                stock_keys = set((row['material_id'], row['batch_no']) for row in cursor.fetchall())

                pending_in_where = "WHERE io.status = 'pending'"
                pending_in_params = []
                if category_code:
                    pending_in_where += " AND m.category_code LIKE ?"
                    pending_in_params.append(f'{category_code}%')

                pending_items = []
                cursor.execute(f"""
                    SELECT
                        m.id as material_id, m.code as material_code, m.name as material_name,
                        m.spec, m.unit, m.manufacturer, m.storage_condition, m.shelf_life,
                        ioi.batch_no, ioi.production_date, ioi.expiry_date,
                        ioi.quantity, io.created_at as updated_at
                    FROM in_order_item ioi
                    JOIN in_order io ON ioi.order_id = io.id
                    JOIN material m ON ioi.material_id = m.id
                    {pending_in_where}
                    ORDER BY m.code, ioi.batch_no
                """, pending_in_params)
                for row in cursor.fetchall():
                    item = dict(row)
                    item['pending_in'] = item['quantity']
                    item['pending_out'] = 0
                    item['quantity'] = 0
                    item['status'] = '正常'
                    if status in ('过期', '本月过期', '下月过期'):
                        if _expiry_matches_filter(item.get('expiry_date'), status):
                            pending_items.append(item)
                    elif status in ('正常', None, ''):
                        pending_items.append(item)

                cursor.execute(f"""
                    SELECT
                        m.id as material_id, m.code as material_code, m.name as material_name,
                        m.spec, m.unit, m.manufacturer, m.storage_condition, m.shelf_life,
                        i.batch_no, i.production_date, i.expiry_date,
                        i.quantity, i.updated_at
                    FROM inventory i
                    JOIN material m ON i.material_id = m.id
                    {where_sql}
                    ORDER BY m.code, i.batch_no
                """, params)

                inventory = []
                inventory_map = {}

                for row in cursor.fetchall():
                    item = dict(row)
                    if status == '过期':
                        item['status'] = '过期'
                    elif status == '正常':
                        item['status'] = '正常'
                    else:
                        from datetime import date, datetime
                        today = date.today()
                        expiry = item.get('expiry_date')
                        if expiry:
                            if isinstance(expiry, str):
                                try:
                                    expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
                                except Exception:
                                    expiry_date = None
                            else:
                                expiry_date = expiry
                            item['status'] = '过期' if expiry_date and expiry_date < today else '正常'
                        else:
                            item['status'] = '正常'
                    item['pending_in'] = 0
                    item['pending_out'] = 0
                    inventory.append(item)
                    inventory_map[(item['material_id'], item['batch_no'])] = len(inventory) - 1

                for item in pending_items:
                    key = (item['material_id'], item['batch_no'])
                    if key not in stock_keys:
                        inventory.append(item)
                        inventory_map[key] = len(inventory) - 1
                    else:
                        if key in inventory_map:
                            idx = inventory_map[key]
                            inventory[idx]['pending_in'] += item['pending_in']

                total = len(inventory)

                if status in ('过期', '本月过期', '下月过期'):
                    inventory.sort(key=lambda x: (_normalize_date(x.get('expiry_date')), x['material_code'], x.get('batch_no', '')))
                else:
                    inventory.sort(key=lambda x: (x['material_code'], x.get('batch_no', '')))

                inventory = inventory[offset:offset + per_page]
                inventory_map = {(item['material_id'], item['batch_no']): idx for idx, item in enumerate(inventory)}

            if not summary and inventory:
                material_ids = [item['material_id'] for item in inventory]
                batch_nos = [item['batch_no'] for item in inventory if item['batch_no']]
                if material_ids and batch_nos:
                    placeholders_ids = ','.join(['?'] * len(material_ids))
                    placeholders_batches = ','.join(['?'] * len(batch_nos))
                    query = ("SELECT material_id, batch_no, COALESCE(SUM(actual_quantity), 0) as total "
                             "FROM out_order_item ooi "
                             "JOIN out_order oo ON ooi.order_id = oo.id "
                             "WHERE oo.status = 'pending' "
                             "AND ooi.material_id IN ({}) "
                             "AND ooi.batch_no IN ({}) "
                             "GROUP BY ooi.material_id, ooi.batch_no").format(placeholders_ids, placeholders_batches)
                    cursor.execute(query, material_ids + batch_nos)
                    pending_out_map = {(row['material_id'], row['batch_no']): row['total'] for row in cursor.fetchall()}
                    for item in inventory:
                        key = (item['material_id'], item['batch_no'])
                        item['pending_out'] = pending_out_map.get(key, 0)

            if status in ('过期', '本月过期', '下月过期'):
                inventory.sort(key=lambda x: (_normalize_date(x.get('expiry_date')), x['material_code'], x.get('batch_no', '')))
            else:
                inventory.sort(key=lambda x: (x['material_code'], x.get('batch_no', '')))

            return inventory, total, total_quantity

    @staticmethod
    def get_inventory_totals(cursor, where_sql, params, summary=False):
        """Get total quantity sum for inventory"""
        cursor.execute(
            f"""
            SELECT COALESCE(SUM(i.quantity), 0) as total_quantity
            FROM inventory i
            JOIN material m ON i.material_id = m.id
            {where_sql}
            """,
            params
        )
        result = cursor.fetchone()
        return result['total_quantity'] if result else 0

    @staticmethod
    def get_inventory_by_material(material_id):
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    m.id, m.code as material_code, m.name as material_name,
                    m.spec, m.unit, m.storage_condition, m.shelf_life,
                    SUM(i.quantity) as quantity,
                    MIN(i.expiry_date) as earliest_expiry,
                    MAX(i.updated_at) as updated_at
                FROM inventory i
                JOIN material m ON i.material_id = m.id
                WHERE m.id = ? AND i.quantity > 0
                GROUP BY m.id
                """,
                (material_id,)
            )
            row = cursor.fetchone()

            if row:
                item = dict(row)
                item['status'] = '正常'
                return item
            return None

    @staticmethod
    def get_inventory_details(material_id):
        """Get all batch details for a material"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    id, material_id, batch_no, production_date, expiry_date,
                    quantity, updated_at
                FROM inventory
                WHERE material_id = ? AND quantity > 0
                ORDER BY batch_no
                """,
                (material_id,)
            )
            details = [dict(row) for row in cursor.fetchall()]
            return details

    @staticmethod
    def update_inventory(material_id, quantity_change, batch_no=None, production_date=None, expiry_date=None, in_order_item_id=None):
        """Add inventory - UPSERT on (material_id, batch_no)"""
        if not batch_no:
            from datetime import datetime
            batch_no = f"AUTO-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")

            try:
                if batch_no:
                    cursor.execute(
                        "SELECT id, quantity FROM inventory WHERE material_id = ? AND batch_no = ?",
                        (material_id, batch_no)
                    )
                    existing = cursor.fetchone()

                    if existing:
                        cursor.execute(
                            """UPDATE inventory
                               SET quantity = ROUND(quantity + ?, 2), updated_at = datetime('now', 'localtime')
                               WHERE material_id = ? AND batch_no = ?""",
                            (quantity_change, material_id, batch_no)
                        )
                    else:
                        cursor.execute(
                            """INSERT INTO inventory (material_id, batch_no, production_date, expiry_date, quantity, in_order_item_id)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (material_id, batch_no, production_date, expiry_date, round(quantity_change, 2), in_order_item_id)
                        )

                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                raise e

    @staticmethod
    def reduce_inventory(material_id, quantity, batch_no=None):
        """Reduce inventory for outbound - deduct from specified batch or oldest batch"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")

            try:
                if batch_no:
                    cursor.execute(
                        """UPDATE inventory
                           SET quantity = ROUND(quantity - ?, 2), updated_at = datetime('now', 'localtime')
                           WHERE material_id = ? AND batch_no = ? AND quantity >= ?""",
                        (quantity, material_id, batch_no, quantity)
                    )
                    if cursor.rowcount == 0:
                        raise Exception(f"库存不足或批次不存在: 物料ID {material_id}, 批次 {batch_no}")
                else:
                    cursor.execute(
                        """SELECT id, quantity FROM inventory
                           WHERE material_id = ? AND quantity > 0
                           ORDER BY expiry_date ASC, batch_no ASC
                           LIMIT 1""",
                        (material_id,)
                    )
                    batch = cursor.fetchone()
                    if not batch or batch['quantity'] < quantity:
                        raise Exception(f"库存不足: 物料ID {material_id}")

                    cursor.execute(
                        """UPDATE inventory
                           SET quantity = ROUND(quantity - ?, 2), updated_at = datetime('now', 'localtime')
                           WHERE id = ?""",
                        (quantity, batch['id'])
                    )

                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                raise e

    @staticmethod
    def import_inventory(data):
        """Import initial inventory from list of dictionaries"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            success = 0
            failed = 0
            errors = []

            for idx, row in enumerate(data):
                try:
                    material_code = row.get('material_code')
                    quantity = row.get('quantity')
                    batch_no = row.get('batch_no') or None
                    production_date = row.get('production_date') or None
                    expiry_date = row.get('expiry_date') or None

                    if quantity is None:
                        quantity = 0
                    else:
                        try:
                            quantity = float(quantity)
                        except Exception:
                            raise ValueError(f"数量必须是数字，当前值: {quantity}")

                    if not batch_no:
                        from datetime import datetime
                        batch_no = f"IMP-{datetime.now().strftime('%Y%m%d%H%M%S')}"

                    if not material_code:
                        errors.append(f"Row {idx + 2}: Missing material_code")
                        failed += 1
                        continue

                    material_code = str(material_code)

                    cursor.execute("SELECT id FROM material WHERE code = ?", (material_code,))
                    material = cursor.fetchone()
                    if not material:
                        errors.append(f"Row {idx + 2}: Material with code '{material_code}' not found")
                        failed += 1
                        continue

                    material_id = material['id']

                    cursor.execute(
                        "SELECT id FROM inventory WHERE material_id = ? AND batch_no = ?",
                        (material_id, batch_no)
                    )
                    existing = cursor.fetchone()

                    if existing:
                        cursor.execute(
                            """UPDATE inventory SET quantity = ROUND(?, 2), updated_at = datetime('now', 'localtime')
                               WHERE material_id = ? AND batch_no = ?""",
                            (quantity, material_id, batch_no)
                        )
                    else:
                        cursor.execute(
                            """INSERT INTO inventory (material_id, batch_no, production_date, expiry_date, quantity)
                               VALUES (?, ?, ?, ?, ?)""",
                            (material_id, batch_no, production_date, expiry_date, round(quantity, 2))
                        )

                    conn.commit()
                    success += 1
                except Exception as e:
                    errors.append(f"Row {idx + 2}: {str(e)}")
                    failed += 1

            return {'success': success, 'failed': failed, 'errors': errors}

    @staticmethod
    def get_inventory_for_select(category_code=None, keyword=None, page=1, per_page=50):
        """库存选择接口，返回物料+批次+库存信息，支持多条件过滤和分页"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            where_clauses = ["i.quantity > 0"]
            params = []

            if category_code:
                where_clauses.append("m.category_code LIKE ?")
                params.append(f"{category_code}%")
            if keyword:
                where_clauses.append("(m.code LIKE ? OR m.name LIKE ? OR m.spec LIKE ? OR m.manufacturer LIKE ?)")
                params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])

            where_sql = "WHERE " + " AND ".join(where_clauses)

            cursor.execute(
                f"""
                SELECT COUNT(*) as count
                FROM inventory i
                JOIN material m ON i.material_id = m.id
                {where_sql}
                """,
                params
            )
            total = cursor.fetchone()['count']

            offset = (page - 1) * per_page
            cursor.execute(
                f"""
                SELECT
                    i.id as inventory_id,
                    i.material_id,
                    i.batch_no,
                    i.quantity as available_qty,
                    i.production_date,
                    i.expiry_date,
                    m.code as material_code,
                    m.name as material_name,
                    m.spec as material_spec,
                    m.manufacturer,
                    m.unit,
                    m.category_code,
                    m.is_reusable as material_is_reusable
                FROM inventory i
                JOIN material m ON i.material_id = m.id
                {where_sql}
                ORDER BY m.code, i.batch_no
                LIMIT ? OFFSET ?
                """,
                params + [per_page, offset]
            )

            items = [dict(row) for row in cursor.fetchall()]
            return items, total
