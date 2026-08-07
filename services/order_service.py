import logging
from database import get_db_connection
from datetime import datetime
from services.inventory_service import InventoryService
from utils.sql import escape_like, build_update_sql, build_like_clause

logger = logging.getLogger(__name__)

IN_ORDER_UPDATE_FIELDS = ['supplier_id', 'remark', 'receiver', 'purpose', 'receiver_date']
OUT_ORDER_UPDATE_FIELDS = ['department', 'receiver', 'receiver_date', 'remark', 'purpose']
RETURN_ORDER_UPDATE_FIELDS = ['department', 'receiver', 'receiver_date', 'remark', 'related_out_order_id']


def _upsert_inventory(cursor, material_id, batch_no, quantity, add_mode=False):
    """库存 UPSERT: add_mode=True 追加, False 覆盖"""
    cursor.execute(
        "SELECT id, quantity FROM inventory WHERE material_id = ? AND batch_no = ?",
        (material_id, batch_no)
    )
    inv = cursor.fetchone()
    if inv:
        new_qty = round(inv['quantity'] + quantity, 2) if add_mode else round(quantity, 2)
        cursor.execute(
            "UPDATE inventory SET quantity = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (new_qty, inv['id'])
        )
    else:
        cursor.execute(
            """SELECT i.production_date, i.expiry_date
               FROM in_order_item i
               WHERE i.batch_no = ? AND i.material_id = ?
               ORDER BY i.id DESC LIMIT 1""",
            (batch_no, material_id)
        )
        orig = cursor.fetchone()
        cursor.execute(
            """INSERT INTO inventory (material_id, batch_no, quantity, production_date, expiry_date)
               VALUES (?, ?, ?, ?, ?)""",
            (material_id, batch_no, round(quantity, 2),
             orig['production_date'] if orig else None,
             orig['expiry_date'] if orig else None)
        )


class OrderService:
    @staticmethod
    def _generate_order_no(prefix='RK'):
        """Generate order number: PREFIX-YYYYMMDD-序号"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            today = datetime.now().strftime('%Y%m%d')
            table = 'out_order' if prefix == 'CK' else 'in_order'

            cursor.execute(
                f"SELECT order_no FROM {table} WHERE order_no LIKE ? ORDER BY order_no DESC LIMIT 1",
                (f"{prefix}-{today}-%",)
            )
            last_order = cursor.fetchone()

            if last_order:
                try:
                    last_seq = int(last_order['order_no'].split('-')[-1])
                    seq = last_seq + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1

            return f"{prefix}-{today}-{str(seq).zfill(4)}"

    @staticmethod
    def get_in_orders(page=1, per_page=20, status=None, start_date=None, end_date=None):
        """分页查询入库单列表 (按单维度, 不含 items)

        Args:
            page: 页码 (1-based)
            per_page: 每页条数
            status: 单据状态过滤, None 不过滤
            start_date: 收货日期下界 (含)
            end_date: 收货日期上界 (含)

        Returns:
            (orders, total) — orders 为字段字典列表, total 为全量条数
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()

            offset = (page - 1) * per_page

            where_clauses = []
            params = []
            if status:
                where_clauses.append("o.status = ?")
                params.append(status)
            if start_date:
                where_clauses.append("o.receiver_date >= ?")
                params.append(start_date)
            if end_date:
                where_clauses.append("o.receiver_date <= ?")
                params.append(end_date)

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            cursor.execute(f"SELECT COUNT(*) as count FROM in_order o {where_sql}", params)
            total = cursor.fetchone()['count']

            cursor.execute(
                f"""
                SELECT
                    o.id, o.order_no, o.supplier_id, o.operator_id, o.status,
                    o.remark, o.receiver, o.purpose, o.receiver_date,
                    o.created_at, o.approved_at, o.approved_by,
                    s.name as supplier_name,
                    u.username as operator_name
                FROM in_order o
                LEFT JOIN supplier s ON o.supplier_id = s.id
                LEFT JOIN user u ON o.operator_id = u.id
                {where_sql}
                ORDER BY o.created_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [per_page, offset]
            )
            orders = [dict(row) for row in cursor.fetchall()]

            return orders, total

    @staticmethod
    def get_in_order_by_id(order_id):
        """按 ID 查询入库单详情 (含 items 明细)

        Args:
            order_id: 入库单主键

        Returns:
            字段字典 + 'items' 列表, 不存在返回 None
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    o.id, o.order_no, o.supplier_id, o.operator_id, o.status,
                    o.remark, o.receiver, o.purpose, o.receiver_date,
                    o.created_at, o.approved_at, o.approved_by,
                    s.name as supplier_name,
                    u.username as operator_name,
                    a.username as approved_by_name
                FROM in_order o
                LEFT JOIN supplier s ON o.supplier_id = s.id
                LEFT JOIN user u ON o.operator_id = u.id
                LEFT JOIN user a ON o.approved_by = a.id
                WHERE o.id = ?
                """,
                (order_id,)
            )
            order = cursor.fetchone()

            if not order:
                return None

            cursor.execute(
                """
                SELECT
                    i.id, i.order_id, i.material_id, i.batch_no,
                    i.production_date, i.expiry_date, i.quantity, i.unit_price, i.remark,
                    m.code as material_code,
                    m.name as material_name,
                    m.manufacturer,
                    m.spec,
                    m.unit
                FROM in_order_item i
                JOIN material m ON i.material_id = m.id
                WHERE i.order_id = ?
                """,
                (order_id,)
            )
            items = [dict(row) for row in cursor.fetchall()]

            result = dict(order)
            result['items'] = items
            return result

    @staticmethod
    def _validate_materials_active(cursor, items):
        """校验明细物料存在且未禁用 (禁用物料不能出入库)"""
        if not items:
            return
        material_ids = [it['material_id'] for it in items]
        placeholders = ','.join('?' * len(material_ids))
        cursor.execute(
            f"SELECT id, code, name, disabled FROM material WHERE id IN ({placeholders})",
            material_ids
        )
        mats = {row['id']: row for row in cursor.fetchall()}
        for it in items:
            m = mats.get(it['material_id'])
            if not m:
                raise ValueError(f'物料不存在: id={it["material_id"]}')
            if m['disabled']:
                raise ValueError(f'物料 {m["code"]} {m["name"]} 已禁用，不能出入库')

    @staticmethod
    def create_in_order(supplier_id, operator_id, remark=None, receiver=None, purpose=None, receiver_date=None, items=None):
        """创建入库单, 含 items; 返回完整入库单"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            try:
                order_no = OrderService._generate_order_no('RK')

                cursor.execute(
                    """
                    INSERT INTO in_order (order_no, supplier_id, operator_id, remark, receiver, purpose, receiver_date, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (order_no, supplier_id, operator_id, remark, receiver, purpose, receiver_date)
                )
                order_id = cursor.lastrowid

                OrderService._validate_materials_active(cursor, items)

                if items:
                    for item in items:
                        batch_no = item['batch_no'] if item.get('batch_no') else f"AUTO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        production_date = item['production_date'] if 'production_date' in item.keys() else None
                        expiry_date = item['expiry_date'] if 'expiry_date' in item.keys() else None
                        unit_price = item['unit_price'] if 'unit_price' in item.keys() else 0
                        remark = item['remark'] if 'remark' in item.keys() else None
                        cursor.execute(
                            """
                            INSERT INTO in_order_item (order_id, material_id, batch_no, production_date, expiry_date, quantity, unit_price, remark)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (order_id, item['material_id'], batch_no, production_date, expiry_date, item['quantity'], unit_price, remark)
                        )

                conn.commit()
                return OrderService.get_in_order_by_id(order_id)
            except Exception:
                logger.exception('操作失败')
                conn.rollback()
                raise

    @staticmethod
    def update_in_order(order_id, data):
        """更新入库单 (仅 pending); 返回更新后或 None"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("SELECT status FROM in_order WHERE id = ?", (order_id,))
                order = cursor.fetchone()
                if not order or order['status'] != 'pending':
                    return None

                sql, params = build_update_sql('in_order', {**data, 'id': order_id}, IN_ORDER_UPDATE_FIELDS)
                if sql:
                    cursor.execute(sql, params)

                if 'items' in data:
                    OrderService._validate_materials_active(cursor, data['items'])
                    cursor.execute("DELETE FROM in_order_item WHERE order_id = ?", (order_id,))
                    for item in data['items']:
                        batch_no = item['batch_no'] if item.get('batch_no') else f"AUTO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        production_date = item.get('production_date')
                        expiry_date = item.get('expiry_date')
                        unit_price = item.get('unit_price', 0)
                        remark = item.get('remark')
                        cursor.execute(
                            """
                            INSERT INTO in_order_item (order_id, material_id, batch_no, production_date, expiry_date, quantity, unit_price, remark)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (order_id, item['material_id'], batch_no, production_date, expiry_date, item['quantity'], unit_price, remark)
                        )

                conn.commit()
                return OrderService.get_in_order_by_id(order_id)
            except Exception:
                logger.exception('操作失败')
                conn.rollback()
                raise

    @staticmethod
    def delete_in_order(order_id):
        """删除入库单 (仅 pending); 返回 bool"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT status FROM in_order WHERE id = ?", (order_id,))
            order = cursor.fetchone()
            if not order or order['status'] != 'pending':
                return False

            cursor.execute("DELETE FROM in_order_item WHERE order_id = ?", (order_id,))
            cursor.execute("DELETE FROM in_order WHERE id = ?", (order_id,))
            conn.commit()
            return True

    @staticmethod
    def _upsert_inventory_for_in_item(cursor, item, batch_no):
        """per-item 库存 UPSERT: 存在累加, 不存在 INSERT"""
        cursor.execute(
            "SELECT id, quantity FROM inventory WHERE material_id = ? AND batch_no = ?",
            (item['material_id'], batch_no)
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                """UPDATE inventory
                   SET quantity = ROUND(quantity + ?, 2), updated_at = datetime('now', 'localtime')
                   WHERE material_id = ? AND batch_no = ?""",
                (item['quantity'], item['material_id'], batch_no)
            )
        else:
            cursor.execute(
                """INSERT INTO inventory (material_id, batch_no, production_date, expiry_date, quantity, in_order_item_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (item['material_id'], batch_no, item.get('production_date'),
                 item.get('expiry_date'), round(item['quantity'], 2), item['id'])
            )

    @staticmethod
    def approve_in_order(order_id, approved_by):
        """审核入库单 - 同一事务内完成"""
        from datetime import datetime

        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT id, order_no, supplier_id, operator_id, status, remark, receiver, purpose, receiver_date, created_at, approved_at, approved_by FROM in_order WHERE id = ?", (order_id,))
                order = cursor.fetchone()

                if not order or order['status'] != 'pending':
                    return None

                cursor.execute("SELECT id, order_id, material_id, batch_no, production_date, expiry_date, quantity, unit_price, remark FROM in_order_item WHERE order_id = ?", (order_id,))
                items = [dict(row) for row in cursor.fetchall()]

                if not items:
                    return None

                for item in items:
                    batch_no = item['batch_no'] if item['batch_no'] else f"AUTO-{datetime.now().strftime('%Y%m%d%H%M%S')}"

                    if not item['batch_no']:
                        cursor.execute(
                            "UPDATE in_order_item SET batch_no = ? WHERE id = ?",
                            (batch_no, item['id'])
                        )

                    OrderService._upsert_inventory_for_in_item(cursor, item, batch_no)

                cursor.execute(
                    "UPDATE in_order SET status = 'approved', approved_at = datetime('now', 'localtime'), approved_by = ? WHERE id = ?",
                    (approved_by, order_id)
                )

                conn.commit()
                return OrderService.get_in_order_by_id(order_id)

            except Exception:
                logger.exception('操作失败')
                conn.rollback()
                raise

    @staticmethod
    def get_out_orders(page=1, per_page=20, status=None, start_date=None, end_date=None):
        """分页查询出库单列表, 按单维度"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            offset = (page - 1) * per_page

            where_clauses = []
            params = []
            if status:
                where_clauses.append("o.status = ?")
                params.append(status)
            if start_date:
                where_clauses.append("o.receiver_date >= ?")
                params.append(start_date)
            if end_date:
                where_clauses.append("o.receiver_date <= ?")
                params.append(end_date)

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            cursor.execute(f"SELECT COUNT(*) as count FROM out_order o {where_sql}", params)
            total = cursor.fetchone()['count']

            cursor.execute(
                f"""
                SELECT
                    o.id, o.order_no,
                    o.status, o.remark, o.created_at, o.approved_at,
                    o.department, o.receiver, o.receiver_date, o.purpose,
                    u.username as operator_name,
                    a.username as approved_by_name
                FROM out_order o
                LEFT JOIN user u ON o.operator_id = u.id
                LEFT JOIN user a ON o.approved_by = a.id
                {where_sql}
                ORDER BY o.created_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [per_page, offset]
            )
            orders = [dict(row) for row in cursor.fetchall()]

            return orders, total

    @staticmethod
    def get_out_order_by_id(order_id):
        """按 ID 查出库单详情含 items; 不存在返 None"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    o.id, o.order_no,
                    o.status, o.remark, o.created_at, o.approved_at,
                    o.department, o.receiver, o.receiver_date, o.purpose,
                    u.username as operator_name,
                    a.username as approved_by_name
                FROM out_order o
                LEFT JOIN user u ON o.operator_id = u.id
                LEFT JOIN user a ON o.approved_by = a.id
                WHERE o.id = ?
                """,
                (order_id,)
            )
            order = cursor.fetchone()

            if not order:
                return None

            cursor.execute(
                """
                SELECT
                    i.id, i.order_id, i.material_id, i.batch_no, i.unit_price,
                    i.remark, i.requested_quantity, i.actual_quantity,
                    i.initial_gross_weight, i.shipment_info,
                    m.code as material_code,
                    m.name as material_name,
                    m.manufacturer,
                    m.spec,
                    m.unit,
                    m.is_reusable as material_is_reusable
                FROM out_order_item i
                JOIN material m ON i.material_id = m.id
                WHERE i.order_id = ?
                """,
                (order_id,)
            )
            items = [dict(row) for row in cursor.fetchall()]

            result = dict(order)
            result['items'] = items
            return result

    @staticmethod
    def create_out_order(department, receiver, receiver_date, operator_id, remark=None, purpose=None, items=None):
        """创建出库单, 含 items; 返回完整出库单"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            try:
                order_no = OrderService._generate_order_no('CK')

                cursor.execute(
                    """
                    INSERT INTO out_order (order_no, department, receiver, receiver_date, operator_id, remark, purpose, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (order_no, department, receiver, receiver_date, operator_id, remark, purpose)
                )
                order_id = cursor.lastrowid

                OrderService._validate_materials_active(cursor, items)

                if items:
                    for item in items:
                        actual_qty = item.get('actual_quantity', 0) or 0
                        cursor.execute(
                            """
                            INSERT INTO out_order_item (order_id, material_id, batch_no, requested_quantity, actual_quantity, initial_gross_weight, shipment_info)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (order_id, item['material_id'], item.get('batch_no'),
                             item.get('requested_quantity', 0), actual_qty,
                             item.get('initial_gross_weight'), item.get('shipment_info'))
                        )

                conn.commit()
                return OrderService.get_out_order_by_id(order_id)
            except Exception:
                logger.exception('操作失败')
                conn.rollback()
                raise

    @staticmethod
    def update_out_order(order_id, data):
        """更新出库单 (仅 pending); 返回更新后或 None"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("SELECT status FROM out_order WHERE id = ?", (order_id,))
                order = cursor.fetchone()
                if not order or order['status'] != 'pending':
                    return None

                sql, params = build_update_sql('out_order', {**data, 'id': order_id}, OUT_ORDER_UPDATE_FIELDS)
                if sql:
                    cursor.execute(sql, params)

                if 'items' in data:
                    OrderService._validate_materials_active(cursor, data['items'])
                    cursor.execute("DELETE FROM out_order_item WHERE order_id = ?", (order_id,))
                    for item in data['items']:
                        actual_qty = item.get('actual_quantity', 0) or 0
                        cursor.execute(
                            """
                            INSERT INTO out_order_item (order_id, material_id, batch_no, requested_quantity, actual_quantity, initial_gross_weight, shipment_info)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (order_id, item['material_id'], item.get('batch_no'),
                             item.get('requested_quantity', 0), actual_qty,
                             item.get('initial_gross_weight'), item.get('shipment_info'))
                        )

                conn.commit()
                return OrderService.get_out_order_by_id(order_id)
            except Exception:
                logger.exception('操作失败')
                conn.rollback()
                raise

    @staticmethod
    def delete_out_order(order_id):
        """删除出库单 (仅 pending); 返回 bool"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT status FROM out_order WHERE id = ?", (order_id,))
            order = cursor.fetchone()
            if not order or order['status'] != 'pending':
                return False

            # 先删称重记录（引用 out_order_item）
            cursor.execute(
                "DELETE FROM reusable_material_weight WHERE out_order_item_id IN (SELECT id FROM out_order_item WHERE order_id = ?)",
                (order_id,)
            )
            cursor.execute("DELETE FROM out_order_item WHERE order_id = ?", (order_id,))
            cursor.execute("DELETE FROM out_order WHERE id = ?", (order_id,))
            conn.commit()
            return True

    @staticmethod
    def _deduct_inventory_for_out_item(cursor, item):
        """per-item 库存扣减: 有 batch_no 精确扣, 无 batch_no FIFO 选最早过期批次"""
        actual_qty = item['actual_quantity']
        batch_no = item['batch_no']

        if batch_no:
            cursor.execute(
                """UPDATE inventory
                   SET quantity = ROUND(quantity - ?, 2), updated_at = datetime('now', 'localtime')
                   WHERE material_id = ? AND batch_no = ? AND ROUND(quantity, 2) >= ?""",
                (actual_qty, item['material_id'], batch_no, actual_qty)
            )
            if cursor.rowcount == 0:
                raise ValueError(f"库存不足或批次不存在: 物料ID {item['material_id']}, 批次 {batch_no}")
        else:
            cursor.execute(
                """SELECT id, quantity FROM inventory
                   WHERE material_id = ? AND quantity > 0
                   ORDER BY expiry_date ASC, batch_no ASC LIMIT 1""",
                (item['material_id'],)
            )
            batch = cursor.fetchone()
            if not batch or round(batch['quantity'], 2) < actual_qty:
                raise ValueError(f"库存不足: 物料ID {item['material_id']}")
            cursor.execute(
                """UPDATE inventory
                   SET quantity = ROUND(quantity - ?, 2), updated_at = datetime('now', 'localtime')
                   WHERE id = ?""",
                (actual_qty, batch['id'])
            )

    @staticmethod
    def _record_reusable_weight_for_out_item(cursor, item, approved_by, reusable_map):
        """per-item: 写入 reusable_material_weight (仅当 initial_weight > 0 且物料可回用)"""
        initial_weight = item.get('initial_gross_weight')
        if initial_weight is None or initial_weight <= 0:
            return
        if not reusable_map.get(item['material_id'], False):
            return
        cursor.execute(
            """INSERT OR REPLACE INTO reusable_material_weight
               (out_order_item_id, material_id, initial_gross_weight, initial_weight_time, initial_operator_id, status)
               VALUES (?, ?, ?, datetime('now', 'localtime'), ?, 'checked_out')""",
            (item['id'], item['material_id'], initial_weight, approved_by)
        )

    @staticmethod
    def approve_out_order(order_id, approved_by, weight_data=None):
        """weight_data: [{out_order_item_id, initial_gross_weight}, ...]"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            weight_map = {w['out_order_item_id']: w['initial_gross_weight'] for w in (weight_data or [])}

            try:
                cursor.execute("SELECT id, order_no, operator_id, status, remark, purpose, created_at, approved_at, approved_by, department, receiver, receiver_date FROM out_order WHERE id = ?", (order_id,))
                order = cursor.fetchone()

                if not order or order['status'] != 'pending':
                    return None

                cursor.execute(
                    "SELECT id, order_id, material_id, batch_no, unit_price, remark, requested_quantity, actual_quantity, initial_gross_weight, shipment_info FROM out_order_item WHERE order_id = ?",
                    (order_id,)
                )
                items = [dict(row) for row in cursor.fetchall()]

                if not items:
                    return None

                # 批量查询物料是否可回用
                material_ids = list(set(item['material_id'] for item in items))
                placeholders = ','.join('?' * len(material_ids))
                cursor.execute(f"SELECT id, is_reusable FROM material WHERE id IN ({placeholders})", material_ids)
                reusable_map = {row['id']: row['is_reusable'] == 1 for row in cursor.fetchall()}

                for item in items:
                    OrderService._deduct_inventory_for_out_item(cursor, item)

                cursor.execute(
                    """UPDATE out_order
                       SET status = 'approved', approved_at = datetime('now', 'localtime'), approved_by = ?
                       WHERE id = ?""",
                    (approved_by, order_id)
                )

                for item in items:
                    OrderService._record_reusable_weight_for_out_item(
                        cursor, item, approved_by, reusable_map
                    )

                conn.commit()
                return OrderService.get_out_order_by_id(order_id)
            except Exception:
                logger.exception('操作失败')
                conn.rollback()
                raise

    @staticmethod
    def _build_in_order_where(status, start_date, end_date, keyword):
        """构造入库单详表查询的 WHERE 子句: order 级 + material 级"""
        order_clauses = []
        order_params = []
        if status:
            order_clauses.append("o.status = ?")
            order_params.append(status)
        if start_date:
            order_clauses.append("o.receiver_date >= ?")
            order_params.append(start_date)
        if end_date:
            order_clauses.append("o.receiver_date <= ?")
            order_params.append(end_date)

        material_clauses = []
        material_params = []
        if keyword:
            material_clauses.append(build_like_clause(['m.code', 'm.name', 'm.spec', 'm.manufacturer'], keyword, material_params))

        return order_clauses, order_params, material_clauses, material_params

    @staticmethod
    def _combine_in_where(order_clauses, order_params, material_clauses, material_params):
        """合并 order+material 条件为 (where_sql, all_params)"""
        all_clauses = order_clauses + material_clauses
        all_params = order_params + material_params
        where_sql = "WHERE " + " AND ".join(all_clauses) if all_clauses else ""
        return where_sql, all_params

    @staticmethod
    def _count_in_detail_items(cursor, where_sql, all_params):
        """统计入库单明细行数 (分页依据是 item)"""
        cursor.execute(
            f"""SELECT COUNT(i.id) as count
                FROM in_order_item i
                INNER JOIN in_order o ON o.id = i.order_id
                INNER JOIN material m ON i.material_id = m.id
                {where_sql}""",
            all_params
        )
        return cursor.fetchone()['count']

    @staticmethod
    def _query_in_paginated_detail_items(cursor, where_sql, all_params, per_page, page):
        """按 item 分页拉取入库单明细"""
        offset = (page - 1) * per_page
        cursor.execute(
            f"""SELECT i.id as item_id, i.order_id, i.material_id, i.batch_no,
                       i.production_date, i.expiry_date, i.quantity, i.unit_price, i.remark,
                       m.code as material_code, m.name as material_name, m.spec, m.manufacturer, m.unit
                FROM in_order_item i
                INNER JOIN in_order o ON o.id = i.order_id
                INNER JOIN material m ON i.material_id = m.id
                {where_sql}
                ORDER BY o.created_at DESC, i.id
                LIMIT ? OFFSET ?""",
            all_params + [per_page, offset]
        )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _fetch_in_orders_and_items(cursor, paginated_items, material_clauses, material_params):
        """根据 paginated items 拉取所属 orders + 完整 items (含 material 过滤)"""
        order_ids = list(dict.fromkeys(item['order_id'] for item in paginated_items))
        paginated_item_ids = [item['item_id'] for item in paginated_items]
        placeholders_orders = ','.join(['?'] * len(order_ids))
        placeholders_items = ','.join(['?'] * len(paginated_item_ids))

        cursor.execute(
            f"""SELECT o.id as order_id, o.order_no, o.status, o.remark, o.receiver,
                       o.receiver_date, o.created_at, o.approved_at,
                       s.name as supplier_name,
                       u.username as operator_name,
                       a.username as approved_by_name
                FROM in_order o
                LEFT JOIN supplier s ON o.supplier_id = s.id
                LEFT JOIN user u ON o.operator_id = u.id
                LEFT JOIN user a ON o.approved_by = a.id
                WHERE o.id IN ({placeholders_orders})
                ORDER BY o.created_at DESC""",
            order_ids
        )
        orders = [dict(row) for row in cursor.fetchall()]

        has_material_filter = bool(material_clauses)
        material_filter_sql = " AND " + " AND ".join(material_clauses) if has_material_filter else ""
        cursor.execute(
            f"""SELECT i.id, i.order_id, i.material_id, i.batch_no,
                       i.production_date, i.expiry_date, i.quantity, i.unit_price, i.remark,
                       m.code as material_code, m.name as material_name, m.spec, m.manufacturer, m.unit
                FROM in_order_item i
                JOIN material m ON i.material_id = m.id
                WHERE i.order_id IN ({placeholders_orders}) AND i.id IN ({placeholders_items})
                {material_filter_sql}
                ORDER BY i.id""",
            order_ids + paginated_item_ids + (material_params if has_material_filter else [])
        )
        all_items = [dict(row) for row in cursor.fetchall()]
        return orders, all_items

    @staticmethod
    def _attach_items_to_orders(orders, items, key='order_id'):
        """原地: 给每个 order 添加 'items' 字段"""
        items_by_order = {}
        for item in items:
            oid = item[key]
            items_by_order.setdefault(oid, []).append(item)
        for order in orders:
            order['items'] = items_by_order.get(order[key], [])

    @staticmethod
    def get_in_orders_with_details(page=1, per_page=20, status=None, start_date=None, end_date=None, keyword=None):
        """Get in-orders with details - paginated by items"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            order_clauses, order_params, mat_clauses, mat_params = \
                OrderService._build_in_order_where(status, start_date, end_date, keyword)
            where_sql, all_params = OrderService._combine_in_where(
                order_clauses, order_params, mat_clauses, mat_params
            )
            total = OrderService._count_in_detail_items(cursor, where_sql, all_params)
            if total == 0:
                return [], 0
            paginated = OrderService._query_in_paginated_detail_items(
                cursor, where_sql, all_params, per_page, page
            )
            if not paginated:
                return [], 0
            orders, all_items = OrderService._fetch_in_orders_and_items(
                cursor, paginated, mat_clauses, mat_params
            )
            OrderService._attach_items_to_orders(orders, all_items)
            return orders, total

    @staticmethod
    def _build_out_order_where(status, start_date, end_date, receiver):
        """出库单 order 级 WHERE"""
        clauses = []
        params = []
        if status:
            clauses.append("o.status = ?")
            params.append(status)
        if start_date:
            clauses.append("o.receiver_date >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("o.receiver_date <= ?")
            params.append(end_date)
        if receiver:
            clauses.append("o.receiver = ?")
            params.append(receiver)
        return clauses, params

    @staticmethod
    def _build_out_material_where(keyword, has_reusable):
        """出库单 material 级 WHERE"""
        clauses = []
        params = []
        if keyword:
            clauses.append(build_like_clause(['m.code', 'm.name', 'm.spec', 'm.manufacturer'], keyword, params))
        if has_reusable:
            clauses.append("m.is_reusable = 1")
            # 可回用退库需有称重记录, 排除历史普通出库单 (物料后改可回用但无称重)
            clauses.append("EXISTS (SELECT 1 FROM reusable_material_weight rw WHERE rw.out_order_item_id = i.id)")
        return clauses, params

    @staticmethod
    def _query_out_paginated_detail_items(cursor, where_sql, all_params, per_page, page):
        """按 item 分页拉取出库单明细 (per_page=None 时无分页)"""
        if per_page is not None:
            offset = (page - 1) * per_page
            cursor.execute(
                f"""SELECT i.id as item_id, i.order_id, i.material_id, i.batch_no,
                           i.unit_price, i.remark, i.requested_quantity, i.actual_quantity,
                           i.initial_gross_weight, i.shipment_info,
                           m.code as material_code, m.name as material_name, m.spec, m.manufacturer, m.unit
                    FROM out_order_item i
                    INNER JOIN out_order o ON o.id = i.order_id
                    INNER JOIN material m ON i.material_id = m.id
                    {where_sql}
                    ORDER BY o.created_at DESC, i.id
                    LIMIT ? OFFSET ?""",
                all_params + [per_page, offset]
            )
        else:
            cursor.execute(
                f"""SELECT i.id as item_id, i.order_id, i.material_id, i.batch_no,
                           i.unit_price, i.remark, i.requested_quantity, i.actual_quantity,
                           i.initial_gross_weight, i.shipment_info,
                           m.code as material_code, m.name as material_name, m.spec, m.manufacturer, m.unit
                    FROM out_order_item i
                    INNER JOIN out_order o ON o.id = i.order_id
                    INNER JOIN material m ON i.material_id = m.id
                    {where_sql}
                    ORDER BY o.created_at DESC, i.id""",
                all_params
            )
        return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _fetch_out_orders_and_items(cursor, paginated_items, material_clauses, material_params):
        """拉取出库 orders + 补全 items (含 material 过滤)"""
        order_ids = list(dict.fromkeys(item['order_id'] for item in paginated_items))
        paginated_item_ids = [item['item_id'] for item in paginated_items]
        placeholders_orders = ','.join(['?'] * len(order_ids))
        placeholders_items = ','.join(['?'] * len(paginated_item_ids))

        cursor.execute(
            f"""SELECT o.id as order_id, o.order_no, o.department, o.receiver, o.receiver_date,
                       o.status, o.remark, o.purpose, o.created_at, o.approved_at,
                       u.username as operator_name, a.username as approved_by_name
                FROM out_order o
                LEFT JOIN user u ON o.operator_id = u.id
                LEFT JOIN user a ON o.approved_by = a.id
                WHERE o.id IN ({placeholders_orders})
                ORDER BY o.created_at DESC""",
            order_ids
        )
        orders = [dict(row) for row in cursor.fetchall()]

        has_material_filter = bool(material_clauses)
        material_filter_sql = " AND " + " AND ".join(material_clauses) if has_material_filter else ""
        cursor.execute(
            f"""SELECT i.id, i.order_id, i.material_id, i.batch_no, i.unit_price,
                       i.remark, i.requested_quantity, i.actual_quantity,
                       i.initial_gross_weight, i.shipment_info,
                       m.code as material_code, m.name as material_name, m.spec, m.manufacturer, m.unit
                FROM out_order_item i
                JOIN material m ON i.material_id = m.id
                WHERE i.order_id IN ({placeholders_orders}) AND i.id IN ({placeholders_items})
                {material_filter_sql}
                ORDER BY i.id""",
            order_ids + paginated_item_ids + (material_params if has_material_filter else [])
        )
        all_items = [dict(row) for row in cursor.fetchall()]
        return orders, all_items

    @staticmethod
    def _query_out_grand_total(cursor, where_sql, all_params):
        """出库实际数量汇总"""
        cursor.execute(
            f"""SELECT COALESCE(SUM(i.actual_quantity), 0) as grand_total
                FROM out_order_item i
                INNER JOIN out_order o ON o.id = i.order_id
                INNER JOIN material m ON i.material_id = m.id
                {where_sql}""",
            all_params
        )
        return cursor.fetchone()['grand_total']

    @staticmethod
    def get_out_orders_with_details(page=1, per_page=20, status=None, start_date=None, end_date=None, keyword=None, has_reusable=None, receiver=None):
        """Get out-orders with details - paginated by items"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            order_clauses, order_params = OrderService._build_out_order_where(
                status, start_date, end_date, receiver
            )
            mat_clauses, mat_params = OrderService._build_out_material_where(keyword, has_reusable)
            where_sql, all_params = OrderService._combine_in_where(
                order_clauses, order_params, mat_clauses, mat_params
            )

            cursor.execute(
                f"SELECT COUNT(i.id) as count FROM out_order_item i "
                f"INNER JOIN out_order o ON o.id = i.order_id "
                f"INNER JOIN material m ON i.material_id = m.id {where_sql}",
                all_params
            )
            total = cursor.fetchone()['count']
            if total == 0:
                return [], 0, 0

            paginated = OrderService._query_out_paginated_detail_items(
                cursor, where_sql, all_params, per_page, page
            )
            if not paginated:
                return [], 0, 0

            orders, all_items = OrderService._fetch_out_orders_and_items(
                cursor, paginated, mat_clauses, mat_params
            )
            OrderService._attach_items_to_orders(orders, all_items)
            grand_total = OrderService._query_out_grand_total(cursor, where_sql, all_params)
            return orders, total, grand_total

    @staticmethod
    def _generate_return_order_no():
        """Generate return order number: TK-YYYYMMDD-序号"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            today = datetime.now().strftime('%Y%m%d')

            cursor.execute(
                "SELECT order_no FROM return_order WHERE order_no LIKE ? ORDER BY order_no DESC LIMIT 1",
                (f"TK-{today}-%",)
            )
            last_order = cursor.fetchone()

            if last_order:
                try:
                    last_seq = int(last_order['order_no'].split('-')[-1])
                    seq = last_seq + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1

            return f"TK-{today}-{str(seq).zfill(4)}"

    @staticmethod
    def get_return_orders(page=1, per_page=20, status=None, start_date=None, end_date=None, out_order_no=None, keyword=None):
        """分页查询退库单列表, 支持出库单号/keyword 过滤"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            offset = (page - 1) * per_page

            where_clauses = []
            params = []
            if status:
                where_clauses.append("r.status = ?")
                params.append(status)
            if start_date:
                where_clauses.append("r.receiver_date >= ?")
                params.append(start_date)
            if end_date:
                where_clauses.append("r.receiver_date <= ?")
                params.append(end_date)
            if out_order_no:
                where_clauses.append(build_like_clause(['o.order_no'], out_order_no, params, prefix=True))
            if keyword:
                code_clause = build_like_clause(['m.code'], keyword, params, prefix=True)
                other_clause = build_like_clause(['m.name', 'm.manufacturer', 'm.spec'], keyword, params)
                where_clauses.append(f"{code_clause} OR {other_clause}")
            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            count_sql = f"""SELECT COUNT(ri.id) as count FROM return_order r
                LEFT JOIN out_order o ON r.related_out_order_id = o.id
                LEFT JOIN return_order_item ri ON ri.return_order_id = r.id
                LEFT JOIN material m ON ri.material_id = m.id
                {where_sql}"""
            cursor.execute(count_sql, params)
            total = cursor.fetchone()['count']

            if total == 0:
                return [], 0

            cursor.execute(
                f"""
                SELECT
                    ri.id as ri_id, ri.return_order_id, ri.out_order_item_id, ri.material_id,
                    ri.batch_no, ri.remark, ri.return_gross_weight, ri.actual_net_weight, ri.quantity,
                    m.code as material_code, m.name as material_name, m.manufacturer, m.spec, m.unit
                FROM return_order_item ri
                INNER JOIN return_order r ON ri.return_order_id = r.id
                LEFT JOIN out_order o ON r.related_out_order_id = o.id
                LEFT JOIN material m ON ri.material_id = m.id
                {where_sql}
                ORDER BY r.created_at DESC, ri.id
                LIMIT ? OFFSET ?
                """,
                params + [per_page, offset]
            )
            paginated_items = [dict(row) for row in cursor.fetchall()]

            if not paginated_items:
                return [], 0

            order_ids = list(dict.fromkeys(item['return_order_id'] for item in paginated_items))

            placeholders = ','.join(['?'] * len(order_ids))
            cursor.execute(
                f"""
                SELECT
                    r.id as order_id, r.order_no, r.department, r.receiver, r.receiver_date,
                    r.related_out_order_id, r.status, r.remark, r.created_at, r.approved_at,
                    r.operator_id, r.approved_by,
                    o.order_no as out_order_no,
                    u.username as operator_name,
                    a.username as approved_by_name
                FROM return_order r
                LEFT JOIN out_order o ON r.related_out_order_id = o.id
                LEFT JOIN user u ON r.operator_id = u.id
                LEFT JOIN user a ON r.approved_by = a.id
                WHERE r.id IN ({placeholders})
                ORDER BY r.created_at DESC
                """,
                order_ids
            )
            orders = [dict(row) for row in cursor.fetchall()]

            items_by_order = {}
            for item in paginated_items:
                oid = item['return_order_id']
                if oid not in items_by_order:
                    items_by_order[oid] = []
                items_by_order[oid].append(item)

            for order in orders:
                order['items'] = items_by_order.get(order['order_id'], [])

            return orders, total

    @staticmethod
    def get_return_order_by_id(order_id):
        """按 ID 查退库单详情含 items; 不存在返 None"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    r.id, r.order_no, r.related_out_order_id, r.department,
                    r.receiver, r.receiver_date, r.operator_id, r.status,
                    r.remark, r.created_at, r.approved_at, r.approved_by,
                    o.order_no as out_order_no,
                    u.username as operator_name,
                    a.username as approved_by_name
                FROM return_order r
                LEFT JOIN out_order o ON r.related_out_order_id = o.id
                LEFT JOIN user u ON r.operator_id = u.id
                LEFT JOIN user a ON r.approved_by = a.id
                WHERE r.id = ?
                """,
                (order_id,)
            )
            order = cursor.fetchone()

            if not order:
                return None

            cursor.execute(
                """
                SELECT
                    ri.id, ri.return_order_id, ri.out_order_item_id, ri.material_id,
                    ri.batch_no, ri.remark, ri.return_gross_weight, ri.actual_net_weight,
                    ri.quantity,
                    m.code as material_code,
                    m.name as material_name,
                    m.spec,
                    m.unit,
                    m.is_reusable as material_is_reusable,
                    rw.initial_gross_weight
                FROM return_order_item ri
                LEFT JOIN material m ON ri.material_id = m.id
                LEFT JOIN reusable_material_weight rw ON ri.out_order_item_id = rw.out_order_item_id
                WHERE ri.return_order_id = ?
                """,
                (order_id,)
            )
            items = [dict(row) for row in cursor.fetchall()]

            result = dict(order)
            result['items'] = items
            return result

    @staticmethod
    def create_return_order(related_out_order_id, department, receiver, receiver_date, operator_id, remark=None, items=None):
        """创建退库单 (关联出库单), 含 items; 返回完整退库单"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            try:
                if items:
                    # 防重: 同一出库单内相同 (material_id, batch_no) 只能退一次
                    for item in items:
                        cursor.execute(
                            """SELECT COUNT(*) as count FROM return_order_item ri
                               JOIN return_order r ON ri.return_order_id = r.id
                               WHERE r.related_out_order_id = ? AND r.status = 'approved'
                                 AND ri.material_id = ? AND ri.batch_no = ?""",
                            (related_out_order_id, item.get('material_id'), item.get('batch_no'))
                        )
                        if cursor.fetchone()['count'] > 0:
                            raise ValueError("该出库单此物料批次已审核通过退库，不允许重复退库")

                order_no = OrderService._generate_return_order_no()

                cursor.execute(
                    """
                    INSERT INTO return_order (order_no, related_out_order_id, department, receiver, receiver_date, operator_id, remark, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (order_no, related_out_order_id, department, receiver, receiver_date, operator_id, remark)
                )
                order_id = cursor.lastrowid

                if items:
                    for item in items:
                        cursor.execute(
                            "SELECT actual_quantity FROM out_order_item WHERE id = ? AND order_id = ?",
                            (item['out_order_item_id'], related_out_order_id)
                        )
                        out_item = cursor.fetchone()
                        if not out_item:
                            raise ValueError('出库单明细不属于该出库单')

                        qty = item.get('quantity')
                        if qty:
                            if round(float(qty), 2) > round(float(out_item['actual_quantity']), 2):
                                raise ValueError('退回数量不能大于实际用量')

                        cursor.execute(
                            """
                            INSERT INTO return_order_item (return_order_id, out_order_item_id, material_id, batch_no, remark, return_gross_weight, actual_net_weight, quantity)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (order_id, item['out_order_item_id'], item['material_id'],
                             item.get('batch_no'), item.get('remark'), item.get('return_gross_weight'),
                             item.get('actual_net_weight'), item.get('quantity'))
                        )

                conn.commit()
                return OrderService.get_return_order_by_id(order_id)
            except Exception:
                logger.exception('操作失败')
                conn.rollback()
                raise

    @staticmethod
    def update_return_order(order_id, data):
        """更新退库单 (仅 pending); 返回更新后或 None"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("SELECT status FROM return_order WHERE id = ?", (order_id,))
                order = cursor.fetchone()
                if not order or order['status'] != 'pending':
                    return None

                sql, params = build_update_sql('return_order', {**data, 'id': order_id}, RETURN_ORDER_UPDATE_FIELDS)
                if sql:
                    cursor.execute(sql, params)

                if 'items' in data:
                    cursor.execute("DELETE FROM return_order_item WHERE return_order_id = ?", (order_id,))
                    for item in data['items']:
                        qty = item.get('quantity')
                        if qty:
                            cursor.execute(
                                "SELECT actual_quantity FROM out_order_item WHERE id = ?",
                                (item['out_order_item_id'],)
                            )
                            out_item = cursor.fetchone()
                            if out_item and round(float(qty), 2) > round(float(out_item['actual_quantity']), 2):
                                raise ValueError('退回数量不能大于实际用量')
                        cursor.execute(
                            """
                            INSERT INTO return_order_item (return_order_id, out_order_item_id, material_id, batch_no, remark, return_gross_weight, actual_net_weight, quantity)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (order_id, item['out_order_item_id'], item['material_id'],
                             item.get('batch_no'), item.get('remark'), item.get('return_gross_weight'),
                             item.get('actual_net_weight'), item.get('quantity'))
                        )

                conn.commit()
                return OrderService.get_return_order_by_id(order_id)
            except Exception:
                logger.exception('操作失败')
                conn.rollback()
                raise

    @staticmethod
    def delete_return_order(order_id):
        """删除退库单 (仅 pending); 返回 bool"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT status FROM return_order WHERE id = ?", (order_id,))
            order = cursor.fetchone()
            if not order or order['status'] != 'pending':
                return False

            cursor.execute("DELETE FROM return_order_item WHERE return_order_id = ?", (order_id,))
            cursor.execute("DELETE FROM return_order WHERE id = ?", (order_id,))
            conn.commit()
            return True

    @staticmethod
    def _process_return_item(cursor, item, weight_map, approved_by):
        """per-item 退库业务: 可回用走称重, 普通物料直接回加库存"""
        material_id = item['material_id']
        batch_no = item['batch_no']

        cursor.execute("SELECT is_reusable FROM material WHERE id = ?", (material_id,))
        mat = cursor.fetchone()
        is_reusable = mat and mat['is_reusable'] == 1

        if is_reusable:
            # --- 可回用: 现有称重逻辑 ---
            return_weight = weight_map.get(item['out_order_item_id'])
            if return_weight is None:
                return_weight = item.get('return_gross_weight', 0) or 0
            actual_net_weight = item.get('actual_net_weight', 0)

            cursor.execute(
                "SELECT initial_gross_weight FROM reusable_material_weight WHERE out_order_item_id = ?",
                (item['out_order_item_id'],)
            )
            weight_record = cursor.fetchone()
            initial_weight = weight_record['initial_gross_weight'] if weight_record else 0

            if return_weight is not None and return_weight > 0:
                net_weight = round(initial_weight - return_weight, 2)
            else:
                net_weight = round(actual_net_weight, 2) if actual_net_weight > 0 else 0
                return_weight = round(initial_weight - net_weight, 2)

            if net_weight < 0:
                raise ValueError('净用量不能为负数，请检查退库毛重是否大于初始毛重')

            cursor.execute(
                """UPDATE reusable_material_weight
                   SET return_gross_weight = ?, return_weight_time = datetime('now', 'localtime'),
                       return_operator_id = ?, actual_net_weight = ?, status = 'returned'
                   WHERE out_order_item_id = ?""",
                (return_weight, approved_by, net_weight, item['out_order_item_id'])
            )

            cursor.execute("SELECT actual_quantity FROM out_order_item WHERE id = ?", (item['out_order_item_id'],))
            out_item_row = cursor.fetchone()
            original_qty = out_item_row['actual_quantity'] if out_item_row else 0

            returned_qty = round(original_qty - net_weight, 2)
            if returned_qty < 0:
                raise ValueError('剩余库存不能为负数')

            # 退回数量写回明细
            cursor.execute(
                "UPDATE return_order_item SET quantity = ? WHERE id = ?",
                (round(returned_qty, 2), item['id'])
            )

            _upsert_inventory(cursor, material_id, batch_no, returned_qty, add_mode=True)
        else:
            # --- 普通物料: 直接用 quantity 回加库存 ---
            qty = item.get('quantity', 0)
            if not qty or qty <= 0:
                return
            _upsert_inventory(cursor, material_id, batch_no, qty, add_mode=True)

    @staticmethod
    def approve_return_order(order_id, approved_by, weight_data=None):
        """审核退库单：回冲库存,更新原出库单状态"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            weight_map = {w['out_order_item_id']: w['return_gross_weight'] for w in (weight_data or [])}

            try:
                cursor.execute("SELECT id, order_no, related_out_order_id, department, receiver, receiver_date, operator_id, status, remark, created_at, approved_at, approved_by FROM return_order WHERE id = ?", (order_id,))
                order = cursor.fetchone()

                if not order or order['status'] != 'pending':
                    return None

                cursor.execute("SELECT id, return_order_id, out_order_item_id, material_id, batch_no, remark, return_gross_weight, actual_net_weight, quantity FROM return_order_item WHERE return_order_id = ?", (order_id,))
                items = [dict(row) for row in cursor.fetchall()]

                # 防重: 同一出库单内相同 (material_id, batch_no) 只能退一次
                if order['related_out_order_id']:
                    for item in items:
                        cursor.execute(
                            """SELECT COUNT(*) as count FROM return_order_item ri
                               JOIN return_order r ON ri.return_order_id = r.id
                               WHERE r.related_out_order_id = ? AND r.status = 'approved'
                                 AND ri.material_id = ? AND ri.batch_no = ? AND r.id != ?""",
                            (order['related_out_order_id'], item['material_id'], item['batch_no'], order_id)
                        )
                        if cursor.fetchone()[0] > 0:
                            return False

                for item in items:
                    # 退回数量不能大于实际用量
                    if item.get('quantity'):
                        cursor.execute(
                            "SELECT actual_quantity FROM out_order_item WHERE id = ?",
                            (item['out_order_item_id'],)
                        )
                        out_item = cursor.fetchone()
                        if out_item and round(float(item['quantity']), 2) > round(float(out_item['actual_quantity']), 2):
                            raise ValueError('退回数量不能大于实际用量')
                    OrderService._process_return_item(cursor, item, weight_map, approved_by)

                cursor.execute(
                    "UPDATE return_order SET status = 'approved', approved_at = datetime('now', 'localtime'), approved_by = ? WHERE id = ?",
                    (approved_by, order_id)
                )

                conn.commit()
                return OrderService.get_return_order_by_id(order_id)
            except Exception:
                logger.exception('操作失败')
                conn.rollback()
                raise

    @staticmethod
    def get_return_orders_by_out_order(out_order_id):
        """获取指定出库单关联的退库单"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    r.id, r.order_no, r.related_out_order_id, r.department,
                    r.receiver, r.receiver_date, r.operator_id, r.status,
                    r.remark, r.created_at, r.approved_at, r.approved_by,
                    o.order_no as out_order_no,
                    u.username as operator_name,
                    a.username as approved_by_name
                FROM return_order r
                LEFT JOIN out_order o ON r.related_out_order_id = o.id
                LEFT JOIN user u ON r.operator_id = u.id
                LEFT JOIN user a ON r.approved_by = a.id
                WHERE r.related_out_order_id = ?
                ORDER BY r.created_at DESC
                """,
                (out_order_id,)
            )
            orders = [dict(row) for row in cursor.fetchall()]

            if orders:
                order_ids = [o['id'] for o in orders]
                placeholders = ','.join(['?'] * len(order_ids))
                cursor.execute(
                    f"""
                    SELECT
                        ri.id, ri.return_order_id, ri.out_order_item_id, ri.material_id,
                        ri.batch_no, ri.remark, ri.return_gross_weight, ri.actual_net_weight, ri.quantity,
                        m.code as material_code, m.name as material_name, m.spec, m.unit,
                        m.is_reusable as material_is_reusable,
                        rw.initial_gross_weight
                    FROM return_order_item ri
                    LEFT JOIN material m ON ri.material_id = m.id
                    LEFT JOIN reusable_material_weight rw ON ri.out_order_item_id = rw.out_order_item_id
                    WHERE ri.return_order_id IN ({placeholders})
                    ORDER BY ri.id
                    """,
                    order_ids
                )
                items_by_order = {}
                for row in cursor.fetchall():
                    d = dict(row)
                    items_by_order.setdefault(d['return_order_id'], []).append(d)
                for o in orders:
                    o['items'] = items_by_order.get(o['id'], [])

            return orders, len(orders)

    @staticmethod
    def is_material_reusable(material_id):
        """检查物料是否为可回用物料"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_reusable FROM material WHERE id = ?", (material_id,))
            row = cursor.fetchone()
            return row and row['is_reusable'] == 1

    @staticmethod
    def create_weight_record(out_order_item_id, material_id, initial_gross_weight, operator_id):
        """创建称重记录(出库审核时)"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO reusable_material_weight
                    (out_order_item_id, material_id, initial_gross_weight, initial_weight_time, initial_operator_id, status)
                    VALUES (?, ?, ?, datetime('now', 'localtime'), ?, 'checked_out')
                    """,
                    (out_order_item_id, material_id, initial_gross_weight, operator_id)
                )
                conn.commit()
                return OrderService.get_weight_record_by_out_order_item(out_order_item_id)
            except Exception:
                logger.exception('操作失败')
                conn.rollback()
                raise

    @staticmethod
    def update_weight_record_return(out_order_item_id, return_gross_weight, operator_id):
        """更新称重记录(退库审核时): 计算净用量"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT id, out_order_item_id, material_id, initial_gross_weight, initial_weight_time, initial_operator_id, return_gross_weight, return_weight_time, return_operator_id, actual_net_weight, status, remark FROM reusable_material_weight WHERE out_order_item_id = ?",
                    (out_order_item_id,)
                )
                record = cursor.fetchone()
                if not record:
                    return None

                initial_weight = record['initial_gross_weight'] or 0
                net_weight = round(initial_weight - return_gross_weight, 2)

                cursor.execute(
                    """
                    UPDATE reusable_material_weight
                    SET return_gross_weight = ?,
                        return_weight_time = datetime('now', 'localtime'),
                        return_operator_id = ?,
                        actual_net_weight = ?,
                        status = 'returned'
                    WHERE out_order_item_id = ?
                    """,
                    (return_gross_weight, operator_id, net_weight, out_order_item_id)
                )

                conn.commit()
                return OrderService.get_weight_record_by_out_order_item(out_order_item_id)
            except Exception:
                logger.exception('操作失败')
                conn.rollback()
                raise

    @staticmethod
    def get_weight_record_by_out_order_item(out_order_item_id):
        """获取指定出库明细的称重记录"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    w.id, w.out_order_item_id, w.material_id,
                    w.initial_gross_weight, w.initial_weight_time, w.initial_operator_id,
                    w.return_gross_weight, w.return_weight_time, w.return_operator_id,
                    w.actual_net_weight, w.status, w.remark,
                    m.code as material_code,
                    m.name as material_name,
                    m.spec,
                    m.unit
                FROM reusable_material_weight w
                JOIN material m ON w.material_id = m.id
                WHERE w.out_order_item_id = ?
                """,
                (out_order_item_id,)
            )
            record = cursor.fetchone()
            return dict(record) if record else None

    @staticmethod
    def get_all_weight_records(page=1, per_page=20, status=None, keyword=None):
        """获取所有称重记录,支持分页和筛选"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            where_clauses = []
            params = []
            if status:
                where_clauses.append("w.status = ?")
                params.append(status)
            if keyword:
                code_clause = build_like_clause(['m.code'], keyword, params, prefix=True)
                other_clause = build_like_clause(['m.name', 'm.manufacturer', 'm.spec'], keyword, params)
                where_clauses.append(f"{code_clause} OR {other_clause}")
            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            cursor.execute(
                f"SELECT COUNT(*) as count FROM reusable_material_weight w JOIN material m ON w.material_id = m.id {where_sql}",
                params
            )
            total = cursor.fetchone()['count']

            offset = (page - 1) * per_page
            cursor.execute(
                f"""
                SELECT
                    w.id, w.out_order_item_id, w.material_id,
                    w.initial_gross_weight, w.initial_weight_time, w.initial_operator_id,
                    w.return_gross_weight, w.return_weight_time, w.return_operator_id,
                    w.actual_net_weight, w.status, w.remark,
                    m.code as material_code,
                    m.name as material_name,
                    m.spec,
                    m.manufacturer,
                    m.unit,
                    oi.batch_no,
                    oi.order_id,
                    o.order_no as out_order_no,
                    o.receiver as initial_operator_name,
                    (SELECT r.receiver FROM return_order_item roi
                     JOIN return_order r ON r.id = roi.return_order_id AND r.status = 'approved'
                     WHERE roi.out_order_item_id = w.out_order_item_id
                     LIMIT 1) as return_operator_name
                FROM reusable_material_weight w
                JOIN material m ON w.material_id = m.id
                JOIN out_order_item oi ON w.out_order_item_id = oi.id
                JOIN out_order o ON oi.order_id = o.id
                {where_sql}
                ORDER BY w.id DESC
                LIMIT ? OFFSET ?
                """,
                params + [per_page, offset]
            )
            records = [dict(row) for row in cursor.fetchall()]

            return records, total

    @staticmethod
    def get_weight_records_by_out_order(order_id):
        """获取出库单所有明细的称重记录"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    w.id, w.out_order_item_id, w.material_id,
                    w.initial_gross_weight, w.initial_weight_time, w.initial_operator_id,
                    w.return_gross_weight, w.return_weight_time, w.return_operator_id,
                    w.actual_net_weight, w.status, w.remark,
                    m.code as material_code,
                    m.name as material_name,
                    m.spec,
                    m.unit
                FROM reusable_material_weight w
                JOIN material m ON w.material_id = m.id
                JOIN out_order_item oi ON w.out_order_item_id = oi.id
                WHERE oi.order_id = ?
                """,
                (order_id,)
            )
            records = [dict(row) for row in cursor.fetchall()]
            return records
