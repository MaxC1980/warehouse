from database import get_db_connection


class InventoryService:
    @staticmethod
    def get_inventory(page=1, per_page=20, keyword=None, summary=False, category_code=None, status=None):
        """Get inventory - summary for material汇总, detail for batch明细"""
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * per_page

        where_clauses = ["i.quantity > 0"]
        params = []

        if keyword:
            where_clauses.append("(m.code LIKE ? OR m.name LIKE ? OR m.spec LIKE ?)")
            params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])

        if category_code:
            where_clauses.append("m.category_code LIKE ?")
            params.append(f'{category_code}%')

        if status:
            from datetime import datetime
            # 用 INSTR 找分隔符位置，兼容非标准格式如 '2026-4-15'
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

        where_sql = "WHERE " + " AND ".join(where_clauses)

        if summary:
            count_query = f"""
                SELECT COUNT(DISTINCT m.code) as count
                FROM inventory i
                JOIN material m ON i.material_id = m.id
                {where_sql}
            """
            cursor.execute(count_query, params)
            total = cursor.fetchone()['count']

            cursor.execute(
                f"""
                SELECT
                    m.code as material_code, m.name as material_name,
                    m.spec, m.unit, m.manufacturer,
                    SUM(i.quantity) as quantity,
                    MAX(i.updated_at) as updated_at
                FROM inventory i
                JOIN material m ON i.material_id = m.id
                {where_sql}
                GROUP BY m.code, m.name, m.spec, m.unit, m.manufacturer
                ORDER BY m.code
                LIMIT ? OFFSET ?
                """,
                params + [per_page, offset]
            )
            inventory = []
            for row in cursor.fetchall():
                item = dict(row)
                item['status'] = '正常'
                inventory.append(item)
        else:
            count_query = f"""
                SELECT COUNT(*) as count
                FROM inventory i
                JOIN material m ON i.material_id = m.id
                {where_sql}
            """
            cursor.execute(count_query, params)
            total = cursor.fetchone()['count']

            cursor.execute(
                f"""
                SELECT
                    m.id as material_id, m.code as material_code, m.name as material_name,
                    m.spec, m.unit, m.manufacturer, m.storage_condition, m.shelf_life,
                    i.batch_no, i.production_date, i.expiry_date,
                    i.quantity, i.updated_at
                FROM inventory i
                JOIN material m ON i.material_id = m.id
                {where_sql}
                ORDER BY m.code, i.batch_no
                LIMIT ? OFFSET ?
                """,
                params + [per_page, offset]
            )

            inventory = []
            inventory_map = {}

            for row in cursor.fetchall():
                item = dict(row)
                # SQL 已按状态过滤，精确赋值；status=None 时需动态判断
                if status == '过期':
                    item['status'] = '过期'
                elif status == '正常':
                    item['status'] = '正常'
                else:
                    # 全部时动态判断
                    from datetime import date, datetime
                    today = date.today()
                    expiry = item.get('expiry_date')
                    if expiry:
                        if isinstance(expiry, str):
                            try:
                                expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
                            except:
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

            # 待审入库：先按批次匹配到已有库存行，匹配不上才新增行
            pending_in_where = "WHERE io.status = 'pending'"
            pending_in_params = []
            if category_code:
                pending_in_where += " AND m.category_code LIKE ?"
                pending_in_params.append(f'{category_code}%')
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
                key = (row['material_id'], row['batch_no'])
                if key in inventory_map:
                    idx = inventory_map[key]
                    inventory[idx]['pending_in'] += row['quantity']
                else:
                    item = dict(row)
                    item['quantity'] = 0
                    item['status'] = '正常'
                    item['pending_in'] = row['quantity']
                    item['pending_out'] = 0
                    inventory.append(item)
                    inventory_map[key] = len(inventory) - 1
                    total += 1

            inventory.sort(key=lambda x: (x['material_code'], x.get('batch_no', '')))

        # 待审出库：匹配到已有库存行，不新增行
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

        conn.close()
        return inventory, total

    @staticmethod
    def get_inventory_by_material(material_id):
        conn = get_db_connection()
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
        conn.close()

        if row:
            item = dict(row)
            item['status'] = '正常'
            return item
        return None

    @staticmethod
    def get_inventory_details(material_id):
        """Get all batch details for a material"""
        conn = get_db_connection()
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
        conn.close()
        return details

    @staticmethod
    def update_inventory(material_id, quantity_change, batch_no=None, production_date=None, expiry_date=None, in_order_item_id=None):
        """Add inventory - UPSERT on (material_id, batch_no)"""
        if not batch_no:
            from datetime import datetime
            batch_no = f"AUTO-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        conn = get_db_connection()
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
                        (material_id, batch_no, production_date, expiry_date, quantity_change, in_order_item_id)
                    )

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    @staticmethod
    def reduce_inventory(material_id, quantity, batch_no=None):
        """Reduce inventory for outbound - deduct from specified batch or oldest batch"""
        conn = get_db_connection()
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
                    conn.close()
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
                    conn.close()
                    raise Exception(f"库存不足: 物料ID {material_id}")

                cursor.execute(
                    """UPDATE inventory
                       SET quantity = ROUND(quantity - ?, 2), updated_at = datetime('now', 'localtime')
                       WHERE id = ?""",
                    (quantity, batch['id'])
                )

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    @staticmethod
    def import_inventory(data):
        """Import initial inventory from list of dictionaries"""
        conn = get_db_connection()
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
                    except:
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
                        """UPDATE inventory SET quantity = ?, updated_at = datetime('now', 'localtime')
                           WHERE material_id = ? AND batch_no = ?""",
                        (quantity, material_id, batch_no)
                    )
                else:
                    cursor.execute(
                        """INSERT INTO inventory (material_id, batch_no, production_date, expiry_date, quantity)
                           VALUES (?, ?, ?, ?, ?)""",
                        (material_id, batch_no, production_date, expiry_date, quantity)
                    )

                conn.commit()
                success += 1
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                failed += 1

        conn.close()
        return {'success': success, 'failed': failed, 'errors': errors}

    @staticmethod
    def get_inventory_for_select(category_code=None, material_code=None, material_name=None, material_spec=None, page=1, per_page=50):
        """库存选择接口，返回物料+批次+库存信息，支持多条件过滤和分页"""
        conn = get_db_connection()
        cursor = conn.cursor()

        where_clauses = ["i.quantity > 0"]
        params = []

        if category_code:
            where_clauses.append("m.category_code LIKE ?")
            params.append(f"{category_code}%")
        if material_code:
            where_clauses.append("m.code LIKE ?")
            params.append(f"%{material_code}%")
        if material_name:
            where_clauses.append("m.name LIKE ?")
            params.append(f"%{material_name}%")
        if material_spec:
            where_clauses.append("m.spec LIKE ?")
            params.append(f"%{material_spec}%")

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
        conn.close()
        return items, total
