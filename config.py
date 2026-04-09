import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'warehouse-management-secret-key-2024'
    DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'db', 'warehouse.db')
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE_PATH}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Pagination
    PAGE_SIZE = 20

    # Upload settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

    # Default: debug off for safety
    DEBUG = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
