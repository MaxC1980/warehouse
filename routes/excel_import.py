from flask import Blueprint, request, jsonify
from services.material_service import MaterialService
from services.inventory_service import InventoryService
from utils.excel_utils import import_from_excel, import_from_excel_by_position

import_bp = Blueprint('import', __name__)

@import_bp.route('/import/materials', methods=['POST'])
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
        return jsonify({'error': str(e)}), 500

@import_bp.route('/import/inventory', methods=['POST'])
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
        return jsonify({'error': str(e)}), 500

@import_bp.route('/import/categories', methods=['POST'])
def import_categories():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        # Read Excel file - no header row, directly use column positions
        data = import_from_excel_by_position(file, 2)  # 2 columns: code, name

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
        return jsonify({'error': str(e)}), 500

@import_bp.route('/import/minor-categories', methods=['POST'])
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
        return jsonify({'error': str(e)}), 500
