from database import get_db_connection

class ReportService:
    @staticmethod
    def get_inventory_report(page=1, per_page=100, keyword=None, major_category=None, minor_category=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * per_page

        where_clauses = []
        params = []

        if keyword:
            where_clauses.append("(m.code LIKE ? OR m.name LIKE ? OR m.spec LIKE ? OR m.manufacturer LIKE ?)")
            params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])

        if major_category:
            where_clauses.append("m.category_code LIKE ?")
            params.append(major_category + '%')

        if minor_category:
            where_clauses.append("m.category_code = ?")
            params.append(minor_category)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Get total count (distinct materials)
        cursor.execute(
            f"""
            SELECT COUNT(DISTINCT m.id) as count
            FROM material m
            LEFT JOIN inventory i ON m.id = i.material_id
            {where_sql}
            """,
            params
        )
        total = cursor.fetchone()['count']

        # Get report data - aggregate by material
        cursor.execute(
            f"""
            SELECT
                m.code as material_code,
                m.name as material_name,
                m.spec,
                m.unit,
                m.manufacturer,
                m.safety_stock,
                COALESCE(SUM(i.quantity), 0) as quantity,
                CASE
                    WHEN COALESCE(SUM(i.quantity), 0) < m.safety_stock THEN '低于安全库存'
                    ELSE '正常'
                END as status
            FROM material m
            LEFT JOIN inventory i ON m.id = i.material_id
            {where_sql}
            GROUP BY m.id
            ORDER BY m.code
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset]
        )
        report_data = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return report_data, total

    @staticmethod
    def get_in_detail_report(page=1, per_page=100, date_from=None, date_to=None, material_id=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * per_page

        where_clauses = []
        params = []

        if date_from:
            where_clauses.append("o.receiver_date >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("o.receiver_date <= ?")
            params.append(date_to + ' 23:59:59')
        if material_id:
            where_clauses.append("i.material_id = ?")
            params.append(material_id)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Get total count
        cursor.execute(
            f"""
            SELECT COUNT(*) as count
            FROM in_order_item i
            JOIN in_order o ON i.order_id = o.id
            {where_sql}
            """,
            params
        )
        total = cursor.fetchone()['count']

        # Get report data
        cursor.execute(
            f"""
            SELECT
                o.order_no,
                o.receiver_date as created_at,
                s.name as supplier_name,
                m.code as material_code,
                m.name as material_name,
                m.spec,
                m.manufacturer,
                i.batch_no,
                i.quantity,
                i.unit_price,
                i.quantity * i.unit_price as amount,
                u.username as operator
            FROM in_order_item i
            JOIN in_order o ON i.order_id = o.id
            JOIN material m ON i.material_id = m.id
            LEFT JOIN supplier s ON o.supplier_id = s.id
            LEFT JOIN user u ON o.operator_id = u.id
            {where_sql}
            ORDER BY o.receiver_date DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset]
        )
        report_data = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return report_data, total

    @staticmethod
    def get_out_detail_report(page=1, per_page=100, date_from=None, date_to=None, material_id=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * per_page

        where_clauses = []
        params = []

        if date_from:
            where_clauses.append("o.receiver_date >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("o.receiver_date <= ?")
            params.append(date_to + ' 23:59:59')
        if material_id:
            where_clauses.append("i.material_id = ?")
            params.append(material_id)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Get total count
        cursor.execute(
            f"""
            SELECT COUNT(*) as count
            FROM out_order_item i
            JOIN out_order o ON i.order_id = o.id
            {where_sql}
            """,
            params
        )
        total = cursor.fetchone()['count']

        # Get report data
        cursor.execute(
            f"""
            SELECT
                o.order_no,
                o.receiver_date as created_at,
                o.department,
                m.code as material_code,
                m.name as material_name,
                m.spec,
                m.manufacturer,
                i.batch_no,
                i.actual_quantity,
                i.unit_price,
                i.actual_quantity * i.unit_price as amount,
                u.username as operator
            FROM out_order_item i
            JOIN out_order o ON i.order_id = o.id
            JOIN material m ON i.material_id = m.id
            LEFT JOIN user u ON o.operator_id = u.id
            {where_sql}
            ORDER BY o.receiver_date DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset]
        )
        report_data = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return report_data, total

    @staticmethod
    def get_summary_report(date_from=None, date_to=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        where_clauses = []
        params = []

        if date_from:
            where_clauses.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("created_at <= ?")
            params.append(date_to + ' 23:59:59')

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Total materials
        cursor.execute("SELECT COUNT(*) as count FROM material")
        total_materials = cursor.fetchone()['count']

        # Total suppliers
        cursor.execute("SELECT COUNT(*) as count FROM supplier")
        total_suppliers = cursor.fetchone()['count']

        # Low stock count
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM inventory i
            JOIN material m ON i.material_id = m.id
            WHERE i.quantity < m.safety_stock
            """
        )
        low_stock_count = cursor.fetchone()['count']

        # Pending in orders
        cursor.execute("SELECT COUNT(*) as count FROM in_order WHERE status = 'pending'")
        pending_in = cursor.fetchone()['count']

        # Pending out orders
        cursor.execute("SELECT COUNT(*) as count FROM out_order WHERE status = 'pending'")
        pending_out = cursor.fetchone()['count']

        # In order stats
        cursor.execute(
            f"""
            SELECT
                COUNT(*) as count,
                COALESCE(SUM(quantity * unit_price), 0) as total_amount
            FROM in_order_item i
            JOIN in_order o ON i.order_id = o.id
            {where_sql}
            """,
            params
        )
        in_stats = cursor.fetchone()

        # Out order stats
        cursor.execute(
            f"""
            SELECT
                COUNT(*) as count,
                COALESCE(SUM(actual_quantity * unit_price), 0) as total_amount
            FROM out_order_item i
            JOIN out_order o ON i.order_id = o.id
            {where_sql}
            """,
            params
        )
        out_stats = cursor.fetchone()

        conn.close()

        return {
            'total_materials': total_materials,
            'total_suppliers': total_suppliers,
            'low_stock_count': low_stock_count,
            'pending_in': pending_in,
            'pending_out': pending_out,
            'in_order_count': in_stats['count'],
            'in_order_amount': in_stats['total_amount'],
            'out_order_count': out_stats['count'],
            'out_order_amount': out_stats['total_amount']
        }

    @staticmethod
    def get_stock_flow_report(page=1, per_page=100, date_from=None, date_to=None, keyword=None, major_category=None, minor_category=None, hide_zero=False, hide_no_change=False):
        conn = get_db_connection()
        cursor = conn.cursor()
        offset = (page - 1) * per_page

        where_clauses = []
        params = []

        if keyword:
            where_clauses.append("(m.code LIKE ? OR m.name LIKE ? OR m.spec LIKE ? OR m.manufacturer LIKE ?)")
            params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])

        if major_category:
            where_clauses.append("m.category_code LIKE ?")
            params.append(major_category + '%')

        if minor_category:
            where_clauses.append("m.category_code = ?")
            params.append(minor_category)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # 先查符合条件的 material，再用 subquery 计算汇总
        inner_sql = f"""
            SELECT
                m.id,
                m.code as material_code,
                m.name as material_name,
                m.manufacturer,
                m.spec,
                m.unit,
                (SELECT COALESCE(SUM(ioi.quantity), 0) FROM in_order_item ioi JOIN in_order io ON ioi.order_id = io.id WHERE ioi.material_id = m.id AND io.status = 'approved' AND io.receiver_date < ?) as opening_in,
                (SELECT COALESCE(SUM(ooi.actual_quantity), 0) FROM out_order_item ooi JOIN out_order oo ON ooi.order_id = oo.id WHERE ooi.material_id = m.id AND oo.status = 'approved' AND oo.receiver_date < ?) as opening_out,
                (SELECT COALESCE(SUM(ioi.quantity), 0) FROM in_order_item ioi JOIN in_order io ON ioi.order_id = io.id WHERE ioi.material_id = m.id AND io.status = 'approved' AND io.receiver_date >= ? AND io.receiver_date <= ?) as period_in,
                (SELECT COALESCE(SUM(ooi.actual_quantity), 0) FROM out_order_item ooi JOIN out_order oo ON ooi.order_id = oo.id WHERE ooi.material_id = m.id AND oo.status = 'approved' AND oo.receiver_date >= ? AND oo.receiver_date <= ?) as period_out
            FROM material m
            {where_sql}
        """

        data_sql = f"""
            SELECT
                id, material_code, material_name, manufacturer, spec, unit,
                opening_in - opening_out as opening_qty,
                period_in as in_qty,
                period_out as out_qty,
                opening_in - opening_out + period_in - period_out as closing_qty
            FROM ({inner_sql}) t
        """

        filter_conditions = []
        if hide_zero:
            filter_conditions.append("((opening_in - opening_out) != 0 OR period_in != 0 OR period_out != 0)")
        if hide_no_change:
            filter_conditions.append("(period_in != 0 OR period_out != 0)")

        if filter_conditions:
            data_sql += " WHERE " + " AND ".join(filter_conditions)

        data_sql += " ORDER BY material_code LIMIT ? OFFSET ?"

        # Count
        count_sql = f"SELECT COUNT(*) FROM ({inner_sql}) t"
        if filter_conditions:
            count_sql += " WHERE " + " AND ".join(filter_conditions)

        cursor.execute(count_sql, [date_from, date_from, date_from, date_to, date_from, date_to] + params)
        total = cursor.fetchone()[0]

        cursor.execute(data_sql, [date_from, date_from, date_from, date_to, date_from, date_to] + params + [per_page, offset])

        report_data = []
        for row in cursor.fetchall():
            item = dict(row)
            item['opening_qty'] = round(item['opening_qty'], 2)
            item['in_qty'] = round(item['in_qty'], 2)
            item['out_qty'] = round(item['out_qty'], 2)
            item['closing_qty'] = round(item['closing_qty'], 2)
            report_data.append(item)

        conn.close()
        return report_data, total
