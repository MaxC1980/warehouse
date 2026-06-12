from database import get_db_connection


class PermissionService:

    @staticmethod
    def get_user_permissions(user_id):
        """返回用户所有权限的 (module, action) 集合"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT DISTINCT p.module, p.action
                   FROM permission p
                   JOIN role_permission rp ON p.id = rp.permission_id
                   JOIN user_role ur ON rp.role_id = ur.role_id
                   WHERE ur.user_id = ?""",
                (user_id,)
            )
            return {(row['module'], row['action']) for row in cursor.fetchall()}

    @staticmethod
    def has_permission(user_id, module, action):
        """检查用户是否有指定权限"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT 1 FROM permission p
                   JOIN role_permission rp ON p.id = rp.permission_id
                   JOIN user_role ur ON rp.role_id = ur.role_id
                   WHERE ur.user_id = ? AND p.module = ? AND p.action = ?
                   LIMIT 1""",
                (user_id, module, action)
            )
            return cursor.fetchone() is not None

    @staticmethod
    def get_all_roles():
        """获取所有角色"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, description, is_system FROM role ORDER BY id")
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_role_permissions(role_id):
        """获取角色的所有权限ID"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT permission_id FROM role_permission WHERE role_id = ?",
                (role_id,)
            )
            return [row['permission_id'] for row in cursor.fetchall()]

    @staticmethod
    def get_all_permissions():
        """获取所有权限定义"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, module, action, name FROM permission ORDER BY id")
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def create_role(name, description, permission_ids):
        """创建角色"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO role (name, description) VALUES (?, ?)",
                (name, description)
            )
            role_id = cursor.lastrowid
            for pid in permission_ids:
                cursor.execute(
                    "INSERT INTO role_permission (role_id, permission_id) VALUES (?, ?)",
                    (role_id, pid)
                )
            conn.commit()
            return role_id

    @staticmethod
    def update_role(role_id, name, description, permission_ids):
        """更新角色"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT is_system FROM role WHERE id = ?",
                (role_id,)
            )
            role = cursor.fetchone()
            if not role:
                raise ValueError('角色不存在')
            if role['is_system']:
                raise ValueError('系统内置角色不可修改')

            cursor.execute(
                "UPDATE role SET name = ?, description = ? WHERE id = ?",
                (name, description, role_id)
            )
            cursor.execute("DELETE FROM role_permission WHERE role_id = ?", (role_id,))
            for pid in permission_ids:
                cursor.execute(
                    "INSERT INTO role_permission (role_id, permission_id) VALUES (?, ?)",
                    (role_id, pid)
                )
            conn.commit()

    @staticmethod
    def delete_role(role_id):
        """删除角色（系统内置角色不可删）"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT is_system FROM role WHERE id = ?",
                (role_id,)
            )
            role = cursor.fetchone()
            if not role:
                raise ValueError('角色不存在')
            if role['is_system']:
                raise ValueError('系统内置角色不可删除')

            cursor.execute("SELECT COUNT(*) as cnt FROM user_role WHERE role_id = ?", (role_id,))
            if cursor.fetchone()['cnt'] > 0:
                raise ValueError('该角色下有用户，不能删除')

            cursor.execute("DELETE FROM role_permission WHERE role_id = ?", (role_id,))
            cursor.execute("DELETE FROM user_role WHERE role_id = ?", (role_id,))
            cursor.execute("DELETE FROM role WHERE id = ?", (role_id,))
            conn.commit()

    @staticmethod
    def assign_role(user_id, role_id):
        """给用户分配角色"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO user_role (user_id, role_id) VALUES (?, ?)",
                (user_id, role_id)
            )
            conn.commit()

    @staticmethod
    def remove_role(user_id, role_id):
        """移除用户角色"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM user_role WHERE user_id = ? AND role_id = ?",
                (user_id, role_id)
            )
            conn.commit()

    @staticmethod
    def get_user_roles(user_id):
        """获取用户的所有角色"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT r.id, r.name, r.description
                   FROM role r
                   JOIN user_role ur ON r.id = ur.role_id
                   WHERE ur.user_id = ?""",
                (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_users_with_roles():
        """获取所有用户及其角色"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT u.id, u.username,
                          GROUP_CONCAT(r.name, ', ') as roles
                   FROM user u
                   LEFT JOIN user_role ur ON u.id = ur.user_id
                   LEFT JOIN role r ON ur.role_id = r.id
                   GROUP BY u.id
                   ORDER BY u.id"""
            )
            return [dict(row) for row in cursor.fetchall()]
