from database import get_db_connection
from utils.sql import escape_like

class SupplierService:
    @staticmethod
    def get_suppliers(page=1, per_page=20, keyword=None):
        with get_db_connection() as conn:
            cursor = conn.cursor()

            offset = (page - 1) * per_page

            where_sql = ""
            params = []

            if keyword:
                kw = escape_like(keyword)
                where_sql = "WHERE name LIKE ? ESCAPE '\\' OR contact LIKE ? ESCAPE '\\' OR phone LIKE ? ESCAPE '\\'"
                params = [f'%{kw}%', f'%{kw}%', f'%{kw}%']

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

            updates = []
            params = []

            if 'name' in data:
                updates.append("name = ?")
                params.append(data['name'])
            if 'contact' in data:
                updates.append("contact = ?")
                params.append(data['contact'])
            if 'phone' in data:
                updates.append("phone = ?")
                params.append(data['phone'])
            if 'address' in data:
                updates.append("address = ?")
                params.append(data['address'])

            if updates:
                params.append(supplier_id)
                cursor.execute(
                    f"UPDATE supplier SET {', '.join(updates)} WHERE id = ?",
                    params
                )
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
