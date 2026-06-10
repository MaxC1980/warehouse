import logging
from flask import Blueprint, request, jsonify
from services.material_service import MaterialService
from services.inventory_service import InventoryService

logger = logging.getLogger(__name__)
from utils.excel_utils import import_from_excel
from utils.decorators import require_permission

import_bp = Blueprint('import', __name__)

@import_bp.route('/import/materials', methods=['POST'])
@require_permission('material', 'edit')
def import_materials():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        # Read Excel file
        data = import_from_excel(file)

        if not data:
            return jsonify({'error': 'Empty file or no data rows'}), 400

        # Import materials
        results = MaterialService.import_materials(data)

        return jsonify({
            'message': f'Import completed. {results["success"]} succeeded, {results["failed"]} failed.',
            'results': results
        })
    except Exception as e:
        logger.exception('Excel导入失败')
        return jsonify({'error': '服务器内部错误'}), 500

@import_bp.route('/import/inventory', methods=['POST'])
@require_permission('material', 'edit')
def import_inventory():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        # Read Excel file
        data = import_from_excel(file)

        if not data:
            return jsonify({'error': 'Empty file or no data rows'}), 400

        # Import inventory
        results = InventoryService.import_inventory(data)

        return jsonify({
            'message': f'Import completed. {results["success"]} succeeded, {results["failed"]} failed.',
            'results': results
        })
    except Exception as e:
        logger.exception('Excel导入失败')
        return jsonify({'error': '服务器内部错误'}), 500

@import_bp.route('/import/categories', methods=['POST'])
@require_permission('material', 'edit')
def import_categories():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        # Read Excel file with header row
        data = import_from_excel(file)

        if not data:
            return jsonify({'error': 'Empty file'}), 400

        # Import categories
        results = MaterialService.import_categories(data)

        return jsonify({
            'message': f'Import completed. {results["success"]} succeeded, {results["failed"]} failed.',
            'errors': results['errors'][:10] if results['errors'] else [],
            'total_errors': len(results['errors'])
        })
    except Exception as e:
        logger.exception('Excel导入失败')
        return jsonify({'error': '服务器内部错误'}), 500

@import_bp.route('/import/minor-categories', methods=['POST'])
@require_permission('material', 'edit')
def import_minor_categories():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        # Read Excel file with header row
        data = import_from_excel(file)

        if not data:
            return jsonify({'error': 'Empty file'}), 400

        # Import minor categories
        results = MaterialService.import_minor_categories(data)

        return jsonify({
            'message': f'Import completed. {results["success"]} succeeded, {results["failed"]} failed.',
            'errors': results['errors'][:10] if results['errors'] else [],
            'total_errors': len(results['errors'])
        })
    except Exception as e:
        logger.exception('Excel导入失败')
        return jsonify({'error': '服务器内部错误'}), 500
