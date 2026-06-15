from database import get_db_connection
from werkzeug.security import generate_password_hash, check_password_hash

# werkzeug 各种 hash 算法的前缀 (3.x 默认 scrypt, 旧版 pbkdf2)
_HASH_PREFIXES = ('pbkdf2:', 'scrypt:', 'argon2:')


def _is_hash(value):
    """判断值是否是 werkzeug 生成的 hash (而非明文)"""
    return value.startswith(_HASH_PREFIXES)


class AuthService:
    @staticmethod
    def authenticate(username, password):
        """校验用户密码, 首次登录成功后自动将明文升级为 hash (原地覆盖 password 列)

        Returns:
            成功返回 {'id', 'username'}, 失败 None
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, password FROM user WHERE username = ?",
                (username,)
            )
            user = cursor.fetchone()
            if not user:
                return None

            stored = user['password'] or ''

            if _is_hash(stored):
                if check_password_hash(stored, password):
                    return {'id': user['id'], 'username': user['username']}
                return None

            # 旧明文: 校验通过后原地升级为 hash
            if stored == password:
                cursor.execute(
                    "UPDATE user SET password = ? WHERE id = ?",
                    (generate_password_hash(password), user['id'])
                )
                conn.commit()
                return {'id': user['id'], 'username': user['username']}

            return None

    @staticmethod
    def get_user_by_id(user_id):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username FROM user WHERE id = ?",
                (user_id,)
            )
            user = cursor.fetchone()

        if user:
            return {
                'id': user['id'],
                'username': user['username']
            }
        return None

    @staticmethod
    def change_password(user_id, old_password, new_password):
        """修改密码 (old 用明文校验兼容旧账号, new 写 hash)"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT password FROM user WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            if not user:
                return False, '用户不存在'

            stored = user['password'] or ''
            if _is_hash(stored):
                if not check_password_hash(stored, old_password):
                    return False, '旧密码错误'
            else:
                if stored != old_password:
                    return False, '旧密码错误'

            cursor.execute(
                "UPDATE user SET password = ? WHERE id = ?",
                (generate_password_hash(new_password), user_id)
            )
            conn.commit()

        return True, None
