"""产品与 BOM 业务层: CRUD + 缺料计算 + 最大可生产数

库存按物料聚合, 排除已过期批次。
替代物料 (bom_substitute) 库存合并计入主物料的可用量, 用于缺料与最大可生产数计算。
BOM 单层, qty_per_unit 4 位小数 (支持极小用量)。
"""
import math
from database import get_db_connection
from utils.sql import escape_like, build_like_clause, build_update_sql

PRODUCT_UPDATE_FIELDS = ['name', 'spec', 'unit', 'remark', 'disabled']


class ProductService:

    @staticmethod
    def get_products(page=1, per_page=20, keyword=None, active_only=False):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            offset = (page - 1) * per_page
            where_clauses = []
            params = []
            if keyword:
                where_clauses.append(build_like_clause(['p.code', 'p.name', 'p.spec'], keyword, params))
            if active_only:
                where_clauses.append("COALESCE(p.disabled, 0) = 0")
            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

            cursor.execute(
                f"SELECT COUNT(*) as count FROM product p {where_sql}",
                params
            )
            total = cursor.fetchone()['count']

            cursor.execute(
                f"""
                SELECT p.id, p.code, p.name, p.spec, p.unit, p.remark, p.disabled, p.created_at,
                       (SELECT COUNT(*) FROM bom WHERE product_id = p.id) as bom_count
                FROM product p
                {where_sql}
                ORDER BY p.code
                LIMIT ? OFFSET ?
                """,
                params + [per_page, offset]
            )
            items = [dict(row) for row in cursor.fetchall()]
        return items, total

    @staticmethod
    def get_active_products():
        """获取未禁用的产品列表 (用于下拉)"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, code, name, spec, unit FROM product WHERE COALESCE(disabled, 0) = 0 ORDER BY code"
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_product_by_id(product_id):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, code, name, spec, unit, disabled, remark, created_at FROM product WHERE id = ?",
                (product_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            product = dict(row)
            cursor.execute(
                "SELECT COUNT(*) as count FROM bom WHERE product_id = ?",
                (product_id,)
            )
            product['bom_count'] = cursor.fetchone()['count']
        return product

    @staticmethod
    def duplicate_product(product_id):
        """复制产品: 名称追加 "副本", 编码重新生成, 复制 BOM 物料清单与替代关系"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM product WHERE id = ?", (product_id,))
            src = cursor.fetchone()
            if not src:
                return False, '产品不存在'

            new_name = f"{src['name']}副本"
            prefix = (src['code'] or '')[:4]

            new_code = None
            cursor.execute(
                "SELECT code FROM product WHERE code LIKE ? ORDER BY code",
                (prefix + '%',)
            )
            seq = 0
            for row in cursor.fetchall():
                suffix = row['code'][len(prefix):]
                try:
                    s = int(suffix)
                except ValueError:
                    s = 0
                if s > seq:
                    seq = s

            def _fmt(prefix, seq, digits):
                return f"{prefix}{str(seq).zfill(digits)}"

            if seq == 0:
                if prefix:
                    digits = max(1, 8 - len(prefix))
                    new_code = _fmt(prefix, 1, digits)
                else:
                    cursor.execute("SELECT code FROM product ORDER BY code DESC LIMIT 1")
                    last = cursor.fetchone()
                    try:
                        seq = int(last['code']) + 1 if last else 1
                    except ValueError:
                        seq = 1
                    new_code = str(seq).zfill(8)
            else:
                if prefix:
                    digits = max(1, 8 - len(prefix))
                    new_code = _fmt(prefix, seq + 1, digits)
                else:
                    new_code = str(seq + 1).zfill(8)

            # 兜底: 如果碰撞直接用前缀重试
            cursor.execute("SELECT id FROM product WHERE code = ?", (new_code,))
            if cursor.fetchone():
                new_code = _fmt(prefix, seq + 2, max(1, 8 - len(prefix))) if prefix else str(seq + 2).zfill(8)

            cursor.execute(
                "INSERT INTO product (code, name, spec, unit, remark) VALUES (?, ?, ?, ?, ?)",
                (new_code, new_name, src['spec'], src['unit'], src['remark'])
            )
            new_id = cursor.lastrowid

            cursor.execute(
                "SELECT material_id, qty_per_unit, remark FROM bom WHERE product_id = ?",
                (product_id,)
            )
            bom_rows = cursor.fetchall()
            if bom_rows:
                cursor.executemany(
                    "INSERT INTO bom (product_id, material_id, qty_per_unit, remark) VALUES (?, ?, ?, ?)",
                    [(new_id, r['material_id'], r['qty_per_unit'], r['remark']) for r in bom_rows]
                )

                old_bom_id_map = {}
                cursor.execute("SELECT id, material_id FROM bom WHERE product_id = ?", (product_id,))
                for r in cursor.fetchall():
                    old_bom_id_map[r['id']] = r['material_id']
                new_bom_id_by_material = {}
                cursor.execute("SELECT id, material_id FROM bom WHERE product_id = ?", (new_id,))
                for r in cursor.fetchall():
                    new_bom_id_by_material[r['material_id']] = r['id']

                cursor.execute(
                    """SELECT bs.bom_id, bs.material_id, bs.priority, bs.remark
                       FROM bom_substitute bs JOIN bom b ON bs.bom_id = b.id
                       WHERE b.product_id = ?""",
                    (product_id,)
                )
                sub_rows = cursor.fetchall()
                if sub_rows:
                    inserts = []
                    for s in sub_rows:
                        main_material = old_bom_id_map.get(s['bom_id'])
                        if main_material and main_material in new_bom_id_by_material:
                            inserts.append((
                                new_bom_id_by_material[main_material],
                                s['material_id'],
                                s['priority'],
                                s['remark']
                            ))
                    if inserts:
                        cursor.executemany(
                            "INSERT INTO bom_substitute (bom_id, material_id, priority, remark) VALUES (?, ?, ?, ?)",
                            inserts
                        )

            conn.commit()
            return True, ProductService.get_product_by_id(new_id)

    @staticmethod
    def get_next_code(prefix=None):
        """自动生成下一个编码: 前缀 + 序号"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if prefix:
                cursor.execute("SELECT code FROM product WHERE code LIKE ? ORDER BY code", (prefix + '%',))
            else:
                cursor.execute("SELECT code FROM product ORDER BY code DESC LIMIT 1")
            rows = cursor.fetchall()
            seq = 0
            for row in rows:
                suffix = row['code'][len(prefix):] if prefix else row['code']
                try:
                    s = int(suffix)
                except ValueError:
                    s = 0
                if s > seq:
                    seq = s
            if prefix and len(prefix) < 8:
                digits = max(1, 8 - len(prefix))
                return prefix + str(seq + 1).zfill(digits)
            elif prefix:
                return prefix + str(seq + 1)
            return str(seq + 1).zfill(8)

    @staticmethod
    def create_product(code=None, name=None, spec=None, unit='个', remark=None):
        if not name or not str(name).strip():
            raise ValueError('产品名称不能为空')
        if not code or not str(code).strip():
            code = ProductService.get_next_code()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM product WHERE code = ?", (code,))
            if cursor.fetchone():
                raise ValueError(f'产品编码 {code} 已存在')
            cursor.execute(
                "INSERT INTO product (code, name, spec, unit, remark) VALUES (?, ?, ?, ?, ?)",
                (code, name, spec, unit, remark)
            )
            conn.commit()
            return ProductService.get_product_by_id(cursor.lastrowid)

    @staticmethod
    def update_product(product_id, data):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, code FROM product WHERE id = ?", (product_id,))
            if not cursor.fetchone():
                return None
            payload = {**data, 'id': product_id}
            sql, params = build_update_sql('product', payload, PRODUCT_UPDATE_FIELDS)
            if sql:
                cursor.execute(sql, params)
                conn.commit()
        return ProductService.get_product_by_id(product_id)

    @staticmethod
    def delete_product(product_id):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM product WHERE id = ?", (product_id,))
            if not cursor.fetchone():
                return False, '产品不存在'
            cursor.execute("DELETE FROM bom_substitute WHERE bom_id IN (SELECT id FROM bom WHERE product_id = ?)", (product_id,))
            cursor.execute("DELETE FROM bom WHERE product_id = ?", (product_id,))
            cursor.execute("DELETE FROM product WHERE id = ?", (product_id,))
            conn.commit()
        return True, '删除成功'

    @staticmethod
    def get_bom(product_id):
        """返回 BOM 列表 (含物料名/编码/规格/单位 + 每行的替代物料)"""
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT b.id, b.product_id, b.material_id, b.qty_per_unit, b.remark,
                       m.code, m.name, m.spec, m.unit, m.manufacturer
                FROM bom b
                JOIN material m ON b.material_id = m.id
                WHERE b.product_id = ?
                ORDER BY m.code
                """,
                (product_id,)
            )
            items = [dict(row) for row in cursor.fetchall()]

            if items:
                bom_ids = [it['id'] for it in items]
                placeholders = ','.join('?' * len(bom_ids))
                cursor.execute(
                    f"""
                    SELECT s.id, s.bom_id, s.material_id, s.priority, s.remark,
                           m.code, m.name, m.spec, m.unit, m.manufacturer
                    FROM bom_substitute s
                    JOIN material m ON s.material_id = m.id
                    WHERE s.bom_id IN ({placeholders})
                    ORDER BY s.bom_id, s.priority, m.code
                    """,
                    bom_ids
                )
                subs_by_bom = {}
                for r in cursor.fetchall():
                    subs_by_bom.setdefault(r['bom_id'], []).append(dict(r))
                for it in items:
                    it['substitutes'] = subs_by_bom.get(it['id'], [])
        return items

    @staticmethod
    def replace_bom(product_id, items):
        """整批替换产品的 BOM (含替代物料)

        items: [{material_id, qty_per_unit, remark, substitutes?: [{material_id, priority, remark}]}]
        """
        if not isinstance(items, list):
            raise ValueError('BOM 数据格式错误')
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM product WHERE id = ?", (product_id,))
            if not cursor.fetchone():
                raise ValueError('产品不存在')

            main_seen = set()
            validated_rows = []
            for idx, item in enumerate(items):
                material_id = item.get('material_id')
                qty = item.get('qty_per_unit')
                if not material_id:
                    raise ValueError(f'第 {idx + 1} 行: 物料不能为空')
                if material_id in main_seen:
                    raise ValueError(f'第 {idx + 1} 行: 物料重复 (id={material_id})')
                main_seen.add(material_id)
                try:
                    qty_f = float(qty)
                except (TypeError, ValueError):
                    raise ValueError(f'第 {idx + 1} 行: 单件用量必须为数字')
                if qty_f <= 0:
                    raise ValueError(f'第 {idx + 1} 行: 单件用量必须大于 0')
                cursor.execute("SELECT id FROM material WHERE id = ?", (material_id,))
                if not cursor.fetchone():
                    raise ValueError(f'第 {idx + 1} 行: 物料 id={material_id} 不存在')
                validated_rows.append((product_id, material_id, qty_f, item.get('remark')))

            cursor.execute("DELETE FROM bom_substitute WHERE bom_id IN (SELECT id FROM bom WHERE product_id = ?)", (product_id,))
            cursor.execute("DELETE FROM bom WHERE product_id = ?", (product_id,))
            cursor.executemany(
                "INSERT INTO bom (product_id, material_id, qty_per_unit, remark) VALUES (?, ?, ?, ?)",
                validated_rows
            )
            cursor.execute(
                "SELECT id, material_id FROM bom WHERE product_id = ?",
                (product_id,)
            )
            bom_id_by_material = {row['material_id']: row['id'] for row in cursor.fetchall()}

            sub_validated = []
            for item in items:
                subs = item.get('substitutes') or []
                if not subs:
                    continue
                main_mid = item['material_id']
                bom_id = bom_id_by_material[main_mid]
                seen = set()
                for j, s in enumerate(subs):
                    smid = s.get('material_id')
                    if not smid:
                        raise ValueError(f'物料 id={main_mid} 的替代物料: 第 {j + 1} 项物料不能为空')
                    if smid == main_mid:
                        raise ValueError(f'物料 id={main_mid} 的替代物料: 不能与主物料相同')
                    if smid in seen:
                        raise ValueError(f'物料 id={main_mid} 的替代物料: 物料 id={smid} 重复')
                    seen.add(smid)
                    cursor.execute("SELECT id FROM material WHERE id = ?", (smid,))
                    if not cursor.fetchone():
                        raise ValueError(f'物料 id={main_mid} 的替代物料: id={smid} 不存在')
                    try:
                        pri = int(s.get('priority', 1))
                    except (TypeError, ValueError):
                        raise ValueError(f'物料 id={main_mid} 的替代物料: priority 必须为整数')
                    sub_validated.append((bom_id, smid, pri, s.get('remark')))

            if sub_validated:
                cursor.executemany(
                    "INSERT INTO bom_substitute (bom_id, material_id, priority, remark) VALUES (?, ?, ?, ?)",
                    sub_validated
                )
            conn.commit()
        return ProductService.get_bom(product_id)

    @staticmethod
    def _stock_map(material_ids, exclude_expired=True):
        """返回 {material_id: 可用库存}, 排除过期"""
        if not material_ids:
            return {}
        placeholders = ','.join('?' * len(material_ids))
        sql = f"SELECT material_id, COALESCE(SUM(quantity), 0) AS total FROM inventory WHERE material_id IN ({placeholders})"
        params = list(material_ids)
        if exclude_expired:
            sql += " AND (expiry_date IS NULL OR expiry_date >= date('now', 'localtime'))"
        sql += " GROUP BY material_id"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return {row['material_id']: float(row['total']) for row in cursor.fetchall()}

    @staticmethod
    def calculate_requirements(items, exclude_expired=True):
        """计算需求: items=[{product_id, quantity}], 返回按物料聚合的需求/库存/缺料明细

        主物料库存不足时, 把替代物料库存合并入可用量。
        """
        if not items:
            raise ValueError('请至少添加一个产品')

        product_ids = []
        validated = []
        for idx, it in enumerate(items):
            pid = it.get('product_id')
            qty = it.get('quantity')
            try:
                qty_f = float(qty)
            except (TypeError, ValueError):
                raise ValueError(f'第 {idx + 1} 行: 生产数量必须为数字')
            if qty_f <= 0:
                raise ValueError(f'第 {idx + 1} 行: 生产数量必须大于 0')
            product_ids.append(pid)
            validated.append((pid, qty_f))

        with get_db_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(product_ids))
            cursor.execute(
                f"SELECT id, code, name, spec, unit FROM product WHERE id IN ({placeholders})",
                product_ids
            )
            products = {row['id']: dict(row) for row in cursor.fetchall()}
            missing = [pid for pid in product_ids if pid not in products]
            if missing:
                raise ValueError(f'产品不存在: {missing}')

            cursor.execute(
                f"""
                SELECT b.id AS bom_id, b.product_id, b.material_id, b.qty_per_unit,
                       m.code, m.name, m.spec, m.unit, m.manufacturer
                FROM bom b JOIN material m ON b.material_id = m.id
                WHERE b.product_id IN ({placeholders})
                """,
                product_ids
            )
            bom_rows = cursor.fetchall()

            bom_id_list = [r['bom_id'] for r in bom_rows]
            substitutes_by_bom = {}
            if bom_id_list:
                ph2 = ','.join('?' * len(bom_id_list))
                cursor.execute(
                    f"""
                    SELECT s.bom_id, s.material_id, m.code, m.name, m.spec, m.unit, m.manufacturer
                    FROM bom_substitute s JOIN material m ON s.material_id = m.id
                    WHERE s.bom_id IN ({ph2})
                    ORDER BY s.priority
                    """,
                    bom_id_list
                )
                for r in cursor.fetchall():
                    substitutes_by_bom.setdefault(r['bom_id'], []).append(dict(r))

        agg = {}
        for br in bom_rows:
            qty_total = next(q for pid, q in validated if pid == br['product_id'])
            per_unit = float(br['qty_per_unit'])
            mid = br['material_id']
            if mid not in agg:
                agg[mid] = {
                    'material_id': mid,
                    'code': br['code'],
                    'name': br['name'],
                    'spec': br['spec'],
                    'unit': br['unit'],
                    'manufacturer': br['manufacturer'],
                    'required': 0.0,
                    'substitutes': [],
                }
            agg[mid]['required'] += per_unit * qty_total

            for sub in substitutes_by_bom.get(br['bom_id'], []):
                if sub['material_id'] not in {s['material_id'] for s in agg[mid]['substitutes']}:
                    agg[mid]['substitutes'].append({
                        'material_id': sub['material_id'],
                        'code': sub['code'],
                        'name': sub['name'],
                        'spec': sub['spec'],
                        'unit': sub['unit'],
                    })

        all_material_ids = list(agg.keys())
        for info in agg.values():
            all_material_ids.extend(s['material_id'] for s in info['substitutes'])
        stock = ProductService._stock_map(list(set(all_material_ids)), exclude_expired)

        rows = []
        for mid, info in agg.items():
            req = round(info['required'], 4)
            main_stock = round(stock.get(mid, 0.0), 2)
            sub_stock = round(sum(stock.get(s['material_id'], 0.0) for s in info['substitutes']), 2)
            available = round(main_stock + sub_stock, 2)
            short = round(max(0.0, req - available), 4)
            rows.append({
                'material_id': mid,
                'code': info['code'],
                'name': info['name'],
                'spec': info['spec'],
                'unit': info['unit'],
                'manufacturer': info['manufacturer'],
                'required': req,
                'main_stock': main_stock,
                'substitute_stock': sub_stock,
                'available': available,
                'shortage': short,
                'sufficient': short == 0,
                'substitute_count': len(info['substitutes']),
                'substitutes': info['substitutes'],
            })
        rows.sort(key=lambda r: (r['sufficient'], r['code']))

        product_summary = []
        for pid, qty in validated:
            product_summary.append({
                'product_id': pid,
                'code': products[pid]['code'],
                'name': products[pid]['name'],
                'unit': products[pid]['unit'],
                'quantity': qty,
            })

        return {
            'rows': rows,
            'has_shortage': any(r['shortage'] > 0 for r in rows),
            'products': product_summary,
            'exclude_expired': exclude_expired,
        }

    @staticmethod
    def calculate_max_producible(product_id, exclude_expired=True):
        """返回产品当前库存最大可生产整数件数 + 瓶颈物料

        每个 BOM 物料的可用量 = 主库存 + 替代库存合计。
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, code, name, unit FROM product WHERE id = ?", (product_id,))
            product = cursor.fetchone()
            if not product:
                raise ValueError('产品不存在')

            cursor.execute(
                """
                SELECT b.id AS bom_id, b.material_id, b.qty_per_unit, m.code, m.name, m.spec, m.unit, m.manufacturer
                FROM bom b JOIN material m ON b.material_id = m.id
                WHERE b.product_id = ?
                """,
                (product_id,)
            )
            bom_rows = cursor.fetchall()

        if not bom_rows:
            raise ValueError('该产品未配置 BOM，无法计算')

        all_material_ids = [r['material_id'] for r in bom_rows]
        substitutes_by_bom = {}
        with get_db_connection() as conn:
            cursor = conn.cursor()
            bom_id_list = [r['bom_id'] for r in bom_rows]
            if bom_id_list:
                ph = ','.join('?' * len(bom_id_list))
                cursor.execute(
                    f"""
                    SELECT s.bom_id, s.material_id, m.code, m.name, m.spec, m.unit, m.manufacturer
                    FROM bom_substitute s JOIN material m ON s.material_id = m.id
                    WHERE s.bom_id IN ({ph})
                    ORDER BY s.priority
                    """,
                    bom_id_list
                )
                for r in cursor.fetchall():
                    substitutes_by_bom.setdefault(r['bom_id'], []).append(dict(r))
                    all_material_ids.append(r['material_id'])
        stock = ProductService._stock_map(list(set(all_material_ids)), exclude_expired)

        breakdown = []
        max_units = None
        bottleneck = None
        for r in bom_rows:
            per = float(r['qty_per_unit'])
            main_stock = stock.get(r['material_id'], 0.0)
            sub_stock = sum(stock.get(s['material_id'], 0.0) for s in substitutes_by_bom.get(r['bom_id'], []))
            available = main_stock + sub_stock
            possible = math.floor(available / per) if per > 0 else 0
            breakdown.append({
                'material_id': r['material_id'],
                'code': r['code'],
                'name': r['name'],
                'manufacturer': r['manufacturer'] or '',
                'unit': r['unit'],
                'qty_per_unit': per,
                'main_stock': round(main_stock, 2),
                'substitute_stock': round(sub_stock, 2),
                'available': round(available, 2),
                'max_units': possible,
                'substitute_count': len(substitutes_by_bom.get(r['bom_id'], [])),
            })
            if max_units is None or possible < max_units:
                max_units = possible
                bottleneck = r['code']

        return {
            'product': dict(product),
            'max_producible': max_units or 0,
            'bottleneck_material': bottleneck,
            'breakdown': breakdown,
            'exclude_expired': exclude_expired,
        }
