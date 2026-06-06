import sqlite3
import os
from contextlib import contextmanager
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

def init_db():
    """Initialize database tables"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # User table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at DATETIME
            )
        ''')

        # Add permission_level column if it doesn't exist (for existing databases)
        cursor.execute("PRAGMA table_info(user)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'permission_level' not in columns:
            cursor.execute("ALTER TABLE user ADD COLUMN permission_level INTEGER DEFAULT 1")
            # Set admin permission_level = 3
            cursor.execute("UPDATE user SET permission_level = 3 WHERE username = 'admin'")

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
                FOREIGN KEY (return_order_id) REFERENCES return_order(id),
                FOREIGN KEY (out_order_item_id) REFERENCES out_order_item(id),
                FOREIGN KEY (material_id) REFERENCES material(id)
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

        # Seed permissions (24 records)
        permissions = [
            ('dashboard', 'view', '首页-查看'),
            ('category_major', 'view', '大类管理-查看'), ('category_major', 'edit', '大类管理-编辑'),
            ('category_minor', 'view', '小类管理-查看'), ('category_minor', 'edit', '小类管理-编辑'),
            ('material', 'view', '物料管理-查看'), ('material', 'edit', '物料管理-编辑'),
            ('supplier', 'view', '供应商-查看'), ('supplier', 'edit', '供应商-编辑'),
            ('employee', 'view', '员工管理-查看'), ('employee', 'edit', '员工管理-编辑'),
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

        # Assign permissions to roles
        cursor.execute("SELECT id FROM role WHERE name = '管理员'")
        admin_role = cursor.fetchone()
        cursor.execute("SELECT id FROM role WHERE name = '操作员'")
        operator_role = cursor.fetchone()
        cursor.execute("SELECT id FROM role WHERE name = '查看员'")
        viewer_role = cursor.fetchone()

        if admin_role and operator_role and viewer_role:
            admin_role_id = admin_role['id']
            operator_role_id = operator_role['id']
            viewer_role_id = viewer_role['id']

            # 管理员：全部权限（包括 admin.manage）
            cursor.execute("SELECT id FROM permission")
            for row in cursor.fetchall():
                cursor.execute("INSERT OR IGNORE INTO role_permission (role_id, permission_id) VALUES (?, ?)",
                               (admin_role_id, row['id']))

            # 操作员：view + edit（不含 approve）
            cursor.execute("SELECT id FROM permission WHERE action != 'approve'")
            for row in cursor.fetchall():
                cursor.execute("INSERT OR IGNORE INTO role_permission (role_id, permission_id) VALUES (?, ?)",
                               (operator_role_id, row['id']))

            # 查看员：仅 view
            cursor.execute("SELECT id FROM permission WHERE action = 'view'")
            for row in cursor.fetchall():
                cursor.execute("INSERT OR IGNORE INTO role_permission (role_id, permission_id) VALUES (?, ?)",
                               (viewer_role_id, row['id']))

            # Migrate existing users to roles based on permission_level
            cursor.execute("SELECT id, permission_level FROM user WHERE id NOT IN (SELECT user_id FROM user_role)")
            for user in cursor.fetchall():
                level = user['permission_level'] or 1
                if level >= 3:
                    cursor.execute("INSERT OR IGNORE INTO user_role (user_id, role_id) VALUES (?, ?)",
                                   (user['id'], admin_role_id))
                elif level >= 2:
                    cursor.execute("INSERT OR IGNORE INTO user_role (user_id, role_id) VALUES (?, ?)",
                                   (user['id'], operator_role_id))
                else:
                    cursor.execute("INSERT OR IGNORE INTO user_role (user_id, role_id) VALUES (?, ?)",
                                   (user['id'], viewer_role_id))

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_in_order_order_no ON in_order(order_no)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_out_order_order_no ON out_order(order_no)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_inventory_material ON inventory(material_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_return_order_order_no ON return_order(order_no)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_return_order_related_out ON return_order(related_out_order_id)')

        # Create triggers for auto-setting localtime timestamps
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS user_created_at AFTER INSERT ON user
            WHEN NEW.created_at IS NULL
            BEGIN
                UPDATE user SET created_at = datetime('now', 'localtime') WHERE rowid = NEW.rowid;
            END
        ''')

        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS material_created_at AFTER INSERT ON material
            WHEN NEW.created_at IS NULL
            BEGIN
                UPDATE material SET created_at = datetime('now', 'localtime') WHERE rowid = NEW.rowid;
            END
        ''')

        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS supplier_created_at AFTER INSERT ON supplier
            WHEN NEW.created_at IS NULL
            BEGIN
                UPDATE supplier SET created_at = datetime('now', 'localtime') WHERE rowid = NEW.rowid;
            END
        ''')

        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS in_order_created_at AFTER INSERT ON in_order
            WHEN NEW.created_at IS NULL
            BEGIN
                UPDATE in_order SET created_at = datetime('now', 'localtime') WHERE rowid = NEW.rowid;
            END
        ''')

        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS out_order_created_at AFTER INSERT ON out_order
            WHEN NEW.created_at IS NULL
            BEGIN
                UPDATE out_order SET created_at = datetime('now', 'localtime') WHERE rowid = NEW.rowid;
            END
        ''')

        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS return_order_created_at AFTER INSERT ON return_order
            WHEN NEW.created_at IS NULL
            BEGIN
                UPDATE return_order SET created_at = datetime('now', 'localtime') WHERE rowid = NEW.rowid;
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

        # Insert default users if not exists and assign roles
        # Level 1 (查看): view / view123
        # Level 2 (编辑): edit / edit123
        # Level 3 (管理): admin / admin123
        cursor.execute("SELECT id FROM user WHERE username = 'admin'")
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO user (username, password, permission_level) VALUES (?, ?, ?)",
                ('admin', 'admin12345', 3)
            )
            admin_user_id = cursor.lastrowid
            if admin_role:
                cursor.execute("INSERT OR IGNORE INTO user_role (user_id, role_id) VALUES (?, ?)",
                               (admin_user_id, admin_role['id']))
        cursor.execute("SELECT id FROM user WHERE username = 'view'")
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO user (username, password, permission_level) VALUES (?, ?, ?)",
                ('view', 'view123', 1)
            )
            view_user_id = cursor.lastrowid
            if viewer_role:
                cursor.execute("INSERT OR IGNORE INTO user_role (user_id, role_id) VALUES (?, ?)",
                               (view_user_id, viewer_role['id']))
        cursor.execute("SELECT id FROM user WHERE username = 'edit'")
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO user (username, password, permission_level) VALUES (?, ?, ?)",
                ('edit', 'edit123', 2)
            )
            edit_user_id = cursor.lastrowid
            if operator_role:
                cursor.execute("INSERT OR IGNORE INTO user_role (user_id, role_id) VALUES (?, ?)",
                               (edit_user_id, operator_role['id']))

        conn.commit()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully!")
