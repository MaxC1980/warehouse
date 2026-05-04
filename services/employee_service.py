from database import get_db_connection

class EmployeeService:
    @staticmethod
    def get_all_employees(page=1, per_page=20, keyword=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * per_page

        where_clauses = []
        params = []
        if keyword:
            where_clauses.append("(name LIKE ? OR department LIKE ? OR phone LIKE ?)")
            params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        cursor.execute(f"SELECT COUNT(*) as count FROM employee {where_sql}", params)
        total = cursor.fetchone()['count']

        cursor.execute(
            f"SELECT id, name, department, phone, remark, created_at FROM employee {where_sql} ORDER BY name LIMIT ? OFFSET ?",
            params + [per_page, offset]
        )
        employees = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return employees, total

    @staticmethod
    def get_employee_by_id(employee_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, department, phone, remark, created_at FROM employee WHERE id = ?", (employee_id,))
        employee = cursor.fetchone()
        conn.close()
        return dict(employee) if employee else None

    @staticmethod
    def create_employee(name, department=None, phone=None, remark=None):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO employee (name, department, phone, remark) VALUES (?, ?, ?, ?)",
                (name, department, phone, remark)
            )
            conn.commit()
            employee_id = cursor.lastrowid
            conn.close()
            return EmployeeService.get_employee_by_id(employee_id)
        except Exception as e:
            conn.close()
            raise e

    @staticmethod
    def update_employee(employee_id, data):
        conn = get_db_connection()
        cursor = conn.cursor()
        updates = []
        params = []
        if 'name' in data:
            updates.append("name = ?")
            params.append(data['name'])
        if 'department' in data:
            updates.append("department = ?")
            params.append(data['department'])
        if 'phone' in data:
            updates.append("phone = ?")
            params.append(data['phone'])
        if 'remark' in data:
            updates.append("remark = ?")
            params.append(data['remark'])
        if updates:
            params.append(employee_id)
            cursor.execute(f"UPDATE employee SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        conn.close()
        return EmployeeService.get_employee_by_id(employee_id)

    @staticmethod
    def delete_employee(employee_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM employee WHERE id = ?", (employee_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted
