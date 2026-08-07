import sqlite3
import os
from contextlib import contextmanager
from werkzeug.security import generate_password_hash
from config import Config

@contextmanager
def get_db_connection():
    """Get database connection with automatic cleanup"""
    os.makedirs(os.path.dirname(Config.DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(Config.DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
    finally:
        conn.close()

def _create_tables(cursor):
    """建表: 用户/物料/订单/RBAC 等所有业务表"""
        # User table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at DATETIME
        )
    ''')

    # Employee table (经手人/领用人/退库人)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employee (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            department TEXT,
            phone TEXT,
            remark TEXT,
            created_at DATETIME DEFAULT (datetime('now', 'localtime'))
        )
    ''')

    # Material category table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS material_category (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            parent_code TEXT,
            level INTEGER NOT NULL
        )
    ''')

    # Material table (包含 is_reusable)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS material (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            spec TEXT,
            unit TEXT NOT NULL,
            category_code TEXT,
            manufacturer TEXT,
            storage_condition TEXT DEFAULT '常温',
            shelf_life INTEGER,
            remark TEXT,
            is_reusable INTEGER DEFAULT 0,
            safety_stock DECIMAL(16,2) DEFAULT 0,
            created_at DATETIME
        )
    ''')

    # Supplier table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS supplier (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT,
            phone TEXT,
            address TEXT,
            created_at DATETIME
        )
    ''')

    # Customer (客户)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            short_name TEXT,
            contact TEXT,
            phone TEXT,
            address TEXT,
            remark TEXT,
            created_at DATETIME
        )
    ''')

    # In order (入库单主表)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS in_order (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            supplier_id INTEGER,
            operator_id INTEGER,
            status TEXT DEFAULT 'pending',
            remark TEXT,
            receiver TEXT,
            purpose TEXT,
            receiver_date DATE,
            created_at DATETIME,
            approved_at DATETIME,
            approved_by INTEGER,
            FOREIGN KEY (supplier_id) REFERENCES supplier(id),
            FOREIGN KEY (operator_id) REFERENCES user(id),
            FOREIGN KEY (approved_by) REFERENCES user(id)
        )
    ''')

    # In order item (入库单明细表)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS in_order_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            batch_no TEXT,
            production_date DATE,
            expiry_date DATE,
            quantity DECIMAL(16,2) NOT NULL,
            unit_price DECIMAL(16,2) DEFAULT 0,
            remark TEXT,
            FOREIGN KEY (order_id) REFERENCES in_order(id),
            FOREIGN KEY (material_id) REFERENCES material(id)
        )
    ''')

    # Out order (出库单主表)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS out_order (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            operator_id INTEGER,
            status TEXT DEFAULT 'pending',
            remark TEXT,
            purpose TEXT,
            created_at DATETIME,
            approved_at DATETIME,
            approved_by INTEGER,
            department TEXT,
            receiver TEXT,
            receiver_date DATE,
            FOREIGN KEY (operator_id) REFERENCES user(id),
            FOREIGN KEY (approved_by) REFERENCES user(id)
        )
    ''')

    # Out order item (出库单明细表，包含可回用物料字段)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS out_order_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            batch_no TEXT,
            unit_price DECIMAL(16,2) DEFAULT 0,
            remark TEXT,
            requested_quantity DECIMAL(16,2) DEFAULT 0,
            actual_quantity DECIMAL(16,2) DEFAULT 0,
            initial_gross_weight DECIMAL(16,2),
            shipment_info TEXT,
            FOREIGN KEY (order_id) REFERENCES out_order(id),
            FOREIGN KEY (material_id) REFERENCES material(id)
        )
    ''')

    # Reusable material weight table (称重记录表)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reusable_material_weight (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            out_order_item_id INTEGER NOT NULL UNIQUE,
            material_id INTEGER NOT NULL,
            initial_gross_weight DECIMAL(16,2),
            initial_weight_time DATETIME,
            initial_operator_id INTEGER,
            return_gross_weight DECIMAL(16,2),
            return_weight_time DATETIME,
            return_operator_id INTEGER,
            actual_net_weight DECIMAL(16,2),
            status TEXT DEFAULT 'checked_out',
            remark TEXT,
            FOREIGN KEY (out_order_item_id) REFERENCES out_order_item(id),
            FOREIGN KEY (material_id) REFERENCES material(id),
            FOREIGN KEY (initial_operator_id) REFERENCES user(id),
            FOREIGN KEY (return_operator_id) REFERENCES user(id)
        )
    ''')

    # Inventory (库存表 - 单表设计)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            batch_no TEXT NOT NULL,
            production_date DATE,
            expiry_date DATE,
            quantity DECIMAL(16,2) DEFAULT 0,
            in_order_item_id INTEGER,
            updated_at DATETIME,
            FOREIGN KEY (material_id) REFERENCES material(id),
            FOREIGN KEY (in_order_item_id) REFERENCES in_order_item(id),
            UNIQUE(material_id, batch_no)
        )
    ''')

    # Return order (退库单主表)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS return_order (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            related_out_order_id INTEGER,
            department TEXT,
            receiver TEXT,
            receiver_date DATE,
            operator_id INTEGER,
            status TEXT DEFAULT 'pending',
            remark TEXT,
            created_at DATETIME,
            approved_at DATETIME,
            approved_by INTEGER,
            FOREIGN KEY (related_out_order_id) REFERENCES out_order(id),
            FOREIGN KEY (operator_id) REFERENCES user(id),
            FOREIGN KEY (approved_by) REFERENCES user(id)
        )
    ''')

    # Return order item (退库单明细表，包含退回毛重和实际净用量)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS return_order_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            return_order_id INTEGER NOT NULL,
            out_order_item_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            batch_no TEXT,
            remark TEXT,
            return_gross_weight DECIMAL(16,2),
            actual_net_weight DECIMAL(16,2),
            quantity DECIMAL(16,2),
            FOREIGN KEY (return_order_id) REFERENCES return_order(id),
            FOREIGN KEY (out_order_item_id) REFERENCES out_order_item(id),
            FOREIGN KEY (material_id) REFERENCES material(id)
        )
    ''')

    # Product (产品/成品)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            spec TEXT,
            unit TEXT NOT NULL DEFAULT '个',
            disabled INTEGER DEFAULT 0,
            remark TEXT,
            created_at DATETIME
        )
    ''')

    # BOM (产品物料清单，单层)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bom (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            qty_per_unit DECIMAL(16,4) NOT NULL,
            remark TEXT,
            UNIQUE(product_id, material_id)
        )
    ''')

    # BOM 替代物料 (BOM 行的可替代物料, 库存不足时合并计入可用量)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bom_substitute (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bom_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            priority INTEGER DEFAULT 1,
            remark TEXT,
            UNIQUE(bom_id, material_id)
        )
    ''')

    # RBAC tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS role (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            is_system INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT (datetime('now', 'localtime'))
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_role (
            user_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, role_id),
            FOREIGN KEY (user_id) REFERENCES user(id),
            FOREIGN KEY (role_id) REFERENCES role(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS permission (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL,
            action TEXT NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(module, action)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS role_permission (
            role_id INTEGER NOT NULL,
            permission_id INTEGER NOT NULL,
            PRIMARY KEY (role_id, permission_id),
            FOREIGN KEY (role_id) REFERENCES role(id),
            FOREIGN KEY (permission_id) REFERENCES permission(id)
        )
    ''')



def _create_indexes(cursor):
    """建索引: 21 条索引覆盖主表/明细/状态/时间/库存过期/可回用/权限"""
    # 主表单号
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_in_order_order_no ON in_order(order_no)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_out_order_order_no ON out_order(order_no)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_inventory_material ON inventory(material_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_return_order_order_no ON return_order(order_no)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_return_order_related_out ON return_order(related_out_order_id)')

    # BOM (按产品查清单)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bom_product ON bom(product_id)')

    # BOM 替代 (按 bom_id 查替代物料)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bom_substitute_bom ON bom_substitute(bom_id)')

    # 明细表 (查单/查明细)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_in_order_item_order ON in_order_item(order_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_out_order_item_order ON out_order_item(order_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_return_order_item_ro ON return_order_item(return_order_id)')
    # 唯一约束: 同一入库单内相同物料+批次不能重复
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_in_order_item_unique ON in_order_item(order_id, material_id, batch_no)')
    # 明细表 (按物料, pending_in/out enrich)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_in_order_item_material ON in_order_item(material_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_out_order_item_mb ON out_order_item(material_id, batch_no)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_return_order_item_ooi ON return_order_item(out_order_item_id)')
    # 单据状态/时间 (过滤+排序)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_in_order_status ON in_order(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_out_order_status ON out_order(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_return_order_status ON return_order(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_in_order_created ON in_order(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_out_order_created ON out_order(created_at)')
    # 库存过期 (过期过滤)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_inventory_expiry ON inventory(expiry_date)')
    # 可回用重量 (退库审核)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_reusable_weight_ooi ON reusable_material_weight(out_order_item_id)')
    # 权限 (登录/角色分配/角色管理)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_role_user ON user_role(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_role_role ON user_role(role_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_role_permission_role ON role_permission(role_id)')



def _migrate_iso_dates(cursor):
    """日期格式升级: YYYY-M-D -> YYYY-MM-DD"""
    for table, col in [
        ('inventory', 'expiry_date'), ('inventory', 'production_date'),
        ('in_order_item', 'expiry_date'), ('in_order_item', 'production_date'),
    ]:
        cursor.execute(f"SELECT id, {col} FROM {table} WHERE {col} IS NOT NULL")
        updates = []
        for row in cursor.fetchall():
            val = row[col]
            if not val or val.count('-') != 2:
                continue
            y, m, d = val.split('-')
            if len(m) == 2 and len(d) == 2:
                continue
            iso = f"{y}-{int(m):02d}-{int(d):02d}"
            updates.append((iso, row['id']))
        for iso, rid in updates:
            cursor.execute(f"UPDATE {table} SET {col} = ? WHERE id = ?", (iso, rid))


def _seed_permissions(cursor):
    """种子: 33条权限 + 清理废弃"""
    # Seed permissions (33 records)
    permissions = [
        ('dashboard', 'view', '首页-查看'),
        ('category_major', 'view', '大类管理-查看'), ('category_major', 'edit', '大类管理-编辑'),
        ('category_minor', 'view', '小类管理-查看'), ('category_minor', 'edit', '小类管理-编辑'),
        ('material', 'view', '物料管理-查看'), ('material', 'edit', '物料管理-编辑'),
        ('supplier', 'view', '供应商-查看'), ('supplier', 'edit', '供应商-编辑'),
        ('employee', 'view', '员工管理-查看'), ('employee', 'edit', '员工管理-编辑'),
        ('customer', 'view', '客户管理-查看'), ('customer', 'edit', '客户管理-编辑'),
        ('in_order', 'view', '入库单-查看'), ('in_order', 'edit', '入库单-编辑'), ('in_order', 'approve', '入库单-审核'),
        ('out_order', 'view', '出库单-查看'), ('out_order', 'edit', '出库单-编辑'), ('out_order', 'approve', '出库单-审核'),
        ('return_order', 'view', '退库单-查看'), ('return_order', 'edit', '退库单-编辑'), ('return_order', 'approve', '退库单-审核'),
        ('inventory', 'view', '日常查询-库存查询'),
        ('weight_record', 'view', '日常查询-称重记录'),
        ('report_inventory', 'view', '报表分析-库存报表'),
        ('report_stock_flow', 'view', '报表分析-出入库报表'),
        ('report_in_detail', 'view', '报表分析-入库明细报表'),
        ('report_out_detail', 'view', '报表分析-出库明细报表'),
        ('report_summary', 'view', '报表分析-汇总统计'),
        ('product', 'view', '产品BOM-查看'),
        ('product', 'edit', '产品BOM-编辑'),
        ('admin_role', 'manage', '权限管理-角色管理'),
        ('admin_user', 'manage', '权限管理-用户管理'),
    ]
    for module, action, name in permissions:
        cursor.execute(
            "INSERT OR IGNORE INTO permission (module, action, name) VALUES (?, ?, ?)",
            (module, action, name)
        )
        cursor.execute(
            "UPDATE permission SET name = ? WHERE module = ? AND action = ?",
            (name, module, action)
        )

    # 清理已废弃的权限
    valid_perms = {(m, a) for m, a, _ in permissions}
    cursor.execute("SELECT id, module, action FROM permission")
    for row in cursor.fetchall():
        if (row['module'], row['action']) not in valid_perms:
            cursor.execute("DELETE FROM role_permission WHERE permission_id = ?", (row['id'],))
            cursor.execute("DELETE FROM permission WHERE id = ?", (row['id'],))


def _migrate_product_disabled(cursor):
    """迁移: 旧表加 disabled 列"""
    cursor.execute("PRAGMA table_info(product)")
    cols = {r[1] for r in cursor.fetchall()}
    if 'disabled' not in cols:
        cursor.execute("ALTER TABLE product ADD COLUMN disabled INTEGER DEFAULT 0")


def _migrate_return_qty(cursor):
    """迁移: return_order_item 加 quantity 列"""
    cursor.execute("PRAGMA table_info(return_order_item)")
    cols = {r[1] for r in cursor.fetchall()}
    if 'quantity' not in cols:
        cursor.execute("ALTER TABLE return_order_item ADD COLUMN quantity DECIMAL(16,2)")



def _seed_roles(cursor):
    """种子: 3个默认角色"""
    # Seed default roles
    cursor.execute("SELECT id FROM role WHERE name = '管理员'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO role (name, description, is_system) VALUES ('管理员', '拥有所有权限', 1)")
    cursor.execute("SELECT id FROM role WHERE name = '操作员'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO role (name, description, is_system) VALUES ('操作员', '查看+编辑，无审核权限', 1)")
    cursor.execute("SELECT id FROM role WHERE name = '查看员'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO role (name, description, is_system) VALUES ('查看员', '仅查看权限', 1)")



def _assign_role_permissions(cursor):
    """分配权限 + 旧用户迁移; 返回 {name: role_dict}"""
    role_info = {}
    for name in ('管理员', '操作员', '查看员'):
        cursor.execute("SELECT id FROM role WHERE name = ?", (name,))
        r = cursor.fetchone()
        if r:
            role_info[name] = dict(r)
    if len(role_info) != 3:
        return None
    def _ensure(role_id, perm_filter):
        cursor.execute("SELECT permission_id FROM role_permission WHERE role_id = ?", (role_id,))
        existing = {row['permission_id'] for row in cursor.fetchall()}
        cursor.execute(f"SELECT id FROM permission WHERE {perm_filter}")
        for row in cursor.fetchall():
            if row['id'] not in existing:
                cursor.execute("INSERT INTO role_permission (role_id, permission_id) VALUES (?, ?)",
                               (role_id, row['id']))
    _ensure(role_info['管理员']['id'], '1=1')
    _ensure(role_info['操作员']['id'], "action IN ('view', 'edit')")
    _ensure(role_info['查看员']['id'], "action = 'view'")
    viewer_id = role_info['查看员']['id']
    cursor.execute("SELECT id FROM user WHERE id NOT IN (SELECT user_id FROM user_role)")
    for user in cursor.fetchall():
        cursor.execute("INSERT OR IGNORE INTO user_role (user_id, role_id) VALUES (?, ?)",
                       (user['id'], viewer_id))
    return role_info



def _create_triggers(cursor):
    """建触发器: created_at / updated_at"""
    for t in ('user', 'material', 'supplier', 'in_order', 'out_order', 'return_order', 'product', 'customer'):
        cursor.execute(f'''
            CREATE TRIGGER IF NOT EXISTS {t}_created_at AFTER INSERT ON {t}
            WHEN NEW.created_at IS NULL
            BEGIN
                UPDATE {t} SET created_at = datetime('now', 'localtime') WHERE rowid = NEW.rowid;
            END
        ''')
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS inventory_updated_at AFTER INSERT ON inventory
        WHEN NEW.updated_at IS NULL
        BEGIN
            UPDATE inventory SET updated_at = datetime('now', 'localtime') WHERE rowid = NEW.rowid;
        END
    ''')
    cursor.execute('''
        CREATE TRIGGER IF NOT EXISTS inventory_updated_at_update AFTER UPDATE ON inventory
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
            UPDATE inventory SET updated_at = datetime('now', 'localtime') WHERE rowid = NEW.rowid;
        END
    ''')



def _init_admin(cursor, admin_role):
    """管理员种子 (默认 admin/admin12345)"""
    cursor.execute("SELECT id FROM user WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO user (username, password) VALUES (?, ?)",
            ('admin', generate_password_hash('admin12345'))
        )
        if admin_role:
            cursor.execute("INSERT OR IGNORE INTO user_role (user_id, role_id) VALUES (?, ?)",
                           (cursor.lastrowid, admin_role['id']))




def init_db():
    """Initialize database tables"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        _create_tables(cursor)
        _create_indexes(cursor)
        _migrate_iso_dates(cursor)
        _migrate_product_disabled(cursor)
        _migrate_return_qty(cursor)
        _seed_permissions(cursor)
        _seed_roles(cursor)
        roles = _assign_role_permissions(cursor)
        _create_triggers(cursor)
        _init_admin(cursor, roles['管理员'] if roles else None)
        conn.commit()


if __name__ == '__main__':
    init_db()
    print("Database initialized successfully!")
