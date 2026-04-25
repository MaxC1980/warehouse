from flask import Blueprint, request, jsonify, make_response
from services.report_service import ReportService
from utils.excel_utils import export_to_excel

report_bp = Blueprint('report', __name__)

@report_bp.route('/reports/inventory', methods=['GET'])
def get_inventory_report():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    keyword = request.args.get('keyword')
    major_category = request.args.get('major_category')
    minor_category = request.args.get('minor_category')

    report_data, total = ReportService.get_inventory_report(
        page=page,
        per_page=per_page,
        keyword=keyword,
        major_category=major_category,
        minor_category=minor_category
    )
    return jsonify({
        'items': report_data,
        'total': total,
        'page': page,
        'per_page': per_page
    })

@report_bp.route('/reports/in-detail', methods=['GET'])
def get_in_detail_report():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    material_id = request.args.get('material_id', type=int)

    report_data, total = ReportService.get_in_detail_report(
        page=page,
        per_page=per_page,
        date_from=date_from,
        date_to=date_to,
        material_id=material_id
    )
    return jsonify({
        'items': report_data,
        'total': total,
        'page': page,
        'per_page': per_page
    })

@report_bp.route('/reports/out-detail', methods=['GET'])
def get_out_detail_report():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    material_id = request.args.get('material_id', type=int)

    report_data, total = ReportService.get_out_detail_report(
        page=page,
        per_page=per_page,
        date_from=date_from,
        date_to=date_to,
        material_id=material_id
    )
    return jsonify({
        'items': report_data,
        'total': total,
        'page': page,
        'per_page': per_page
    })

@report_bp.route('/reports/summary', methods=['GET'])
def get_summary_report():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    report_data = ReportService.get_summary_report(
        date_from=date_from,
        date_to=date_to
    )
    return jsonify(report_data)

@report_bp.route('/reports/inventory/export', methods=['GET'])
def export_inventory_report():
    keyword = request.args.get('keyword')
    major_category = request.args.get('major_category')
    minor_category = request.args.get('minor_category')

    report_data, _ = ReportService.get_inventory_report(
        page=1,
        per_page=10000,
        keyword=keyword,
        major_category=major_category,
        minor_category=minor_category
    )

    columns = ['物料编码', '物料名称', '规格型号', '单位', '当前库存', '安全库存', '状态']
    data = [[
        r['material_code'],
        r['material_name'],
        r['spec'],
        r['unit'],
        r['quantity'],
        r['safety_stock'],
        r['status']
    ] for r in report_data]

    excel_data = export_to_excel(columns, data, '库存报表')

    response = make_response(excel_data)
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = 'attachment; filename=inventory_report.xlsx'
    return response

@report_bp.route('/reports/in-detail/export', methods=['GET'])
def export_in_detail_report():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    material_id = request.args.get('material_id', type=int)

    report_data, _ = ReportService.get_in_detail_report(
        page=1,
        per_page=10000,
        date_from=date_from,
        date_to=date_to,
        material_id=material_id
    )

    columns = ['入库单号', '入库日期', '供应商', '物料编码', '物料名称', '批次号', '数量', '单价', '金额', '操作员']
    data = [[
        r['order_no'],
        r['created_at'],
        r['supplier_name'],
        r['material_code'],
        r['material_name'],
        r['batch_no'],
        r['quantity'],
        r['unit_price'],
        r['amount'],
        r['operator']
    ] for r in report_data]

    excel_data = export_to_excel(columns, data, '入库明细报表')

    response = make_response(excel_data)
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = 'attachment; filename=in_detail_report.xlsx'
    return response

@report_bp.route('/reports/out-detail/export', methods=['GET'])
def export_out_detail_report():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    material_id = request.args.get('material_id', type=int)

    report_data, _ = ReportService.get_out_detail_report(
        page=1,
        per_page=10000,
        date_from=date_from,
        date_to=date_to,
        material_id=material_id
    )

    columns = ['出库单号', '出库日期', '物料编码', '物料名称', '批次号', '数量', '单价', '金额', '操作员']
    data = [[
        r['order_no'],
        r['created_at'],
        r['material_code'],
        r['material_name'],
        r['batch_no'],
        r['actual_quantity'],
        r['unit_price'],
        r['amount'],
        r['operator']
    ] for r in report_data]

    excel_data = export_to_excel(columns, data, '出库明细报表')

    response = make_response(excel_data)
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = 'attachment; filename=out_detail_report.xlsx'
    return response
