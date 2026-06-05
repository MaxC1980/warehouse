"""
生产环境入口
用法:
    python app.py
    gunicorn -w 4 -b 0.0.0.0:5000 app:app
"""
import sys
sys.dont_write_bytecode = True

from config import ProductionConfig
from create_app import create_app

app = create_app(ProductionConfig)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=app.config['PORT'])
