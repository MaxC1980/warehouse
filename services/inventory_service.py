import logging
from database import get_db_connection
from utils.sql import escape_like
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)


def _normalize_date(date_str):
    """将日期标准化为YYYYMMDD格式用于排序，兼容 '2026-4-15' 和 '2026-04-15'"""
    if not date_str:
        return '00000000'
    parts = date_str.split('-')
    if len(parts) != 3:
        return '00000000'
    year, month, day = parts
    return f"{year}{int(month):02d}{int(day):02d}"


def _expiry_filter_bounds(status):
    """业务规则集中: status → (operator, ymd_value, require_non_null)

    返回 None 表示该 status 不参与日期过滤 (例如 None 或未识别值)。
    SQL 端用 (op, ymd_value) 拼 WHERE, Python 端用同一 bounds 比较 date 对象。
    require_non_null: True 表示 SQL 需加 `expiry_date IS NOT NULL AND`,
    Python 端 `_expiry_matches_filter` 也用此标志在空值时直接 False。
    """
    today = date.today()
    if status == '过期':
        return ('<', today.strftime('%Y%m%d'), False)
    if status == '正常':
        return ('>=', today.strftime('%Y%m%d'), False)
    if status == '本月过期':
        if today.month == 12:
            last_day = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last_day = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        return ('<=', last_day.strftime('%Y%m%d'), True)
    if status == '下月过期':
        if today.month == 12:
            next_month_first = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month_first = today.replace(month=today.month + 1, day=1)
        if next_month_first.month == 12:
            following_month_first = next_month_first.replace(year=next_month_first.year + 1, month=1, day=1)
        else:
            following_month_first = next_month_first.replace(month=next_month_first.month + 1, day=1)
        last_day = following_month_first - timedelta(days=1)
        return ('<=', last_day.strftime('%Y%m%d'), True)
    return None


def _expiry_matches_filter(expiry_date, status):
    """判断单条记录的 expiry_date 是否符合 status 过滤 (复用 _expiry_filter_bounds)"""
    if not expiry_date:
        return False
    bounds = _expiry_filter_bounds(status)
    if bounds is None:
        return False
    op, ymd_value, _ = bounds
    if isinstance(expiry_date, str):
        try:
            expiry = datetime.strptime(expiry_date, '%Y-%m-%d').date()
        except Exception:
            logger.debug('日期解析失败: %s', expiry_date)
            return False
    else:
        expiry = expiry_date
    target = datetime.strptime(ymd_value, '%Y%m%d').date()
    if op == '<':
        return expiry < target
    if op == '<=':
        return expiry <= target
    if op == '>=':
        return expiry >= target
    return False


class InventoryService:
    @staticmethod
    def _build_inventory_filters(keyword, category_code, status, summary):
        """构造 inventory 列表查询的 WHERE 子句和参数 (keyword + category + status SQL 过滤)

        status 仅在 detail 模式 (非 summary) 时下推到 SQL, 用 ymd_expr 避免日期字符串比较错误。
        无 expiry_date 的行在 ymd_expr 比较中为 NULL, 自然被 WHERE 排除, 不会算作过期。
        """
        where_clauses = ["i.quantity > 0"]
        params = []
        if keyword:
            kw = escape_like(keyword)
            where_clauses.append(
                "(m.code LIKE ? ESCAPE '\' OR m.name LIKE ? ESCAPE '\' "
                "OR m.spec LIKE ? ESCAPE '\' OR m.manufacturer LIKE ? ESCAPE '\')"
            )
            params.extend([f'%{kw}%', f'%{kw}%', f'%{kw}%', f'%{kw}%'])
        if category_code:
            where_clauses.append("m.category_code LIKE ?")
            params.append(f'{category_code}%')

        if status and not summary:
            bounds = _expiry_filter_bounds(status)
            if bounds:
                op, ymd_value, require_non_null = bounds
                ymd_expr = (
                    f"SUBSTR(i.expiry_date, 1, INSTR(i.expiry_date, '-')-1) "
                    f"|| PRINTF('%02d', CAST(SUBSTR(i.expiry_date, "
                    f"INSTR(i.expiry_date, '-')+1, "
                    f"INSTR(SUBSTR(i.expiry_date, INSTR(i.expiry_date, '-')+1), '-')"
                    f") AS INTEGER)) "
                    f"|| PRINTF('%02d', CAST(SUBSTR(i.expiry_date, "
                    f"INSTR(SUBSTR(i.expiry_date, INSTR(i.expiry_date, '-')+1), '-')"
                    f"+INSTR(i.expiry_date, '-')+1) AS INTEGER))"
                )
                # '正常' 允许 expiry_date IS NULL, 其他依赖 bounds 的 require_non_null
                if status == '正常':
                    where_clauses.append(
                        f"(i.expiry_date IS NULL OR {ymd_expr} {op} '{ymd_value}')"
                    )
                else:
                    prefix = "i.expiry_date IS NOT NULL AND " if require_non_null else ""
                    where_clauses.append(f"{prefix}{ymd_expr} {op} '{ymd_value}'")

        return "WHERE " + " AND ".join(where_clauses), params

    @staticmethod
    def _compute_status(expiry_date, status_filter):
        """根据 status_filter 决定单条 inventory 的 status 字段值"""
        if status_filter == '过期':
            return '过期'
        if status_filter == '正常':
            return '正常'
        # 本月过期 / 下月过期 / None: 按实际 expiry 计算
        today = date.today()
        if not expiry_date:
            return '正常'
        if isinstance(expiry_date, str):
            try:
                expiry = datetime.strptime(expiry_date, '%Y-%m-%d').date()
            except Exception:
                return '正常'
        else:
            expiry = expiry_date
        return '过期' if expiry < today else '正常'

    @staticmethod
    def _get_summary_inventory(cursor, where_sql, params, category_code, page, per_page):
        """summary 模式: 按物料汇总, 含 stock + pending_only 合并, 返回 (items, total)"""
        offset = (page - 1) * per_page

        # 有库存的物料 id
        cursor.execute(f"""
            SELECT DISTINCT m.id
            FROM inventory i
            JOIN material m ON i.material_id = m.id
            {where_sql}
        """, params)
        material_ids_with_stock = {row['id'] for row in cursor.fetchall()}

        # 仅在途 (pending_in) 无库存的物料
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

        # 有库存物料汇总
        cursor.execute(f"""
            SELECT
                m.id as material_id, m.code as material_code, m.name as material_name,
                m.spec, m.unit, m.manufacturer,
                SUM(i.quantity) as quantity,
                MAX(i.updated_at) as updated_at
            FROM inventory i
            JOIN material m ON i.material_id = m.id
            {where_sql}
            GROUP BY m.id, m.code, m.name, m.spec, m.unit, m.manufacturer
        """, params)
        all_items = []
        for row in cursor.fetchall():
            item = dict(row)
            item['status'] = '正常'
            item['pending_in'] = 0
            item['pending_out'] = 0
            all_items.append(item)

        all_items.extend(pending_only_items)
        all_items.sort(key=lambda x: x['material_code'])

        total = len(all_items)
        return all_items[offset:offset + per_page], total

    @staticmethod
    def _enrich_summary_pending(cursor, items, category_code):
        """summary: 原地补 pending_in/pending_out (按 material_id)"""
        if not items:
            return
        material_ids = [item['material_id'] for item in items]
        mid_placeholders = ','.join(['?'] * len(material_ids))

        if category_code:
            cursor.execute(f"""
                SELECT ioi.material_id, SUM(ioi.quantity) as total
                FROM in_order_item ioi
                JOIN in_order io ON ioi.order_id = io.id
                JOIN material m ON ioi.material_id = m.id
                WHERE io.status = 'pending' AND ioi.material_id IN ({mid_placeholders})
                  AND m.category_code LIKE ?
                GROUP BY ioi.material_id
            """, material_ids + [f'{category_code}%'])
        else:
            cursor.execute(f"""
                SELECT ioi.material_id, SUM(ioi.quantity) as total
                FROM in_order_item ioi
                JOIN in_order io ON ioi.order_id = io.id
                WHERE io.status = 'pending' AND ioi.material_id IN ({mid_placeholders})
                GROUP BY ioi.material_id
            """, material_ids)
        for row in cursor.fetchall():
            for item in items:
                if item['material_id'] == row['material_id']:
                    item['pending_in'] = row['total']
                    break

        cursor.execute(f"""
            SELECT ooi.material_id, SUM(ooi.actual_quantity) as total
            FROM out_order_item ooi
            JOIN out_order oo ON ooi.order_id = oo.id
            WHERE oo.status = 'pending' AND ooi.material_id IN ({mid_placeholders})
            GROUP BY ooi.material_id
        """, material_ids)
        for row in cursor.fetchall():
            for item in items:
                if item['material_id'] == row['material_id']:
                    item['pending_out'] = row['total']
                    break

    @staticmethod
    def _get_detail_inventory(cursor, where_sql, params, category_code, status, page, per_page):
        """detail 模式: 按批次明细, stock + pending 合并, 返回 (items, total)"""
        offset = (page - 1) * per_page

        # 有库存的 (material_id, batch_no) 键
        cursor.execute(f"""
            SELECT DISTINCT i.material_id, i.batch_no
            FROM inventory i
            JOIN material m ON i.material_id = m.id
            {where_sql}
        """, params)
        stock_keys = {(row['material_id'], row['batch_no']) for row in cursor.fetchall()}

        # pending_in 批次
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
            else:
                pending_items.append(item)

        # 有库存的 inventory
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
            item['status'] = InventoryService._compute_status(item.get('expiry_date'), status)
            item['pending_in'] = 0
            item['pending_out'] = 0
            inventory.append(item)
            inventory_map[(item['material_id'], item['batch_no'])] = len(inventory) - 1

        # 合并 pending (优先新增, 否则累加 pending_in)
        for item in pending_items:
            key = (item['material_id'], item['batch_no'])
            if key not in stock_keys:
                inventory.append(item)
                inventory_map[key] = len(inventory) - 1
            elif key in inventory_map:
                inventory[inventory_map[key]]['pending_in'] += item['pending_in']

        return inventory[offset:offset + per_page], len(inventory)

    @staticmethod
    def _enrich_detail_pending_out(cursor, items):
        """detail: 原地补 pending_out (按 material_id + batch_no)"""
        if not items:
            return
        material_ids = [item['material_id'] for item in items]
        batch_nos = [item['batch_no'] for item in items if item['batch_no']]
        if not material_ids or not batch_nos:
            return
        placeholders_ids = ','.join(['?'] * len(material_ids))
        placeholders_batches = ','.join(['?'] * len(batch_nos))
        cursor.execute(
            f"SELECT material_id, batch_no, COALESCE(SUM(actual_quantity), 0) as total "
            f"FROM out_order_item ooi "
            f"JOIN out_order oo ON ooi.order_id = oo.id "
            f"WHERE oo.status = 'pending' "
            f"AND ooi.material_id IN ({placeholders_ids}) "
            f"AND ooi.batch_no IN ({placeholders_batches}) "
            f"GROUP BY ooi.material_id, ooi.batch_no",
            material_ids + batch_nos
        )
        pending_out_map = {(row['material_id'], row['batch_no']): row['total'] for row in cursor.fetchall()}
        for item in items:
            key = (item['material_id'], item['batch_no'])
            item['pending_out'] = pending_out_map.get(key, 0)

    @staticmethod
    def _sort_inventory(items, status):
        """按 status 决定 expiry 优先, 否则按 material_code"""
        if status in ('过期', '本月过期', '下月过期'):
            items.sort(key=lambda x: (
                _normalize_date(x.get('expiry_date')),
                x['material_code'],
                x.get('batch_no', ''),
            ))
        else:
            items.sort(key=lambda x: (x['material_code'], x.get('batch_no', '')))

    @staticmethod
    def get_inventory(page=1, per_page=20, keyword=None, summary=False, category_code=None, status=None):
        """Get inventory - summary 按物料汇总, detail 按批次明细"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            where_sql, params = InventoryService._build_inventory_filters(keyword, category_code, status, summary)
            total_quantity = InventoryService.get_inventory_totals(cursor, where_sql, params, summary)

            if summary:
                items, total = InventoryService._get_summary_inventory(
                    cursor, where_sql, params, category_code, page, per_page
                )
                InventoryService._enrich_summary_pending(cursor, items, category_code)
            else:
                items, total = InventoryService._get_detail_inventory(
                    cursor, where_sql, params, category_code, status, page, per_page
                )
                InventoryService._enrich_detail_pending_out(cursor, items)

            InventoryService._sort_inventory(items, status)
            return items, total, total_quantity

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
        """按物料 ID 查库存汇总, 含最早 expiry_date; 无库存返 None"""
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
            batch_no = f"AUTO-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        with get_db_connection() as conn:
            cursor = conn.cursor()
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
            except Exception:
                logger.exception('操作失败')
                conn.rollback()
                raise

    @staticmethod
    def reduce_inventory(material_id, quantity, batch_no=None):
        """Reduce inventory for outbound - deduct from specified batch or oldest batch"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                if batch_no:
                    cursor.execute(
                        """UPDATE inventory
                           SET quantity = ROUND(quantity - ?, 2), updated_at = datetime('now', 'localtime')
                           WHERE material_id = ? AND batch_no = ? AND quantity >= ?""",
                        (quantity, material_id, batch_no, quantity)
                    )
                    if cursor.rowcount == 0:
                        raise ValueError(f"库存不足或批次不存在: 物料ID {material_id}, 批次 {batch_no}")
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
                        raise ValueError(f"库存不足: 物料ID {material_id}")

                    cursor.execute(
                        """UPDATE inventory
                           SET quantity = ROUND(quantity - ?, 2), updated_at = datetime('now', 'localtime')
                           WHERE id = ?""",
                        (quantity, batch['id'])
                    )

                conn.commit()
                return True
            except Exception:
                logger.exception('操作失败')
                conn.rollback()
                raise

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
                        batch_no = f"IMP-{datetime.now().strftime('%Y%m%d%H%M%S')}"

                    if not material_code:
                        errors.append(f"第 {idx + 2} 行: 缺少物料编码")
                        failed += 1
                        continue

                    material_code = str(material_code)

                    cursor.execute("SELECT id FROM material WHERE code = ?", (material_code,))
                    material = cursor.fetchone()
                    if not material:
                        errors.append(f"第 {idx + 2} 行: 物料编码 '{material_code}' 不存在")
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
                    errors.append(f"第 {idx + 2} 行: {str(e)}")
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
                kw = escape_like(keyword)
                where_clauses.append("(m.code LIKE ? ESCAPE '\' OR m.name LIKE ? ESCAPE '\' OR m.spec LIKE ? ESCAPE '\' OR m.manufacturer LIKE ? ESCAPE '\')")
                params.extend([f'%{kw}%', f'%{kw}%', f'%{kw}%', f'%{kw}%'])

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
