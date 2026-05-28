from database import get_db_connection

class MaterialService:
    REUSABLE_KEYWORDS = ['胶水', '锡膏']

    @staticmethod
    def _is_reusable_material(name):
        if not name:
            return 0
        name_lower = name.lower()
        for keyword in MaterialService.REUSABLE_KEYWORDS:
            if keyword.lower() in name_lower:
                return 1
        return 0

    @staticmethod
    def get_all_categories():
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, code, name, parent_code, level FROM material_category ORDER BY code"
            )
            categories = [dict(row) for row in cursor.fetchall()]

            material_codes = None
            for cat in categories:
                if cat['level'] == 1:
                    cat['has_materials'] = any(c['parent_code'] == cat['code'] for c in categories if c['level'] == 2)
                else:
                    if material_codes is None:
                        cursor.execute("SELECT DISTINCT category_code FROM material")
                        material_codes = {row['category_code'] for row in cursor.fetchall()}
                    cat['has_materials'] = cat['code'] in material_codes

        return categories

    @staticmethod
    def create_category(code, name, parent_code=None, level=1):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO material_category (code, name, parent_code, level) VALUES (?, ?, ?, ?)",
                (code, name, parent_code, level)
            )
            conn.commit()
            category_id = cursor.lastrowid

        return {
            'id': category_id,
            'code': code,
            'name': name,
            'parent_code': parent_code,
            'level': level
        }

    @staticmethod
    def update_category(category_id, code=None, name=None, parent_code=None):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT code, level, parent_code FROM material_category WHERE id = ?", (category_id,))
            cat = cursor.fetchone()
            if not cat:
                return False, None

            code_changed = code and code != cat['code']
            parent_changed = parent_code is not None and parent_code != cat['parent_code']
            if code_changed or parent_changed:
                if cat['level'] == 1:
                    cursor.execute("SELECT COUNT(*) as count FROM material_category WHERE parent_code = ?", (cat['code'],))
                else:
                    cursor.execute("SELECT COUNT(*) as count FROM material WHERE category_code = ?", (cat['code'],))
                if cursor.fetchone()['count'] > 0:
                    return False, 'has_materials'

            updates = []
            params = []
            if code:
                updates.append("code = ?")
                params.append(code)
            if name:
                updates.append("name = ?")
                params.append(name)
            if parent_code is not None:
                updates.append("parent_code = ?")
                params.append(parent_code)

            if updates:
                params.append(category_id)
                cursor.execute(
                    f"UPDATE material_category SET {', '.join(updates)} WHERE id = ?",
                    params
                )
                conn.commit()

            cursor.execute("SELECT id, code, name, parent_code, level FROM material_category WHERE id = ?", (category_id,))
            category = cursor.fetchone()

            if category:
                return True, dict(category)
            return False, None

    @staticmethod
    def delete_category(category_id):
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT code, level FROM material_category WHERE id = ?", (category_id,))
            cat = cursor.fetchone()
            if not cat:
                return 'not_found'

            cursor.execute(
                "SELECT COUNT(*) as count FROM material_category WHERE parent_code = ?",
                (cat['code'],)
            )
            if cursor.fetchone()['count'] > 0:
                return 'has_children'

            if cat['level'] == 1:
                cursor.execute("SELECT COUNT(*) as count FROM material WHERE category_code LIKE ?", (cat['code'] + '%',))
            else:
                cursor.execute("SELECT COUNT(*) as count FROM material WHERE category_code = ?", (cat['code'],))
            if cursor.fetchone()['count'] > 0:
                return 'has_materials'

            cursor.execute("DELETE FROM material_category WHERE id = ?", (category_id,))
            conn.commit()

        return 'ok'

    @staticmethod
    def get_materials(page=1, per_page=20, category_code=None, keyword=None,
                      major_category=None, minor_category=None):
        with get_db_connection() as conn:
            cursor = conn.cursor()

            offset = (page - 1) * per_page

            where_clauses = []
            params = []

            if category_code:
                if len(category_code) == 2:
                    where_clauses.append("m.category_code LIKE ?")
                    params.append(category_code + '%')
                else:
                    where_clauses.append("m.category_code = ?")
                    params.append(category_code)

            if major_category:
                where_clauses.append("m.category_code LIKE ?")
                params.append(major_category + '%')

            if minor_category:
                where_clauses.append("m.category_code = ?")
                params.append(minor_category)

            if keyword:
                where_clauses.append("(m.code LIKE ? OR m.name LIKE ? OR m.spec LIKE ? OR m.manufacturer LIKE ?)")
                params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])

            where_sql = ""
            if where_clauses:
                where_sql = "WHERE " + " AND ".join(where_clauses)

            cursor.execute(
                f"SELECT COUNT(*) as count FROM material m {where_sql}",
                params
            )
            total = cursor.fetchone()['count']

            cursor.execute(
                f"""
                SELECT m.id, m.code, m.name, m.spec, m.unit, m.category_code, m.manufacturer, m.storage_condition, m.shelf_life, m.remark, m.is_reusable, m.safety_stock, m.created_at, c.name as category_name
                FROM material m
                LEFT JOIN material_category c ON m.category_code = c.code
                {where_sql}
                ORDER BY m.code
                LIMIT ? OFFSET ?
                """,
                params + [per_page, offset]
            )
            materials = [dict(row) for row in cursor.fetchall()]

        return materials, total

    @staticmethod
    def get_material_by_id(material_id):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT m.id, m.code, m.name, m.spec, m.unit, m.category_code, m.manufacturer, m.storage_condition, m.shelf_life, m.remark, m.is_reusable, m.safety_stock, m.created_at, c.name as category_name
                FROM material m
                LEFT JOIN material_category c ON m.category_code = c.code
                WHERE m.id = ?
                """,
                (material_id,)
            )
            material = cursor.fetchone()
            if not material:
                return None

            result = dict(material)
            cursor.execute("SELECT COUNT(*) FROM in_order_item WHERE material_id = ?", (material_id,))
            has_in = cursor.fetchone()[0] > 0
            cursor.execute("SELECT COUNT(*) FROM out_order_item WHERE material_id = ?", (material_id,))
            has_out = cursor.fetchone()[0] > 0
            cursor.execute("SELECT COUNT(*) FROM inventory WHERE material_id = ?", (material_id,))
            has_inv = cursor.fetchone()[0] > 0
            result['has_references'] = has_in or has_out or has_inv

        return result

    @staticmethod
    def create_material(name, spec=None, unit='个', category_code=None, manufacturer=None, storage_condition='常温', shelf_life=None, remark=None, is_reusable=None, safety_stock=0):
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if is_reusable is None:
                is_reusable = MaterialService._is_reusable_material(name)

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

        return MaterialService.get_material_by_id(material_id)

    @staticmethod
    def update_material(material_id, data):
        with get_db_connection() as conn:
            cursor = conn.cursor()

            updates = []
            params = []

            if 'name' in data:
                updates.append("name = ?")
                params.append(data['name'])
            if 'spec' in data:
                updates.append("spec = ?")
                params.append(data['spec'])
            if 'unit' in data:
                updates.append("unit = ?")
                params.append(data['unit'])
            if 'category_code' in data:
                updates.append("category_code = ?")
                params.append(data['category_code'])
            if 'manufacturer' in data:
                updates.append("manufacturer = ?")
                params.append(data['manufacturer'])
            if 'storage_condition' in data:
                updates.append("storage_condition = ?")
                params.append(data['storage_condition'])
            if 'shelf_life' in data:
                updates.append("shelf_life = ?")
                params.append(data['shelf_life'])
            if 'remark' in data:
                updates.append("remark = ?")
                params.append(data['remark'])
            if 'is_reusable' in data:
                updates.append("is_reusable = ?")
                params.append(data['is_reusable'])
            if 'safety_stock' in data:
                updates.append("safety_stock = ?")
                params.append(data['safety_stock'])

            if updates:
                params.append(material_id)
                cursor.execute(
                    f"UPDATE material SET {', '.join(updates)} WHERE id = ?",
                    params
                )
                conn.commit()

        return MaterialService.get_material_by_id(material_id)

    @staticmethod
    def delete_material(material_id):
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM in_order_item WHERE material_id = ?", (material_id,))
            if cursor.fetchone()[0] > 0:
                return False, '该物料已有入库记录，不能删除'

            cursor.execute("SELECT COUNT(*) FROM out_order_item WHERE material_id = ?", (material_id,))
            if cursor.fetchone()[0] > 0:
                return False, '该物料已有出库记录，不能删除'

            cursor.execute("SELECT COUNT(*) FROM inventory WHERE material_id = ?", (material_id,))
            if cursor.fetchone()[0] > 0:
                return False, '该物料已有库存记录，不能删除'

            cursor.execute("DELETE FROM material WHERE id = ?", (material_id,))
            conn.commit()

        return True, '删除成功'

    @staticmethod
    def import_materials(data):
        with get_db_connection() as conn:
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

                    is_reusable = MaterialService._is_reusable_material(name)

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

        return {'success': success, 'failed': failed, 'errors': errors}

    @staticmethod
    def import_categories(data):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            success = 0
            failed = 0
            errors = []

            for idx, row in enumerate(data):
                try:
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

        return {'success': success, 'failed': failed, 'errors': errors}

    @staticmethod
    def import_minor_categories(data):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            success = 0
            failed = 0
            errors = []

            for idx, row in enumerate(data):
                try:
                    raw_code = row.get('编码') or row.get('代码') or row.get('code') or row.get('col1') or ''
                    name = row.get('名称') or row.get('name') or row.get('col2') or ''

                    if not raw_code or not name:
                        errors.append(f"Row {idx + 2}: Missing code or name")
                        failed += 1
                        continue

                    code_str = str(raw_code).strip()

                    if len(code_str) < 2:
                        errors.append(f"Row {idx + 2}: Code '{code_str}' is invalid")
                        failed += 1
                        continue

                    major_code = code_str[:2]

                    cursor.execute("SELECT id FROM material_category WHERE code = ? AND level = 1", (major_code,))
                    parent = cursor.fetchone()
                    if not parent:
                        errors.append(f"Row {idx + 2}: Major category '{major_code}' not found")
                        failed += 1
                        continue

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

        return {'success': success, 'failed': failed, 'errors': errors}
