from database import get_db_connection
from werkzeug.security import generate_password_hash


class UserService:
    """用户管理 service: 创建/删除/重置密码

    所有写操作均在同一事务, 失败回滚。
    业务校验抛 ValueError, 调用方转 400。
    密码统一以 hash 形式写入 (werkzeug pbkdf2 默认)。
    """

    @staticmethod
    def create_user(username, password):
        """创建用户, 默认分配查看员角色

        Args:
            username: 用户名
            password: 明文密码 (内部 hash 后存储)

        Returns:
            user_id (新创建用户的主键)

        Raises:
            ValueError: 用户名/密码为空, 密码长度 < 6, 用户名已存在
        """
        username = (username or '').strip()
        password = (password or '').strip()
        if not username or not password:
            raise ValueError('用户名和密码不能为空')
        if len(password) < 6:
            raise ValueError('密码长度不能少于6位')

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM user WHERE username = ?", (username,))
            if cursor.fetchone():
                raise ValueError('用户名已存在')

            cursor.execute(
                "INSERT INTO user (username, password) VALUES (?, ?)",
                (username, generate_password_hash(password))
            )
            user_id = cursor.lastrowid

            # 默认分配查看员角色
            cursor.execute("SELECT id FROM role WHERE name = '查看员'")
            viewer_role = cursor.fetchone()
            if viewer_role:
                cursor.execute(
                    "INSERT INTO user_role (user_id, role_id) VALUES (?, ?)",
                    (user_id, viewer_role['id'])
                )
            conn.commit()
        return user_id

    @staticmethod
    def delete_user(user_id, current_user_id):
        """删除用户及关联角色

        Args:
            user_id: 待删除用户 ID
            current_user_id: 当前登录用户 ID (用于自删拦截)

        Returns:
            True 成功

        Raises:
            ValueError: 不能删除自己, 不能删除 admin, 用户不存在
        """
        if current_user_id == user_id:
            raise ValueError('不能删除当前登录用户')

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username FROM user WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            if not user:
                raise ValueError('用户不存在')
            if user['username'] == 'admin':
                raise ValueError('不能删除管理员账号')

            cursor.execute("DELETE FROM user_role WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM user WHERE id = ?", (user_id,))
            conn.commit()
        return True

    @staticmethod
    def update_user_roles(user_id, role_ids):
        """更新用户角色 (全量替换)

        Args:
            user_id: 用户 ID
            role_ids: 角色 ID 列表, 空列表 = 清空所有角色

        Returns:
            True 成功

        Raises:
            ValueError: 用户不存在, 不能修改 admin 角色
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM user WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            if not user:
                raise ValueError('用户不存在')
            if user['username'] == 'admin':
                raise ValueError('不能修改管理员角色')

            cursor.execute("DELETE FROM user_role WHERE user_id = ?", (user_id,))
            for role_id in role_ids:
                cursor.execute(
                    "INSERT INTO user_role (user_id, role_id) VALUES (?, ?)",
                    (user_id, role_id)
                )
            conn.commit()
        return True

    @staticmethod
    def reset_password(user_id, new_password):
        """重置用户密码 (内部 hash 后存储)"""
        new_password = (new_password or '').strip()
        if not new_password:
            raise ValueError('新密码不能为空')
        if len(new_password) < 6:
            raise ValueError('密码长度不能少于6位')

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM user WHERE id = ?", (user_id,))
            if not cursor.fetchone():
                raise ValueError('用户不存在')

            cursor.execute(
                "UPDATE user SET password = ? WHERE id = ?",
                (generate_password_hash(new_password), user_id)
            )
            conn.commit()
        return True
