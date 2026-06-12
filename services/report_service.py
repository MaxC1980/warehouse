from database import get_db_connection
from datetime import datetime
from utils.sql import escape_like

class ReportService:
    @staticmethod
    def get_inventory_report(page=1, per_page=100, keyword=None, major_category=None, minor_category=None):
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if per_page is not None:
                offset = (page - 1) * per_page

            where_clauses = []
            params = []

            if keyword:
                kw = escape_like(keyword)
                where_clauses.append("(m.code LIKE ? ESCAPE '\\' OR m.name LIKE ? ESCAPE '\\' OR m.spec LIKE ? ESCAPE '\\' OR m.manufacturer LIKE ? ESCAPE '\\')")
                params.extend([f'%{kw}%', f'%{kw}%', f'%{kw}%', f'%{kw}%'])

            if major_category:
                mc = escape_like(major_category)
                where_clauses.append("m.category_code LIKE ? ESCAPE '\\'")
                params.append(mc + '%')

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
                {"LIMIT ? OFFSET ?" if per_page is not None else ""}
                """,
                params + ([per_page, offset] if per_page is not None else [])
            )
            report_data = [dict(row) for row in cursor.fetchall()]

        return report_data, total

    @staticmethod
    def get_in_detail_report(page=1, per_page=100, date_from=None, date_to=None, material_id=None):
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if per_page is not None:
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
                {"LIMIT ? OFFSET ?" if per_page is not None else ""}
                """,
                params + ([per_page, offset] if per_page is not None else [])
            )
            report_data = [dict(row) for row in cursor.fetchall()]

        return report_data, total

    @staticmethod
    def get_out_detail_report(page=1, per_page=100, date_from=None, date_to=None, material_id=None):
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if per_page is not None:
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
                    COALESCE(i.unit_price, 0) as unit_price,
                    COALESCE(i.actual_quantity, 0) * COALESCE(i.unit_price, 0) as amount,
                    u.username as operator
                FROM out_order_item i
                JOIN out_order o ON i.order_id = o.id
                JOIN material m ON i.material_id = m.id
                LEFT JOIN user u ON o.operator_id = u.id
                {where_sql}
                ORDER BY o.receiver_date DESC
                {"LIMIT ? OFFSET ?" if per_page is not None else ""}
                """,
                params + ([per_page, offset] if per_page is not None else [])
            )
            report_data = [dict(row) for row in cursor.fetchall()]

        return report_data, total

    @staticmethod
    def get_summary_report(date_from=None, date_to=None):
        with get_db_connection() as conn:
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

            # Low stock count (物料级别，汇总各批次后低于安全库存才计)
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM (
                    SELECT m.id
                    FROM material m
                    LEFT JOIN inventory i ON m.id = i.material_id
                    GROUP BY m.id
                    HAVING COALESCE(SUM(i.quantity), 0) < m.safety_stock
                )
                """
            )
            low_stock_count = cursor.fetchone()['count']

            # Expired count (物料级别，有任一批次过期即计入，仅有库存的)
            today_ymd = datetime.now().strftime('%Y%m%d')
            p1 = "INSTR(i.expiry_date, '-')"
            rest = f"SUBSTR(i.expiry_date, {p1}+1)"
            p2 = f"INSTR({rest}, '-') + {p1}"
            year = f"SUBSTR(i.expiry_date, 1, {p1}-1)"
            month = f"SUBSTR(i.expiry_date, {p1}+1, {p2}-{p1}-1)"
            day = f"SUBSTR(i.expiry_date, {p2}+1)"
            ymd_expr = f"{year} || PRINTF('%02d', CAST({month} AS INTEGER)) || PRINTF('%02d', CAST({day} AS INTEGER))"
            cursor.execute(
                f"""
                SELECT COUNT(DISTINCT m.id) as count
                FROM inventory i
                JOIN material m ON i.material_id = m.id
                WHERE i.quantity > 0 AND i.expiry_date IS NOT NULL AND {ymd_expr} < '{today_ymd}'
                """
            )
            expired_count = cursor.fetchone()['count']

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

        return {
            'total_materials': total_materials,
            'total_suppliers': total_suppliers,
            'low_stock_count': low_stock_count,
            'expired_count': expired_count,
            'pending_in': pending_in,
            'pending_out': pending_out,
            'in_order_count': in_stats['count'],
            'in_order_amount': in_stats['total_amount'],
            'out_order_count': out_stats['count'],
            'out_order_amount': out_stats['total_amount']
        }

    @staticmethod
    def get_stock_flow_report(page=1, per_page=100, date_from=None, date_to=None, keyword=None, major_category=None, minor_category=None, hide_zero=False, hide_no_change=False):
        if not date_from or not date_to:
            raise ValueError('date_from 和 date_to 不能为空')

        with get_db_connection() as conn:
            cursor = conn.cursor()
            if per_page is not None:
                offset = (page - 1) * per_page

            where_clauses = []
            params = []

            if keyword:
                kw = escape_like(keyword)
                where_clauses.append("(m.code LIKE ? ESCAPE '\\' OR m.name LIKE ? ESCAPE '\\' OR m.spec LIKE ? ESCAPE '\\' OR m.manufacturer LIKE ? ESCAPE '\\')")
                params.extend([f'%{kw}%', f'%{kw}%', f'%{kw}%', f'%{kw}%'])

            if major_category:
                mc = escape_like(major_category)
                where_clauses.append("m.category_code LIKE ? ESCAPE '\\'")
                params.append(mc + '%')

            if minor_category:
                where_clauses.append("m.category_code = ?")
                params.append(minor_category)

            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)

            inner_sql = f"""
                SELECT
                    m.id,
                    m.code as material_code,
                    m.name as material_name,
                    m.manufacturer,
                    m.spec,
                    m.unit,
                    (SELECT COALESCE(SUM(ioi.quantity), 0) FROM in_order_item ioi JOIN in_order io ON ioi.order_id = io.id WHERE ioi.material_id = m.id AND io.status = 'approved' AND io.receiver_date < ?) as opening_in,
                    (SELECT COALESCE(SUM(ooi.actual_quantity), 0) FROM out_order_item ooi JOIN out_order oo ON ooi.order_id = oo.id WHERE ooi.material_id = m.id AND oo.status IN ('approved', 'completed') AND oo.receiver_date < ?) as opening_out,
                    (SELECT COALESCE(SUM(ioi.quantity), 0) FROM in_order_item ioi JOIN in_order io ON ioi.order_id = io.id WHERE ioi.material_id = m.id AND io.status = 'approved' AND io.receiver_date >= ? AND io.receiver_date <= ?) as period_in,
                    (SELECT COALESCE(SUM(ooi.actual_quantity), 0) FROM out_order_item ooi JOIN out_order oo ON ooi.order_id = oo.id WHERE ooi.material_id = m.id AND oo.status IN ('approved', 'completed') AND oo.receiver_date >= ? AND oo.receiver_date <= ?) as period_out,
                    (SELECT COALESCE(SUM(ooi2.actual_quantity - roi.actual_net_weight), 0) FROM return_order_item roi JOIN return_order ro ON roi.return_order_id = ro.id JOIN out_order_item ooi2 ON roi.out_order_item_id = ooi2.id WHERE roi.material_id = m.id AND ro.status = 'approved' AND ro.receiver_date < ?) as opening_return,
                    (SELECT COALESCE(SUM(ooi3.actual_quantity - roi2.actual_net_weight), 0) FROM return_order_item roi2 JOIN return_order ro2 ON roi2.return_order_id = ro2.id JOIN out_order_item ooi3 ON roi2.out_order_item_id = ooi3.id WHERE roi2.material_id = m.id AND ro2.status = 'approved' AND ro2.receiver_date >= ? AND ro2.receiver_date <= ?) as period_return
                FROM material m
                {where_sql}
            """

            data_sql = f"""
                SELECT
                    id, material_code, material_name, manufacturer, spec, unit,
                    opening_in - opening_out + opening_return as opening_qty,
                    period_in as in_qty,
                    period_out as out_qty,
                    period_return as return_qty,
                    opening_in - opening_out + opening_return + period_in - period_out + period_return as closing_qty
                FROM ({inner_sql}) t
            """

            filter_conditions = []
            if hide_zero:
                filter_conditions.append("((opening_in - opening_out + opening_return) != 0 OR period_in != 0 OR period_out != 0 OR period_return != 0)")
            if hide_no_change:
                filter_conditions.append("(period_in != 0 OR period_out != 0 OR period_return != 0)")

            if filter_conditions:
                data_sql += " WHERE " + " AND ".join(filter_conditions)

            if per_page is not None:
                data_sql += " ORDER BY material_code LIMIT ? OFFSET ?"
            else:
                data_sql += " ORDER BY material_code"

            count_sql = f"SELECT COUNT(*) FROM ({inner_sql}) t"
            if filter_conditions:
                count_sql += " WHERE " + " AND ".join(filter_conditions)

            date_params = [date_from, date_from, date_from, date_to, date_from, date_to, date_from, date_from, date_to]
            cursor.execute(count_sql, date_params + params)
            total = cursor.fetchone()[0]

            cursor.execute(data_sql, date_params + params + ([per_page, offset] if per_page is not None else []))

            report_data = []
            for row in cursor.fetchall():
                item = dict(row)
                item['opening_qty'] = round(item['opening_qty'], 2)
                item['in_qty'] = round(item['in_qty'], 2)
                item['out_qty'] = round(item['out_qty'], 2)
                item['return_qty'] = round(item['return_qty'], 2)
                item['closing_qty'] = round(item['closing_qty'], 2)
                report_data.append(item)

        return report_data, total
