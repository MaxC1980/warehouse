from database import get_db_connection
from datetime import datetime

class MaterialService:
    # Keywords that indicate reusable materials (需要称重退库)
    REUSABLE_KEYWORDS = ['胶水', '锡膏']

    @staticmethod
    def _is_reusable_material(name):
        """根据物料名称自动判断是否为可回用物料"""
        if not name:
            return 0
        name_lower = name.lower()
        for keyword in MaterialService.REUSABLE_KEYWORDS:
            if keyword.lower() in name_lower:
                return 1
        return 0

    @staticmethod
    def get_all_categories():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM material_category ORDER BY code"
        )
        categories = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return categories

    @staticmethod
    def create_category(code, name, parent_code=None, level=1):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO material_category (code, name, parent_code, level) VALUES (?, ?, ?, ?)",
                (code, name, parent_code, level)
            )
            conn.commit()
            category_id = cursor.lastrowid
            conn.close()
            return {
                'id': category_id,
                'code': code,
                'name': name,
                'parent_code': parent_code,
                'level': level
            }
        except Exception as e:
            conn.close()
            raise e

    @staticmethod
    def update_category(category_id, code=None, name=None):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            updates = []
            params = []
            if code:
                updates.append("code = ?")
                params.append(code)
            if name:
                updates.append("name = ?")
                params.append(name)

            if updates:
                params.append(category_id)
                cursor.execute(
                    f"UPDATE material_category SET {', '.join(updates)} WHERE id = ?",
                    params
                )
                conn.commit()

            cursor.execute("SELECT * FROM material_category WHERE id = ?", (category_id,))
            category = cursor.fetchone()
            conn.close()

            if category:
                return dict(category)
            return None
        except Exception as e:
            conn.close()
            raise e

    @staticmethod
    def delete_category(category_id):
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if category has children
        cursor.execute(
            "SELECT COUNT(*) as count FROM material_category WHERE parent_code = (SELECT code FROM material_category WHERE id = ?)",
            (category_id,)
        )
        if cursor.fetchone()['count'] > 0:
            conn.close()
            return False

        cursor.execute("DELETE FROM material_category WHERE id = ?", (category_id,))
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def get_materials(page=1, per_page=20, category_code=None, keyword=None,
                      major_category=None, minor_category=None,
                      material_code=None, material_name=None, material_spec=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        offset = (page - 1) * per_page

        where_clauses = []
        params = []

        if category_code:
            # If category_code is 2 digits (major category), match all sub-categories
            if len(category_code) == 2:
                where_clauses.append("m.category_code LIKE ?")
                params.append(category_code + '%')
            else:
                where_clauses.append("m.category_code = ?")
                params.append(category_code)

        if major_category:
            # Match major category (first 2 digits of category_code)
            where_clauses.append("m.category_code LIKE ?")
            params.append(major_category + '%')

        if minor_category:
            # Match specific minor category
            where_clauses.append("m.category_code = ?")
            params.append(minor_category)

        if material_code:
            where_clauses.append("m.code LIKE ?")
            params.append(material_code + '%')

        if material_name:
            where_clauses.append("m.name LIKE ?")
            params.append(f'%{material_name}%')

        if material_spec:
            where_clauses.append("m.spec LIKE ?")
            params.append(f'%{material_spec}%')

        if keyword:
            where_clauses.append("(m.code LIKE ? OR m.name LIKE ? OR m.spec LIKE ?)")
            params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Get total count
        cursor.execute(
            f"SELECT COUNT(*) as count FROM material m {where_sql}",
            params
        )
        total = cursor.fetchone()['count']

        # Get materials
        cursor.execute(
            f"""
            SELECT m.*, c.name as category_name
            FROM material m
            LEFT JOIN material_category c ON m.category_code = c.code
            {where_sql}
            ORDER BY m.code
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset]
        )
        materials = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return materials, total

    @staticmethod
    def get_material_by_id(material_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT m.*, c.name as category_name
            FROM material m
            LEFT JOIN material_category c ON m.category_code = c.code
            WHERE m.id = ?
            """,
            (material_id,)
        )
        material = cursor.fetchone()
        conn.close()

        if material:
            return dict(material)
        return None

    @staticmethod
    def create_material(name, spec=None, unit='个', category_code=None, manufacturer=None, storage_condition='常温', shelf_life=None, remark=None, is_reusable=None, safety_stock=0):
        conn = get_db_connection()
        cursor = conn.cursor()

        # Auto-detect is_reusable based on material name
        if is_reusable is None:
            is_reusable = MaterialService._is_reusable_material(name)

        # Generate code: category_code(4 digits) + sequence(4 digits)
        if category_code:
            cursor.execute(
                "SELECT code FROM material WHERE category_code = ? ORDER BY code DESC LIMIT 1",
                (category_code,)
            )
            last_code = cursor.fetchone()
            if last_code:
                seq = int(last_code['code'][-4:]) + 1
            else:
                seq = 1
            code = category_code + str(seq).zfill(4)
        else:
            cursor.execute("SELECT code FROM material ORDER BY code DESC LIMIT 1")
            last_code = cursor.fetchone()
            if last_code:
                seq = int(last_code['code']) + 1
            else:
                seq = 1
            code = str(seq).zfill(8)

        cursor.execute(
            """
            INSERT INTO material (code, name, spec, unit, category_code, manufacturer, storage_condition, shelf_life, remark, is_reusable, safety_stock)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (code, name, spec, unit, category_code, manufacturer, storage_condition, shelf_life, remark, is_reusable, safety_stock)
        )
        conn.commit()
        material_id = cursor.lastrowid
        conn.close()

        return MaterialService.get_material_by_id(material_id)

    @staticmethod
    def update_material(material_id, name=None, spec=None, unit=None, category_code=None, manufacturer=None, storage_condition=None, shelf_life=None, remark=None, is_reusable=None, safety_stock=None):
        conn = get_db_connection()
        cursor = conn.cursor()

        updates = []
        params = []

        if name:
            updates.append("name = ?")
            params.append(name)
        if spec is not None:
            updates.append("spec = ?")
            params.append(spec)
        if unit:
            updates.append("unit = ?")
            params.append(unit)
        if category_code:
            updates.append("category_code = ?")
            params.append(category_code)
        if manufacturer is not None:
            updates.append("manufacturer = ?")
            params.append(manufacturer)
        if storage_condition is not None:
            updates.append("storage_condition = ?")
            params.append(storage_condition)
        if shelf_life is not None:
            updates.append("shelf_life = ?")
            params.append(shelf_life)
        if remark is not None:
            updates.append("remark = ?")
            params.append(remark)
        if is_reusable is not None:
            updates.append("is_reusable = ?")
            params.append(is_reusable)
        if safety_stock is not None:
            updates.append("safety_stock = ?")
            params.append(safety_stock)

        if updates:
            params.append(material_id)
            cursor.execute(
                f"UPDATE material SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()

        conn.close()
        return MaterialService.get_material_by_id(material_id)

    @staticmethod
    def delete_material(material_id):
        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查是否有入库明细
        cursor.execute("SELECT COUNT(*) FROM in_order_item WHERE material_id = ?", (material_id,))
        if cursor.fetchone()[0] > 0:
            conn.close()
            return False, '该物料已有入库记录，不能删除'

        # 检查是否有出库明细
        cursor.execute("SELECT COUNT(*) FROM out_order_item WHERE material_id = ?", (material_id,))
        if cursor.fetchone()[0] > 0:
            conn.close()
            return False, '该物料已有出库记录，不能删除'

        # 检查是否有库存
        cursor.execute("SELECT SUM(quantity) FROM inventory WHERE material_id = ?", (material_id,))
        result = cursor.fetchone()[0]
        if result and result > 0:
            conn.close()
            return False, '该物料还有库存，不能删除'

        cursor.execute("DELETE FROM material WHERE id = ?", (material_id,))
        conn.commit()
        conn.close()
        return True, '删除成功'

    @staticmethod
    def import_materials(data):
        """Import materials from list of dictionaries"""
        conn = get_db_connection()
        cursor = conn.cursor()
        success = 0
        failed = 0
        errors = []

        for idx, row in enumerate(data):
            try:
                code = row.get('code')
                name = row.get('name')
                if not name:
                    errors.append(f"Row {idx + 2}: Missing name")
                    failed += 1
                    continue

                if not code:
                    errors.append(f"Row {idx + 2}: Missing code")
                    failed += 1
                    continue

                spec = row.get('spec')
                unit = row.get('unit', '个')

                # Auto-match category by first 4 digits of code
                category_code = row.get('category_code')
                if not category_code and len(str(code)) >= 4:
                    potential_category = str(code)[:4]
                    cursor.execute("SELECT code FROM material_category WHERE code = ?", (potential_category,))
                    if cursor.fetchone():
                        category_code = potential_category

                manufacturer = row.get('manufacturer')
                storage_condition = row.get('storage_condition', '常温')
                shelf_life = row.get('shelf_life')
                remark = row.get('remark')

                # Auto-detect is_reusable based on material name
                is_reusable = MaterialService._is_reusable_material(name)

                # Use code from Excel directly
                cursor.execute(
                    """
                    INSERT INTO material (code, name, spec, unit, category_code, manufacturer, storage_condition, shelf_life, remark, is_reusable)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (code, name, spec, unit, category_code, manufacturer, storage_condition, shelf_life, remark, is_reusable)
                )
                conn.commit()
                success += 1
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                failed += 1

        conn.close()
        return {'success': success, 'failed': failed, 'errors': errors}

    @staticmethod
    def import_categories(data):
        """Import categories (major) from list of dictionaries"""
        conn = get_db_connection()
        cursor = conn.cursor()
        success = 0
        failed = 0
        errors = []

        for idx, row in enumerate(data):
            try:
                # Support both position-based (col1, col2) and header-based keys
                raw_code = row.get('col1') or row.get('代码') or row.get('code') or ''
                code = str(int(raw_code)).strip() if raw_code else ''
                name = str(row.get('col2') or row.get('名称') or row.get('name') or '').strip()

                if not code or not name:
                    errors.append(f"Row {idx + 1}: Missing code or name")
                    failed += 1
                    continue

                if len(code) != 2:
                    errors.append(f"Row {idx + 1}: Code '{code}' must be 2 digits")
                    failed += 1
                    continue

                # Check if code already exists
                cursor.execute("SELECT id FROM material_category WHERE code = ?", (code,))
                if cursor.fetchone():
                    errors.append(f"Row {idx + 1}: Code '{code}' already exists")
                    failed += 1
                    continue

                cursor.execute(
                    "INSERT INTO material_category (code, name, parent_code, level) VALUES (?, ?, ?, ?)",
                    (code, name, None, 1)
                )
                conn.commit()
                success += 1
            except Exception as e:
                errors.append(f"Row {idx + 1}: {str(e)}")
                failed += 1

        conn.close()
        return {'success': success, 'failed': failed, 'errors': errors}

    @staticmethod
    def import_minor_categories(data):
        """Import minor categories from list of dictionaries with header row"""
        conn = get_db_connection()
        cursor = conn.cursor()
        success = 0
        failed = 0
        errors = []

        for idx, row in enumerate(data):
            try:
                # Support various column name formats: 编码/代码/code/col1
                raw_code = row.get('编码') or row.get('代码') or row.get('code') or row.get('col1') or ''
                name = row.get('名称') or row.get('name') or row.get('col2') or ''

                if not raw_code or not name:
                    errors.append(f"Row {idx + 2}: Missing code or name")
                    failed += 1
                    continue

                # Convert to string, preserve leading zeros
                code_str = str(raw_code).strip()

                # Extract major code from first 2 digits
                if len(code_str) < 2:
                    errors.append(f"Row {idx + 2}: Code '{code_str}' is invalid")
                    failed += 1
                    continue

                major_code = code_str[:2]

                # Find parent category
                cursor.execute("SELECT id FROM material_category WHERE code = ? AND level = 1", (major_code,))
                parent = cursor.fetchone()
                if not parent:
                    errors.append(f"Row {idx + 2}: Major category '{major_code}' not found")
                    failed += 1
                    continue

                # Check if code already exists
                cursor.execute("SELECT id FROM material_category WHERE code = ?", (code_str,))
                if cursor.fetchone():
                    errors.append(f"Row {idx + 2}: Code '{code_str}' already exists")
                    failed += 1
                    continue

                cursor.execute(
                    "INSERT INTO material_category (code, name, parent_code, level) VALUES (?, ?, ?, ?)",
                    (code_str, name, major_code, 2)
                )
                conn.commit()
                success += 1
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                failed += 1

        conn.close()
        return {'success': success, 'failed': failed, 'errors': errors}
