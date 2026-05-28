from database import get_db_connection

class AuthService:
    @staticmethod
    def authenticate(username, password):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, permission_level FROM user WHERE username = ? AND password = ?",
                (username, password)
            )
            user = cursor.fetchone()

        if user:
            return {
                'id': user['id'],
                'username': user['username'],
                'permission_level': user['permission_level'] if 'permission_level' in user.keys() else 1
            }
        return None

    @staticmethod
    def get_user_by_id(user_id):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, permission_level FROM user WHERE id = ?",
                (user_id,)
            )
            user = cursor.fetchone()

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
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Verify old password
            cursor.execute("SELECT password FROM user WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            if not user or user['password'] != old_password:
                return False, '旧密码错误'

            # Update new password
            cursor.execute("UPDATE user SET password = ? WHERE id = ?", (new_password, user_id))
            conn.commit()

        return True, None
