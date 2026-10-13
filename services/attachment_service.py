import logging
import os
import uuid

from config import Config
from database import get_db_connection

logger = logging.getLogger(__name__)

# 扩展名 -> (魔数前缀, MIME)。魔数用于防伪造扩展名。
_MAGIC = {
    'jpg': (b'\xff\xd8\xff', 'image/jpeg'),
    'jpeg': (b'\xff\xd8\xff', 'image/jpeg'),
    'png': (b'\x89PNG\r\n\x1a\n', 'image/png'),
    'gif': (b'GIF8', 'image/gif'),
    'bmp': (b'BM', 'image/bmp'),
    'webp': (b'RIFF', 'image/webp'),
    'pdf': (b'%PDF', 'application/pdf'),
}


def _remove_file(stored_name):
    """删除磁盘文件, 失败只记日志不阻断业务"""
    try:
        os.remove(os.path.join(Config.ATTACHMENT_FOLDER, stored_name))
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception(f'附件文件删除失败: {stored_name}')


class AttachmentService:
    @staticmethod
    def _validate(file):
        """校验上传文件 (扩展名 + 魔数 + 大小), 通过返回 error 消息或 None"""
        if not file or not file.filename:
            return '请选择文件'

        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in Config.ATTACHMENT_EXTENSIONS:
            return f'只允许上传 {", ".join(sorted(Config.ATTACHMENT_EXTENSIONS))} 格式'

        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        if size == 0:
            return '文件内容为空'
        if size > Config.ATTACHMENT_MAX_SIZE:
            return f'单个文件不能超过 {Config.ATTACHMENT_MAX_SIZE // 1024 // 1024}MB'

        header = file.read(12)
        file.seek(0)
        if not header.startswith(_MAGIC[ext][0]):
            return '文件内容与扩展名不匹配'
        if ext == 'webp' and header[8:12] != b'WEBP':
            return '文件内容与扩展名不匹配'
        return None

    @staticmethod
    def get_attachments(biz_type, biz_id):
        """按单据查附件, 主表附件 (row_key 为 NULL) 在前"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT a.id, a.biz_type, a.biz_id, a.row_key, a.file_name,
                       a.file_size, a.mime_type, a.created_at,
                       u.username as uploaded_by_name
                FROM attachment a
                LEFT JOIN user u ON a.uploaded_by = u.id
                WHERE a.biz_type = ? AND a.biz_id = ?
                ORDER BY a.row_key IS NOT NULL, a.id
                """,
                (biz_type, biz_id)
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_attachment(attachment_id):
        """查单个附件 (下载用, 需要 stored_name)"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, biz_type, biz_id, row_key, file_name, stored_name,
                       file_size, mime_type
                FROM attachment WHERE id = ?
                """,
                (attachment_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def _count(cursor, biz_type, biz_id, row_key):
        if row_key:
            cursor.execute(
                "SELECT COUNT(*) FROM attachment WHERE biz_type = ? AND biz_id = ? AND row_key = ?",
                (biz_type, biz_id, row_key)
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) FROM attachment WHERE biz_type = ? AND biz_id = ? AND row_key IS NULL",
                (biz_type, biz_id)
            )
        return cursor.fetchone()[0]

    @staticmethod
    def save_attachment(biz_type, biz_id, file, row_key=None, uploaded_by=None):
        """校验并保存附件。先落盘再写库, 写库失败则删掉文件避免孤儿。"""
        error = AttachmentService._validate(file)
        if error:
            raise ValueError(error)

        ext = file.filename.rsplit('.', 1)[-1].lower()
        stored_name = f'{uuid.uuid4().hex}.{ext}'
        limit = Config.ATTACHMENT_MAX_PER_ITEM if row_key else Config.ATTACHMENT_MAX_PER_ORDER

        os.makedirs(Config.ATTACHMENT_FOLDER, exist_ok=True)
        stored_path = os.path.join(Config.ATTACHMENT_FOLDER, stored_name)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            if AttachmentService._count(cursor, biz_type, biz_id, row_key) >= limit:
                raise ValueError(f'附件数量已达上限 ({limit} 个)')

            file.save(stored_path)
            try:
                cursor.execute(
                    """
                    INSERT INTO attachment
                        (biz_type, biz_id, row_key, file_name, stored_name, file_size, mime_type, uploaded_by, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
                    """,
                    (biz_type, biz_id, row_key, file.filename, stored_name,
                     os.path.getsize(stored_path), _MAGIC[ext][1], uploaded_by)
                )
                conn.commit()
                attachment_id = cursor.lastrowid
            except Exception:
                logger.exception('附件入库失败')
                _remove_file(stored_name)
                raise

        return {'id': attachment_id, 'file_name': file.filename, 'row_key': row_key}

    @staticmethod
    def delete_attachment(attachment_id):
        """删除附件 (记录 + 磁盘文件); 返回 bool"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT stored_name FROM attachment WHERE id = ?", (attachment_id,))
            row = cursor.fetchone()
            if not row:
                return False
            cursor.execute("DELETE FROM attachment WHERE id = ?", (attachment_id,))
            conn.commit()

        _remove_file(row['stored_name'])
        return True

    @staticmethod
    def delete_by_row_keys(biz_type, biz_id, keep_row_keys):
        """清理明细行已删除的附件: 该单据下 row_key 不在 keep 集合里的一并删除"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, stored_name, row_key FROM attachment WHERE biz_type = ? AND biz_id = ? AND row_key IS NOT NULL",
                (biz_type, biz_id)
            )
            orphans = [r for r in cursor.fetchall() if r['row_key'] not in keep_row_keys]
            if orphans:
                cursor.executemany(
                    "DELETE FROM attachment WHERE id = ?", [(r['id'],) for r in orphans]
                )
                conn.commit()

        for o in orphans:
            _remove_file(o['stored_name'])

    @staticmethod
    def delete_by_biz(biz_type, biz_id):
        """删除单据时级联清理其全部附件"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT stored_name FROM attachment WHERE biz_type = ? AND biz_id = ?",
                (biz_type, biz_id)
            )
            stored_names = [r['stored_name'] for r in cursor.fetchall()]
            cursor.execute(
                "DELETE FROM attachment WHERE biz_type = ? AND biz_id = ?", (biz_type, biz_id)
            )
            conn.commit()

        for name in stored_names:
            _remove_file(name)
