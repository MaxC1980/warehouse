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
            where_clauses.append("(m.code LIKE ? OR m.name LIKE ? OR m.spec LIKE ?)")
            params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])

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
            where_clauses.append("o.created_at >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("o.created_at <= ?")
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
                o.created_at,
                s.name as supplier_name,
                m.code as material_code,
                m.name as material_name,
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
            ORDER BY o.created_at DESC
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
            where_clauses.append("o.created_at >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("o.created_at <= ?")
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
                o.created_at,
                o.department,
                m.code as material_code,
                m.name as material_name,
                i.batch_no,
                i.quantity,
                i.unit_price,
                i.quantity * i.unit_price as amount,
                u.username as operator
            FROM out_order_item i
            JOIN out_order o ON i.order_id = o.id
            JOIN material m ON i.material_id = m.id
            LEFT JOIN user u ON o.operator_id = u.id
            {where_sql}
            ORDER BY o.created_at DESC
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
                COALESCE(SUM(quantity * unit_price), 0) as total_amount
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
