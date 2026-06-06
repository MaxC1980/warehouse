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
