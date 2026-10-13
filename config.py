import os
import secrets

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'db', 'warehouse.db')

    # Pagination
    PAGE_SIZE = 20

    # Upload settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB

    # 单据附件 (图片/PDF)。不放行 svg: 可内嵌脚本触发 XSS
    ATTACHMENT_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads', 'attachments')
    ATTACHMENT_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'pdf'}
    ATTACHMENT_MAX_SIZE = 5 * 1024 * 1024  # 单文件 5MB
    ATTACHMENT_MAX_PER_ORDER = 10  # 主表附件上限
    ATTACHMENT_MAX_PER_ITEM = 5    # 单条明细附件上限

    # Default: debug off for safety
    DEBUG = False

    # Server port
    PORT = 5000


class DevelopmentConfig(Config):
    DEBUG = True
    PORT = 5001


class ProductionConfig(Config):
    DEBUG = False
    PORT = 5000
