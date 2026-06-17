from database import get_db_connection
from utils.sql import escape_like, build_update_sql, build_like_clause

SUPPLIER_UPDATE_FIELDS = ['name', 'contact', 'phone', 'address']

class SupplierService:
    @staticmethod
    def get_suppliers(page=1, per_page=20, keyword=None):
        with get_db_connection() as conn:
            cursor = conn.cursor()

            offset = (page - 1) * per_page

            where_sql = ""
            params = []

            if keyword:
                where_sql = 'WHERE ' + build_like_clause(['name', 'contact', 'phone'], keyword, params)

            # Get total count
            cursor.execute(f"SELECT COUNT(*) as count FROM supplier {where_sql}", params)
            total = cursor.fetchone()['count']

            # Get suppliers
            cursor.execute(
                f"SELECT id, name, contact, phone, address, created_at FROM supplier {where_sql} ORDER BY id LIMIT ? OFFSET ?",
                params + [per_page, offset]
            )
            suppliers = [dict(row) for row in cursor.fetchall()]

        return suppliers, total

    @staticmethod
    def get_supplier_by_id(supplier_id):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, contact, phone, address, created_at FROM supplier WHERE id = ?", (supplier_id,))
            supplier = cursor.fetchone()
            if supplier:
                return dict(supplier)
        return None

    @staticmethod
    def create_supplier(name, contact=None, phone=None, address=None):
        if not name or not str(name).strip():
            raise ValueError('名称不能为空')
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO supplier (name, contact, phone, address) VALUES (?, ?, ?, ?)",
                (name, contact, phone, address)
            )
            conn.commit()
            supplier_id = cursor.lastrowid

        return SupplierService.get_supplier_by_id(supplier_id)

    @staticmethod
    def update_supplier(supplier_id, data):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            data = {**data, 'id': supplier_id}
            sql, params = build_update_sql('supplier', data, SUPPLIER_UPDATE_FIELDS)
            if sql:
                cursor.execute(sql, params)
                conn.commit()
        return SupplierService.get_supplier_by_id(supplier_id)

    @staticmethod
    def delete_supplier(supplier_id):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM in_order WHERE supplier_id = ?", (supplier_id,))
            if cursor.fetchone()['count'] > 0:
                return False, '该供应商已被入库单引用，无法删除'
            cursor.execute("DELETE FROM supplier WHERE id = ?", (supplier_id,))
            conn.commit()
        return True, None
