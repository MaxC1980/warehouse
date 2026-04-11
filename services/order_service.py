from database import get_db_connection
from datetime import datetime
from services.inventory_service import InventoryService

class OrderService:
    @staticmethod
    def _generate_order_no(prefix='RK'):
        """Generate order number: PREFIX-YYYYMMDD-序号"""
        conn = get_db_connection()
        cursor = conn.cursor()

        today = datetime.now().strftime('%Y%m%d')

        # Determine which table to query based on prefix
        table = 'out_order' if prefix == 'CK' else 'in_order'

        cursor.execute(
            f"SELECT order_no FROM {table} WHERE order_no LIKE ? ORDER BY order_no DESC LIMIT 1",
            (f"{prefix}-{today}-%",)
        )
        last_order = cursor.fetchone()

        if last_order:
            last_seq = int(last_order['order_no'].split('-')[-1])
            seq = last_seq + 1
        else:
            seq = 1

        order_no = f"{prefix}-{today}-{str(seq).zfill(4)}"
        conn.close()
        return order_no

    @staticmethod
    def get_in_orders(page=1, per_page=20, status=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * per_page

        where_sql = ""
        params = []
        if status:
            where_sql = "WHERE o.status = ?"
            params.append(status)

        # Get total count
        cursor.execute(f"SELECT COUNT(*) as count FROM in_order o {where_sql}", params)
        total = cursor.fetchone()['count']

        # Get orders with supplier and operator info
        cursor.execute(
            f"""
            SELECT
                o.*,
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
        conn.close()

        return orders, total

    @staticmethod
    def get_in_order_by_id(order_id):
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                o.*,
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
            conn.close()
            return None

        # Get items
        cursor.execute(
            """
            SELECT
                i.*,
                m.code as material_code,
                m.name as material_name,
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
        conn.close()
        return result

    @staticmethod
    def create_in_order(supplier_id, operator_id, remark=None, receiver=None, purpose=None, receiver_date=None, items=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Generate order number
            order_no = OrderService._generate_order_no('RK')

            # Create main order
            cursor.execute(
                """
                INSERT INTO in_order (order_no, supplier_id, operator_id, remark, receiver, purpose, receiver_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (order_no, supplier_id, operator_id, remark, receiver, purpose, receiver_date)
            )
            order_id = cursor.lastrowid

            # Create items
            if items:
                for item in items:
                    # Auto-generate batch_no if empty
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
            conn.close()
            return OrderService.get_in_order_by_id(order_id)
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    @staticmethod
    def update_in_order(order_id, supplier_id=None, remark=None, receiver=None, purpose=None, receiver_date=None, items=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Check order status
            cursor.execute("SELECT status FROM in_order WHERE id = ?", (order_id,))
            order = cursor.fetchone()
            if not order or order['status'] != 'pending':
                conn.close()
                return None

            # Update main order
            updates = []
            params = []
            if supplier_id is not None:
                updates.append("supplier_id = ?")
                params.append(supplier_id)
            if remark is not None:
                updates.append("remark = ?")
                params.append(remark)
            if receiver is not None:
                updates.append("receiver = ?")
                params.append(receiver)
            if purpose is not None:
                updates.append("purpose = ?")
                params.append(purpose)
            if receiver_date is not None:
                updates.append("receiver_date = ?")
                params.append(receiver_date)

            if updates:
                params.append(order_id)
                cursor.execute(
                    f"UPDATE in_order SET {', '.join(updates)} WHERE id = ?",
                    params
                )

            # Update items - delete old and insert new
            if items is not None:
                cursor.execute("DELETE FROM in_order_item WHERE order_id = ?", (order_id,))
                for item in items:
                    # Auto-generate batch_no if empty
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
            conn.close()
            return OrderService.get_in_order_by_id(order_id)
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    @staticmethod
    def delete_in_order(order_id):
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT status FROM in_order WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        if not order or order['status'] != 'pending':
            conn.close()
            return False

        cursor.execute("DELETE FROM in_order_item WHERE order_id = ?", (order_id,))
        cursor.execute("DELETE FROM in_order WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def approve_in_order(order_id, approved_by):
        """审核入库单 - 同一事务内完成"""
        from datetime import datetime

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        try:
            # 1. 获取订单并验证状态
            cursor.execute("SELECT * FROM in_order WHERE id = ?", (order_id,))
            order = cursor.fetchone()

            if not order or order['status'] != 'pending':
                conn.close()
                return None

            # 2. 获取订单明细
            cursor.execute("SELECT * FROM in_order_item WHERE order_id = ?", (order_id,))
            items = [dict(row) for row in cursor.fetchall()]

            if not items:
                conn.close()
                return None

            # 3. 处理每个明细项（在同一事务内）
            for item in items:
                batch_no = item['batch_no'] if item['batch_no'] else f"AUTO-{datetime.now().strftime('%Y%m%d%H%M%S')}"

                # 如果批次号是自动生成的，更新回 in_order_item
                if not item['batch_no']:
                    cursor.execute(
                        "UPDATE in_order_item SET batch_no = ? WHERE id = ?",
                        (batch_no, item['id'])
                    )

                # 更新或插入库存（在同一事务内）
                cursor.execute(
                    "SELECT id, quantity FROM inventory WHERE material_id = ? AND batch_no = ?",
                    (item['material_id'], batch_no)
                )
                existing = cursor.fetchone()

                if existing:
                    cursor.execute(
                        """UPDATE inventory
                           SET quantity = quantity + ?, updated_at = datetime('now', 'localtime')
                           WHERE material_id = ? AND batch_no = ?""",
                        (item['quantity'], item['material_id'], batch_no)
                    )
                else:
                    cursor.execute(
                        """INSERT INTO inventory (material_id, batch_no, production_date, expiry_date, quantity, in_order_item_id)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (item['material_id'], batch_no, item.get('production_date'),
                         item.get('expiry_date'), item['quantity'], item['id'])
                    )

            # 4. 更新订单状态
            cursor.execute(
                "UPDATE in_order SET status = 'approved', approved_at = datetime('now', 'localtime'), approved_by = ? WHERE id = ?",
                (approved_by, order_id)
            )

            conn.commit()
            conn.close()
            return OrderService.get_in_order_by_id(order_id)

        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    # Out Order methods
    @staticmethod
    def get_out_orders(page=1, per_page=20, status=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * per_page

        where_sql = ""
        params = []
        if status:
            where_sql = "WHERE o.status = ?"
            params.append(status)

        # Get total count
        cursor.execute(f"SELECT COUNT(*) as count FROM out_order o {where_sql}", params)
        total = cursor.fetchone()['count']

        # Get orders with operator info
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
        conn.close()

        return orders, total

    @staticmethod
    def get_out_order_by_id(order_id):
        conn = get_db_connection()
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
            conn.close()
            return None

        # Get items
        cursor.execute(
            """
            SELECT
                i.*,
                m.code as material_code,
                m.name as material_name,
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
        conn.close()
        return result

    @staticmethod
    def create_out_order(department, receiver, receiver_date, operator_id, remark=None, purpose=None, items=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Generate order number
            order_no = OrderService._generate_order_no('CK')

            # Create main order
            cursor.execute(
                """
                INSERT INTO out_order (order_no, department, receiver, receiver_date, operator_id, remark, purpose, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (order_no, department, receiver, receiver_date, operator_id, remark, purpose)
            )
            order_id = cursor.lastrowid

            # Create items
            if items:
                for item in items:
                    actual_qty = item.get('actual_quantity', 0) or 0
                    cursor.execute(
                        """
                        INSERT INTO out_order_item (order_id, material_id, batch_no, quantity, requested_quantity, actual_quantity, initial_gross_weight, shipment_info)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (order_id, item['material_id'], item.get('batch_no'),
                         actual_qty, item.get('requested_quantity', 0), actual_qty,
                         item.get('initial_gross_weight'), item.get('shipment_info'))
                    )

            conn.commit()
            conn.close()
            return OrderService.get_out_order_by_id(order_id)
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    @staticmethod
    def update_out_order(order_id, department=None, receiver=None, receiver_date=None, remark=None, purpose=None, items=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Check order status
            cursor.execute("SELECT status FROM out_order WHERE id = ?", (order_id,))
            order = cursor.fetchone()
            if not order or order['status'] != 'pending':
                conn.close()
                return None

            # Update main order
            updates = []
            params = []
            if department is not None:
                updates.append("department = ?")
                params.append(department)
            if receiver is not None:
                updates.append("receiver = ?")
                params.append(receiver)
            if receiver_date is not None:
                updates.append("receiver_date = ?")
                params.append(receiver_date)
            if remark is not None:
                updates.append("remark = ?")
                params.append(remark)
            if purpose is not None:
                updates.append("purpose = ?")
                params.append(purpose)

            if updates:
                params.append(order_id)
                cursor.execute(
                    f"UPDATE out_order SET {', '.join(updates)} WHERE id = ?",
                    params
                )

            # Update items - delete old and insert new
            if items is not None:
                cursor.execute("DELETE FROM out_order_item WHERE order_id = ?", (order_id,))
                for item in items:
                    actual_qty = item.get('actual_quantity', 0) or 0
                    cursor.execute(
                        """
                        INSERT INTO out_order_item (order_id, material_id, batch_no, quantity, requested_quantity, actual_quantity, initial_gross_weight, shipment_info)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (order_id, item['material_id'], item.get('batch_no'),
                         actual_qty, item.get('requested_quantity', 0), actual_qty,
                         item.get('initial_gross_weight'), item.get('shipment_info'))
                    )

            conn.commit()
            conn.close()
            return OrderService.get_out_order_by_id(order_id)
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    @staticmethod
    def delete_out_order(order_id):
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT status FROM out_order WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        if not order or order['status'] != 'pending':
            conn.close()
            return False

        cursor.execute("DELETE FROM out_order_item WHERE order_id = ?", (order_id,))
        cursor.execute("DELETE FROM out_order WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def approve_out_order(order_id, approved_by, weight_data=None):
        """weight_data: [{out_order_item_id, initial_gross_weight}, ...]"""
        conn = get_db_connection()
        cursor = conn.cursor()
        weight_map = {w['out_order_item_id']: w['initial_gross_weight'] for w in (weight_data or [])}

        try:
            cursor.execute("PRAGMA foreign_keys = ON")

            # Get order
            cursor.execute("SELECT * FROM out_order WHERE id = ?", (order_id,))
            order = cursor.fetchone()

            if not order or order['status'] != 'pending':
                conn.close()
                return None

            # Get items
            cursor.execute(
                "SELECT * FROM out_order_item WHERE order_id = ?",
                (order_id,)
            )
            items = cursor.fetchall()

            # Check and reduce inventory for each item (inline, same transaction)
            # For reusable materials, inventory is deducted at return time based on net weight
            for item in items:
                # Check if material is reusable
                cursor.execute("SELECT is_reusable FROM material WHERE id = ?", (item['material_id'],))
                mat = cursor.fetchone()
                is_reusable = mat and mat['is_reusable'] == 1

                if is_reusable:
                    # For reusable materials: skip inventory deduction at approval
                    # Weight record will be created below for tracking
                    continue

                # For regular materials: deduct inventory based on actual_quantity
                actual_qty = item['actual_quantity'] if item['actual_quantity'] else item['quantity']
                batch_no = item['batch_no']

                if batch_no:
                    # Deduct from specific batch
                    cursor.execute(
                        """UPDATE inventory
                           SET quantity = quantity - ?, updated_at = datetime('now', 'localtime')
                           WHERE material_id = ? AND batch_no = ? AND quantity >= ?""",
                        (actual_qty, item['material_id'], batch_no, actual_qty)
                    )
                    if cursor.rowcount == 0:
                        raise Exception(f"库存不足或批次不存在: 物料ID {item['material_id']}, 批次 {batch_no}")
                else:
                    # Deduct from oldest batch
                    cursor.execute(
                        """SELECT id, quantity FROM inventory
                           WHERE material_id = ? AND quantity > 0
                           ORDER BY expiry_date ASC, batch_no ASC LIMIT 1""",
                        (item['material_id'],)
                    )
                    batch = cursor.fetchone()
                    if not batch or batch['quantity'] < actual_qty:
                        raise Exception(f"库存不足: 物料ID {item['material_id']}")
                    cursor.execute(
                        """UPDATE inventory
                           SET quantity = quantity - ?, updated_at = datetime('now', 'localtime')
                           WHERE id = ?""",
                        (actual_qty, batch['id'])
                    )

            # Update order status
            cursor.execute(
                """UPDATE out_order
                   SET status = 'approved', approved_at = datetime('now', 'localtime'), approved_by = ?
                   WHERE id = ?""",
                (approved_by, order_id)
            )

            # Create weight records for reusable materials
            for item in items:
                initial_weight = item['initial_gross_weight'] if 'initial_gross_weight' in item.keys() else None
                if initial_weight is not None and initial_weight > 0:
                    # Check if material is reusable
                    cursor.execute("SELECT is_reusable FROM material WHERE id = ?", (item['material_id'],))
                    mat = cursor.fetchone()
                    if mat and mat['is_reusable'] == 1:
                        cursor.execute(
                            """INSERT OR REPLACE INTO reusable_material_weight
                               (out_order_item_id, material_id, initial_gross_weight, initial_weight_time, initial_operator_id, status)
                               VALUES (?, ?, ?, datetime('now', 'localtime'), ?, 'checked_out')""",
                            (item['id'], item['material_id'], initial_weight, approved_by)
                        )

            conn.commit()
            conn.close()
            return OrderService.get_out_order_by_id(order_id)
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    @staticmethod
    def get_in_orders_with_details(page=1, per_page=20, status=None, start_date=None, end_date=None, material_code=None, material_name=None, material_spec=None):
        """Get in-orders with details (LEFT JOIN in_order + in_order_item + material)"""
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * per_page

        # Build order-level where clauses
        order_where_clauses = []
        order_params = []
        if status:
            order_where_clauses.append("o.status = ?")
            order_params.append(status)
        if start_date:
            order_where_clauses.append("o.receiver_date >= ?")
            order_params.append(start_date)
        if end_date:
            order_where_clauses.append("o.receiver_date <= ?")
            order_params.append(end_date)

        # Build material filter conditions
        material_conditions = []
        material_params = []
        if material_code:
            material_conditions.append("m.code LIKE ?")
            material_params.append(f"{material_code}%")
        if material_name:
            material_conditions.append("m.name LIKE ?")
            material_params.append(f"%{material_name}%")
        if material_spec:
            material_conditions.append("m.spec LIKE ?")
            material_params.append(f"%{material_spec}%")

        has_material_filter = bool(material_conditions)

        if has_material_filter:
            # Combine all WHERE conditions
            all_conditions = order_where_clauses + material_conditions
            all_params = order_params + material_params
            where_sql = "WHERE " + " AND ".join(all_conditions) if all_conditions else ""

            item_join = """
            INNER JOIN in_order_item i ON o.id = i.order_id
            INNER JOIN material m ON i.material_id = m.id
            """

            # Count total item rows (matching material filter)
            count_query = f"""
                SELECT COUNT(i.id) as count
                FROM in_order_item i
                INNER JOIN in_order o ON o.id = i.order_id
                INNER JOIN material m ON i.material_id = m.id
                {where_sql}
            """
            cursor.execute(count_query, all_params)
            total = cursor.fetchone()['count']

            # Get paginated order IDs
            paginated_query = f"""
                SELECT DISTINCT o.id as order_id
                FROM in_order o
                {item_join}
                {where_sql}
                ORDER BY o.created_at DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(paginated_query, all_params + [per_page, offset])
            order_ids = [row['order_id'] for row in cursor.fetchall()]

            if not order_ids:
                conn.close()
                return [], 0

            # Get order details
            placeholders = ','.join(['?'] * len(order_ids))
            orders_query = f"""
                SELECT
                    o.id as order_id,
                    o.order_no,
                    o.status,
                    o.remark,
                    o.receiver,
                    o.receiver_date,
                    o.created_at,
                    o.approved_at,
                    s.name as supplier_name,
                    u.username as operator_name,
                    a.username as approved_by_name
                FROM in_order o
                LEFT JOIN supplier s ON o.supplier_id = s.id
                LEFT JOIN user u ON o.operator_id = u.id
                LEFT JOIN user a ON o.approved_by = a.id
                WHERE o.id IN ({placeholders})
                ORDER BY o.created_at DESC
            """
            cursor.execute(orders_query, order_ids)
            orders = [dict(row) for row in cursor.fetchall()]

            # Get items for each order (with material filter applied)
            for order in orders:
                item_query = f"""
                    SELECT
                        i.*,
                        m.code as material_code,
                        m.name as material_name,
                        m.spec,
                        m.unit
                    FROM in_order_item i
                    JOIN material m ON i.material_id = m.id
                    WHERE i.order_id = ? AND {" AND ".join(material_conditions)}
                """
                cursor.execute(item_query, [order['order_id']] + material_params)
                order['items'] = [dict(row) for row in cursor.fetchall()]
        else:
            # No material filter - use original efficient query
            order_where_sql = ("WHERE " + " AND ".join(order_where_clauses)) if order_where_clauses else ""

            cursor.execute(f"SELECT COUNT(i.id) as count FROM in_order_item i JOIN in_order o ON o.id = i.order_id {order_where_sql}", order_params)
            total = cursor.fetchone()['count']

            cursor.execute(
                f"""
                SELECT
                    o.id as order_id,
                    o.order_no,
                    o.status,
                    o.remark,
                    o.receiver,
                    o.receiver_date,
                    o.created_at,
                    o.approved_at,
                    s.name as supplier_name,
                    u.username as operator_name,
                    a.username as approved_by_name
                FROM in_order o
                LEFT JOIN supplier s ON o.supplier_id = s.id
                LEFT JOIN user u ON o.operator_id = u.id
                LEFT JOIN user a ON o.approved_by = a.id
                {order_where_sql}
                GROUP BY o.id
                ORDER BY o.created_at DESC
                LIMIT ? OFFSET ?
                """,
                order_params + [per_page, offset]
            )
            orders = [dict(row) for row in cursor.fetchall()]

            for order in orders:
                cursor.execute(
                    """
                    SELECT
                        i.*,
                        m.code as material_code,
                        m.name as material_name,
                        m.spec,
                        m.unit
                    FROM in_order_item i
                    JOIN material m ON i.material_id = m.id
                    WHERE i.order_id = ?
                    """,
                    [order['order_id']]
                )
                order['items'] = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return orders, total

    @staticmethod
    def get_out_orders_with_details(page=1, per_page=20, status=None, start_date=None, end_date=None, material_code=None, material_name=None, material_spec=None, has_reusable=None):
        """Get out-orders with details"""
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * per_page

        # Build order-level where clauses
        order_where_clauses = []
        order_params = []
        if status:
            order_where_clauses.append("o.status = ?")
            order_params.append(status)
        if start_date:
            order_where_clauses.append("o.receiver_date >= ?")
            order_params.append(start_date)
        if end_date:
            order_where_clauses.append("o.receiver_date <= ?")
            order_params.append(end_date)

        # Build material filter conditions
        material_conditions = []
        material_params = []
        if material_code:
            material_conditions.append("m.code LIKE ?")
            material_params.append(f"{material_code}%")
        if material_name:
            material_conditions.append("m.name LIKE ?")
            material_params.append(f"%{material_name}%")
        if material_spec:
            material_conditions.append("m.spec LIKE ?")
            material_params.append(f"%{material_spec}%")
        if has_reusable:
            material_conditions.append("m.is_reusable = 1")

        has_material_filter = bool(material_conditions)

        if has_material_filter:
            # Combine all WHERE conditions
            all_conditions = order_where_clauses + material_conditions
            all_params = order_params + material_params
            where_sql = "WHERE " + " AND ".join(all_conditions) if all_conditions else ""

            item_join = """
            INNER JOIN out_order_item i ON o.id = i.order_id
            INNER JOIN material m ON i.material_id = m.id
            """

            # Count total item rows
            cursor.execute(f"SELECT COUNT(i.id) as count FROM out_order_item i INNER JOIN out_order o ON o.id = i.order_id INNER JOIN material m ON i.material_id = m.id {where_sql}", all_params)
            total = cursor.fetchone()['count']

            # Get paginated order IDs
            cursor.execute(
                f"SELECT DISTINCT o.id as order_id FROM out_order o {item_join} {where_sql} ORDER BY o.created_at DESC LIMIT ? OFFSET ?",
                all_params + [per_page, offset]
            )
            order_ids = [row['order_id'] for row in cursor.fetchall()]

            if not order_ids:
                conn.close()
                return [], 0

            placeholders = ','.join(['?'] * len(order_ids))
            cursor.execute(
                f"""
                SELECT
                    o.id as order_id, o.order_no, o.department, o.receiver, o.receiver_date,
                    o.status, o.remark, o.created_at, o.approved_at,
                    u.username as operator_name, a.username as approved_by_name
                FROM out_order o
                LEFT JOIN user u ON o.operator_id = u.id
                LEFT JOIN user a ON o.approved_by = a.id
                WHERE o.id IN ({placeholders})
                ORDER BY o.created_at DESC
                """,
                order_ids
            )
            orders = [dict(row) for row in cursor.fetchall()]

            for order in orders:
                cursor.execute(
                    f"""
                    SELECT
                        i.*,
                        m.code as material_code, m.name as material_name, m.spec, m.unit
                    FROM out_order_item i
                    JOIN material m ON i.material_id = m.id
                    WHERE i.order_id = ? AND {" AND ".join(material_conditions)}
                    """,
                    [order['order_id']] + material_params
                )
                order['items'] = [dict(row) for row in cursor.fetchall()]
        else:
            order_where_sql = ("WHERE " + " AND ".join(order_where_clauses)) if order_where_clauses else ""

            cursor.execute(f"SELECT COUNT(i.id) as count FROM out_order_item i JOIN out_order o ON o.id = i.order_id {order_where_sql}", order_params)
            total = cursor.fetchone()['count']

            cursor.execute(
                f"""
                SELECT
                    o.id as order_id, o.order_no, o.department, o.receiver, o.receiver_date,
                    o.status, o.remark, o.created_at, o.approved_at,
                    u.username as operator_name, a.username as approved_by_name
                FROM out_order o
                LEFT JOIN user u ON o.operator_id = u.id
                LEFT JOIN user a ON o.approved_by = a.id
                {order_where_sql}
                GROUP BY o.id
                ORDER BY o.created_at DESC
                LIMIT ? OFFSET ?
                """,
                order_params + [per_page, offset]
            )
            orders = [dict(row) for row in cursor.fetchall()]

            for order in orders:
                cursor.execute(
                    """
                    SELECT
                        i.*,
                        m.code as material_code, m.name as material_name, m.spec, m.unit
                    FROM out_order_item i
                    JOIN material m ON i.material_id = m.id
                    WHERE i.order_id = ?
                    """,
                    [order['order_id']]
                )
                order['items'] = [dict(row) for row in cursor.fetchall()]

        if has_material_filter:
            orders = [o for o in orders if o['items']]

        conn.close()
        return orders, total

    # Return Order methods
    @staticmethod
    def _generate_return_order_no():
        """Generate return order number: TK-YYYYMMDD-序号"""
        conn = get_db_connection()
        cursor = conn.cursor()

        today = datetime.now().strftime('%Y%m%d')

        cursor.execute(
            "SELECT order_no FROM return_order WHERE order_no LIKE ? ORDER BY order_no DESC LIMIT 1",
            (f"TK-{today}-%",)
        )
        last_order = cursor.fetchone()

        if last_order:
            last_seq = int(last_order['order_no'].split('-')[-1])
            seq = last_seq + 1
        else:
            seq = 1

        order_no = f"TK-{today}-{str(seq).zfill(4)}"
        conn.close()
        return order_no

    @staticmethod
    def get_return_orders(page=1, per_page=20, status=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * per_page

        where_sql = ""
        params = []
        if status:
            where_sql = "WHERE r.status = ?"
            params.append(status)

        cursor.execute(f"SELECT COUNT(*) as count FROM return_order r {where_sql}", params)
        total = cursor.fetchone()['count']

        cursor.execute(
            f"""
            SELECT
                r.*,
                o.order_no as out_order_no,
                u.username as operator_name,
                a.username as approved_by_name
            FROM return_order r
            LEFT JOIN out_order o ON r.related_out_order_id = o.id
            LEFT JOIN user u ON r.operator_id = u.id
            LEFT JOIN user a ON r.approved_by = a.id
            {where_sql}
            ORDER BY r.created_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset]
        )
        orders = [dict(row) for row in cursor.fetchall()]

        # Fetch items for each order
        for order in orders:
            cursor.execute(
                """
                SELECT
                    ri.*,
                    m.code as material_code,
                    m.name as material_name,
                    m.spec,
                    m.unit
                FROM return_order_item ri
                LEFT JOIN material m ON ri.material_id = m.id
                WHERE ri.return_order_id = ?
                """,
                (order['id'],)
            )
            order['items'] = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return orders, total

    @staticmethod
    def get_return_order_by_id(order_id):
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                r.*,
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
            conn.close()
            return None

        # Get items with initial gross weight from reusable_material_weight
        cursor.execute(
            """
            SELECT
                ri.*,
                m.code as material_code,
                m.name as material_name,
                m.spec,
                m.unit,
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
        conn.close()
        return result

    @staticmethod
    def create_return_order(related_out_order_id, department, receiver, receiver_date, operator_id, remark=None, items=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # Check if this out_order already has an approved return order
            if related_out_order_id:
                cursor.execute(
                    "SELECT COUNT(*) as count FROM return_order WHERE related_out_order_id = ? AND status = 'approved'",
                    (related_out_order_id,)
                )
                if cursor.fetchone()['count'] > 0:
                    conn.close()
                    raise Exception("该出库单已有审核通过的退库单,不允许再次退库")

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
                        """
                        INSERT INTO return_order_item (return_order_id, out_order_item_id, material_id, batch_no, return_quantity, remark, return_gross_weight, actual_net_weight)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (order_id, item['out_order_item_id'], item['material_id'],
                         item.get('batch_no'), item.get('return_quantity', 0), item.get('remark'), item.get('return_gross_weight'), item.get('actual_net_weight'))
                    )

            conn.commit()
            conn.close()
            return OrderService.get_return_order_by_id(order_id)
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    @staticmethod
    def update_return_order(order_id, department=None, receiver=None, receiver_date=None, remark=None, items=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT status FROM return_order WHERE id = ?", (order_id,))
            order = cursor.fetchone()
            if not order or order['status'] != 'pending':
                conn.close()
                return None

            updates = []
            params = []
            if department is not None:
                updates.append("department = ?")
                params.append(department)
            if receiver is not None:
                updates.append("receiver = ?")
                params.append(receiver)
            if receiver_date is not None:
                updates.append("receiver_date = ?")
                params.append(receiver_date)
            if remark is not None:
                updates.append("remark = ?")
                params.append(remark)

            if updates:
                params.append(order_id)
                cursor.execute(
                    f"UPDATE return_order SET {', '.join(updates)} WHERE id = ?",
                    params
                )

            if items is not None:
                cursor.execute("DELETE FROM return_order_item WHERE return_order_id = ?", (order_id,))
                for item in items:
                    cursor.execute(
                        """
                        INSERT INTO return_order_item (return_order_id, out_order_item_id, material_id, batch_no, return_quantity, remark, return_gross_weight, actual_net_weight)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (order_id, item['out_order_item_id'], item['material_id'],
                         item.get('batch_no'), item.get('return_quantity', 0), item.get('remark'), item.get('return_gross_weight'), item.get('actual_net_weight'))
                    )

            conn.commit()
            conn.close()
            return OrderService.get_return_order_by_id(order_id)
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    @staticmethod
    def delete_return_order(order_id):
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT status FROM return_order WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        if not order or order['status'] != 'pending':
            conn.close()
            return False

        cursor.execute("DELETE FROM return_order_item WHERE return_order_id = ?", (order_id,))
        cursor.execute("DELETE FROM return_order WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def approve_return_order(order_id, approved_by, weight_data=None):
        """审核退库单：回冲库存,更新原出库单状态
        weight_data: [{out_order_item_id, return_gross_weight}, ...]"""
        conn = get_db_connection()
        cursor = conn.cursor()
        weight_map = {w['out_order_item_id']: w['return_gross_weight'] for w in (weight_data or [])}

        try:
            cursor.execute("PRAGMA foreign_keys = ON")

            cursor.execute("SELECT * FROM return_order WHERE id = ?", (order_id,))
            order = cursor.fetchone()

            if not order or order['status'] != 'pending':
                conn.close()
                return None

            # 检查是否已有 approved 的退库单关联到同一个出库单
            if order['related_out_order_id']:
                cursor.execute(
                    "SELECT COUNT(*) FROM return_order WHERE related_out_order_id = ? AND status = 'approved' AND id != ?",
                    (order['related_out_order_id'], order_id)
                )
                if cursor.fetchone()[0] > 0:
                    conn.close()
                    return False, '该出库单已有审核通过的退库单，不能重复审核'

            # Get items
            cursor.execute("SELECT * FROM return_order_item WHERE return_order_id = ?", (order_id,))
            items = [dict(row) for row in cursor.fetchall()]

            # Process each return item
            for item in items:
                material_id = item['material_id']
                batch_no = item['batch_no']

                # Check if material is reusable
                cursor.execute("SELECT is_reusable FROM material WHERE id = ?", (material_id,))
                mat = cursor.fetchone()
                is_reusable = mat and mat['is_reusable'] == 1

                # Get return data from weight_map or from saved item
                return_weight = weight_map.get(item['out_order_item_id'])
                # If not in weight_map, use saved value from return_order_item
                if return_weight is None:
                    return_weight = item.get('return_gross_weight', 0) or 0
                actual_net_weight = item.get('actual_net_weight', 0)

                # Determine inventory change amount (to_add: positive = add to inventory, negative = deduct)
                # For reusable materials: deduct consumption (net_weight), add back return weight
                # For non-reusable: add back return_quantity
                if is_reusable:
                    # Get initial gross weight from weight record
                    cursor.execute(
                        "SELECT initial_gross_weight FROM reusable_material_weight WHERE out_order_item_id = ?",
                        (item['out_order_item_id'],)
                    )
                    weight_record = cursor.fetchone()
                    initial_weight = weight_record['initial_gross_weight'] if weight_record else 0

                    # Calculate net weight: initial - return = actual consumption
                    if return_weight is not None and return_weight > 0:
                        net_weight = initial_weight - return_weight
                    else:
                        net_weight = actual_net_weight if actual_net_weight > 0 else 0
                        return_weight = initial_weight - net_weight  # Calculate return_weight from net_weight

                    # Update weight record with return data
                    cursor.execute(
                        """UPDATE reusable_material_weight
                           SET return_gross_weight = ?, return_weight_time = datetime('now', 'localtime'),
                               return_operator_id = ?, actual_net_weight = ?, status = 'returned'
                           WHERE out_order_item_id = ?""",
                        (return_weight, approved_by, net_weight, item['out_order_item_id'])
                    )
                    # Update out_order_item actual_quantity to actual usage (net weight)
                    cursor.execute(
                        "UPDATE out_order_item SET actual_quantity = ? WHERE id = ?",
                        (net_weight, item['out_order_item_id'])
                    )
                    # Deduct actual consumption from inventory (what was used, not returned)
                    inventory_delta = -net_weight

                    # Update returned_quantity with actual return weight (for reference)
                    cursor.execute(
                        "UPDATE out_order_item SET returned_quantity = returned_quantity + ? WHERE id = ?",
                        (return_weight or 0, item['out_order_item_id'])
                    )
                else:
                    # For non-reusable materials
                    return_qty = item.get('return_quantity', 0) or actual_net_weight
                    if return_qty <= 0:
                        continue
                    cursor.execute(
                        "UPDATE out_order_item SET returned_quantity = returned_quantity + ? WHERE id = ?",
                        (return_qty, item['out_order_item_id'])
                    )
                    inventory_delta = return_qty

                # Check existing inventory batch
                cursor.execute(
                    "SELECT id, quantity FROM inventory WHERE material_id = ? AND batch_no = ?",
                    (material_id, batch_no)
                )
                inv = cursor.fetchone()

                if inv:
                    cursor.execute(
                        "UPDATE inventory SET quantity = quantity + ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
                        (inventory_delta, inv['id'])
                    )
                else:
                    # Get production_date and expiry_date from original in_order_item
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
                        (material_id, batch_no, return_qty,
                         orig['production_date'] if orig else None,
                         orig['expiry_date'] if orig else None)
                    )

            # Update return order status
            cursor.execute(
                "UPDATE return_order SET status = 'approved', approved_at = datetime('now', 'localtime'), approved_by = ? WHERE id = ?",
                (approved_by, order_id)
            )

            # Update related out_order status to 'completed'
            cursor.execute(
                "UPDATE out_order SET status = 'completed' WHERE id = ?",
                (order['related_out_order_id'],)
            )

            conn.commit()
            conn.close()
            return OrderService.get_return_order_by_id(order_id)
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    @staticmethod
    def get_return_orders_by_out_order(out_order_id):
        """获取指定出库单关联的退库单"""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                r.*,
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
        conn.close()

        return orders, len(orders)

    # Reusable material weight methods
    @staticmethod
    def is_material_reusable(material_id):
        """检查物料是否为可回用物料"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_reusable FROM material WHERE id = ?", (material_id,))
        row = cursor.fetchone()
        conn.close()
        return row and row['is_reusable'] == 1

    @staticmethod
    def create_weight_record(out_order_item_id, material_id, initial_gross_weight, operator_id):
        """创建称重记录(出库审核时)"""
        conn = get_db_connection()
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
            conn.close()
            return OrderService.get_weight_record_by_out_order_item(out_order_item_id)
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    @staticmethod
    def update_weight_record_return(out_order_item_id, return_gross_weight, operator_id):
        """更新称重记录(退库审核时): 计算净用量"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")

            # Get current weight record
            cursor.execute(
                "SELECT * FROM reusable_material_weight WHERE out_order_item_id = ?",
                (out_order_item_id,)
            )
            record = cursor.fetchone()
            if not record:
                conn.close()
                return None

            initial_weight = record['initial_gross_weight'] or 0
            net_weight = initial_weight - return_gross_weight

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
            conn.close()
            return OrderService.get_weight_record_by_out_order_item(out_order_item_id)
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

    @staticmethod
    def get_weight_record_by_out_order_item(out_order_item_id):
        """获取指定出库明细的称重记录"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                w.*,
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
        conn.close()
        return dict(record) if record else None

    @staticmethod
    def get_all_weight_records(page=1, per_page=20, status=None, material_code=None, material_name=None):
        """获取所有称重记录,支持分页和筛选"""
        conn = get_db_connection()
        cursor = conn.cursor()

        where_sql = ""
        params = []

        if status:
            where_sql += " AND w.status = ?"
            params.append(status)
        if material_code:
            where_sql += " AND m.code LIKE ?"
            params.append(f"{material_code}%")
        if material_name:
            where_sql += " AND m.name LIKE ?"
            params.append(f"%{material_name}%")

        # Get total count
        cursor.execute(
            f"SELECT COUNT(*) as count FROM reusable_material_weight w JOIN material m ON w.material_id = m.id WHERE 1=1 {where_sql}",
            params
        )
        total = cursor.fetchone()['count']

        # Get records with pagination
        offset = (page - 1) * per_page
        cursor.execute(
            f"""
            SELECT
                w.*,
                m.code as material_code,
                m.name as material_name,
                m.spec,
                m.unit,
                oi.batch_no,
                oi.order_id,
                o.order_no as out_order_no,
                o.receiver as initial_operator_name,
                r.receiver as return_operator_name
            FROM reusable_material_weight w
            JOIN material m ON w.material_id = m.id
            JOIN out_order_item oi ON w.out_order_item_id = oi.id
            JOIN out_order o ON oi.order_id = o.id
            LEFT JOIN return_order_item roi ON roi.out_order_item_id = w.out_order_item_id
            LEFT JOIN return_order r ON r.id = roi.return_order_id AND r.status = 'approved'
            WHERE 1=1 {where_sql}
            ORDER BY w.id DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset]
        )
        records = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return records, total

    @staticmethod
    def get_weight_records_by_out_order(order_id):
        """获取出库单所有明细的称重记录"""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                w.*,
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
        conn.close()
        return records
