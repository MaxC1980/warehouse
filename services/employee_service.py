from database import get_db_connection
from utils.sql import escape_like, build_update_sql

EMPLOYEE_UPDATE_FIELDS = ['name', 'department', 'phone', 'remark']

class EmployeeService:
    @staticmethod
    def get_all_employees(page=1, per_page=20, keyword=None):
        with get_db_connection() as conn:
            cursor = conn.cursor()

            offset = (page - 1) * per_page

            where_clauses = []
            params = []
            if keyword:
                kw = escape_like(keyword)
                where_clauses.append("(name LIKE ? ESCAPE '\\' OR department LIKE ? ESCAPE '\\' OR phone LIKE ? ESCAPE '\\')")
                params.extend([f'%{kw}%', f'%{kw}%', f'%{kw}%'])

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            cursor.execute(f"SELECT COUNT(*) as count FROM employee {where_sql}", params)
            total = cursor.fetchone()['count']

            cursor.execute(
                f"SELECT id, name, department, phone, remark, created_at FROM employee {where_sql} ORDER BY name LIMIT ? OFFSET ?",
                params + [per_page, offset]
            )
            employees = [dict(row) for row in cursor.fetchall()]

        return employees, total

    @staticmethod
    def get_employee_by_id(employee_id):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, department, phone, remark, created_at FROM employee WHERE id = ?", (employee_id,))
            employee = cursor.fetchone()
        return dict(employee) if employee else None

    @staticmethod
    def create_employee(name, department=None, phone=None, remark=None):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO employee (name, department, phone, remark) VALUES (?, ?, ?, ?)",
                (name, department, phone, remark)
            )
            conn.commit()
            employee_id = cursor.lastrowid

        return EmployeeService.get_employee_by_id(employee_id)

    @staticmethod
    def update_employee(employee_id, data):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            data = {**data, 'id': employee_id}
            sql, params = build_update_sql('employee', data, EMPLOYEE_UPDATE_FIELDS)
            if sql:
                cursor.execute(sql, params)
                conn.commit()
        return EmployeeService.get_employee_by_id(employee_id)

    @staticmethod
    def delete_employee(employee_id):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM employee WHERE id = ?", (employee_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
        return deleted
