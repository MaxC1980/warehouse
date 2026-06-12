import logging
from flask import Blueprint, request, jsonify
from config import Config
from services.material_service import MaterialService
from services.inventory_service import InventoryService

logger = logging.getLogger(__name__)
from utils.excel_utils import import_from_excel
from utils.decorators import require_permission

import_bp = Blueprint('import', __name__)

def _validate_file(file):
    """校验上传文件"""
    if not file or file.filename == '':
        return '请选择文件'
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in Config.ALLOWED_EXTENSIONS:
        return f'只允许上传 {", ".join(Config.ALLOWED_EXTENSIONS)} 格式'
    # 魔数校验
    header = file.read(8)
    file.seek(0)
    if ext == 'xlsx' and header[:2] != b'PK':
        return '文件内容与扩展名不匹配'
    if ext == 'xls' and header[:4] != b'\xd0\xcf\x11\xe0':
        return '文件内容与扩展名不匹配'
    return None

@import_bp.route('/import/materials', methods=['POST'])
@require_permission('material', 'edit')
def import_materials():
    file = request.files.get('file')
    error = _validate_file(file)
    if error:
        return jsonify({'error': error}), 400

    try:
        # Read Excel file
        data = import_from_excel(file)

        if not data:
            return jsonify({'error': '文件为空或无数据行'}), 400

        # Import materials
        results = MaterialService.import_materials(data)

        return jsonify({
            'message': f'导入完成，成功 {results["success"]} 条，失败 {results["failed"]} 条',
            'results': results
        })
    except Exception as e:
        logger.exception('Excel导入失败')
        return jsonify({'error': '服务器内部错误'}), 500

@import_bp.route('/import/inventory', methods=['POST'])
@require_permission('material', 'edit')
def import_inventory():
    file = request.files.get('file')
    error = _validate_file(file)
    if error:
        return jsonify({'error': error}), 400

    try:
        # Read Excel file
        data = import_from_excel(file)

        if not data:
            return jsonify({'error': '文件为空或无数据行'}), 400

        # Import inventory
        results = InventoryService.import_inventory(data)

        return jsonify({
            'message': f'导入完成，成功 {results["success"]} 条，失败 {results["failed"]} 条',
            'results': results
        })
    except Exception as e:
        logger.exception('Excel导入失败')
        return jsonify({'error': '服务器内部错误'}), 500

@import_bp.route('/import/categories', methods=['POST'])
@require_permission('material', 'edit')
def import_categories():
    file = request.files.get('file')
    error = _validate_file(file)
    if error:
        return jsonify({'error': error}), 400

    try:
        # Read Excel file with header row
        data = import_from_excel(file)

        if not data:
            return jsonify({'error': '文件为空'}), 400

        # Import categories
        results = MaterialService.import_categories(data)

        return jsonify({
            'message': f'导入完成，成功 {results["success"]} 条，失败 {results["failed"]} 条',
            'errors': results['errors'][:10] if results['errors'] else [],
            'total_errors': len(results['errors'])
        })
    except Exception as e:
        logger.exception('Excel导入失败')
        return jsonify({'error': '服务器内部错误'}), 500

@import_bp.route('/import/minor-categories', methods=['POST'])
@require_permission('material', 'edit')
def import_minor_categories():
    file = request.files.get('file')
    error = _validate_file(file)
    if error:
        return jsonify({'error': error}), 400

    try:
        # Read Excel file with header row
        data = import_from_excel(file)

        if not data:
            return jsonify({'error': '文件为空'}), 400

        # Import minor categories
        results = MaterialService.import_minor_categories(data)

        return jsonify({
            'message': f'导入完成，成功 {results["success"]} 条，失败 {results["failed"]} 条',
            'errors': results['errors'][:10] if results['errors'] else [],
            'total_errors': len(results['errors'])
        })
    except Exception as e:
        logger.exception('Excel导入失败')
        return jsonify({'error': '服务器内部错误'}), 500
