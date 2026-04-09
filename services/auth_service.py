from database import get_db_connection

class AuthService:
    @staticmethod
    def authenticate(username, password):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, can_approve FROM user WHERE username = ? AND password = ?",
            (username, password)
        )
        user = cursor.fetchone()
        conn.close()

        if user:
            return {'id': user['id'], 'username': user['username'], 'can_approve': user['can_approve']}
        return None

    @staticmethod
    def get_user_by_id(user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, can_approve FROM user WHERE id = ?",
            (user_id,)
        )
        user = cursor.fetchone()
        conn.close()

        if user:
            return {'id': user['id'], 'username': user['username'], 'can_approve': user['can_approve']}
        return None

    @staticmethod
    def check_can_approve(user_id):
        """检查用户是否有审核权限"""
        user = AuthService.get_user_by_id(user_id)
        if user:
            return user.get('can_approve', 0) == 1
        return False

    @staticmethod
    def change_password(user_id, old_password, new_password):
        """修改密码"""
        conn = get_db_connection()
        cursor = conn.cursor()
        # Verify old password
        cursor.execute("SELECT password FROM user WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user or user['password'] != old_password:
            conn.close()
            return False, '旧密码错误'

        # Update new password
        cursor.execute("UPDATE user SET password = ? WHERE id = ?", (new_password, user_id))
        conn.commit()
        conn.close()
        return True, None
