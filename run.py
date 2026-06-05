"""
开发环境入口
用法: python run.py
"""
import sys
sys.dont_write_bytecode = True

from config import DevelopmentConfig
from create_app import create_app

app = create_app(DevelopmentConfig)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=app.config['PORT'])
