from database import get_db_connection
from utils.sql import build_update_sql, build_like_clause

CUSTOMER_UPDATE_FIELDS = ['name', 'short_name', 'contact', 'phone', 'address', 'remark']


class CustomerService:
    @staticmethod
    def get_customers(page=1, per_page=20, keyword=None):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            offset = (page - 1) * per_page
            where_sql = ""
            params = []
            if keyword:
                where_sql = 'WHERE ' + build_like_clause(
                    ['name', 'short_name', 'contact', 'phone'], keyword, params
                )
            cursor.execute(
                f"SELECT COUNT(*) as count FROM customer {where_sql}", params
            )
            total = cursor.fetchone()['count']
            cursor.execute(
                f"SELECT id, name, short_name, contact, phone, address, remark, created_at "
                f"FROM customer {where_sql} ORDER BY id LIMIT ? OFFSET ?",
                params + [per_page, offset]
            )
            items = [dict(row) for row in cursor.fetchall()]
        return items, total

    @staticmethod
    def get_customer_by_id(customer_id):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, short_name, contact, phone, address, remark, created_at FROM customer WHERE id = ?",
                (customer_id,)
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def create_customer(name, short_name=None, contact=None, phone=None, address=None, remark=None):
        if not name or not str(name).strip():
            raise ValueError('客户名称不能为空')
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO customer (name, short_name, contact, phone, address, remark) VALUES (?, ?, ?, ?, ?, ?)",
                (name, short_name, contact, phone, address, remark)
            )
            conn.commit()
            return CustomerService.get_customer_by_id(cursor.lastrowid)

    @staticmethod
    def update_customer(customer_id, data):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            payload = {**data, 'id': customer_id}
            sql, params = build_update_sql('customer', payload, CUSTOMER_UPDATE_FIELDS)
            if sql:
                cursor.execute(sql, params)
                conn.commit()
        return CustomerService.get_customer_by_id(customer_id)

    @staticmethod
    def delete_customer(customer_id):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM customer WHERE id = ?", (customer_id,))
            if not cursor.fetchone():
                return False, '客户不存在'
            cursor.execute("DELETE FROM customer WHERE id = ?", (customer_id,))
            conn.commit()
        return True, None
