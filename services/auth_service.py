from database import get_db_connection

class AuthService:
    @staticmethod
    def authenticate(username, password):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, permission_level FROM user WHERE username = ? AND password = ?",
            (username, password)
        )
        user = cursor.fetchone()
        conn.close()

        if user:
            return {
                'id': user['id'],
                'username': user['username'],
                'permission_level': user['permission_level'] if 'permission_level' in user.keys() else 1
            }
        return None

    @staticmethod
    def get_user_by_id(user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, permission_level FROM user WHERE id = ?",
            (user_id,)
        )
        user = cursor.fetchone()
        conn.close()

        if user:
            return {
                'id': user['id'],
                'username': user['username'],
                'permission_level': user['permission_level'] if 'permission_level' in user.keys() else 1
            }
        return None

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
