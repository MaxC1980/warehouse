import sqlite3
import os
from config import Config

def get_db_connection():
    """Get database connection"""
    os.makedirs(os.path.dirname(Config.DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(Config.DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")  # 30 second timeout
    return conn

def init_db():
    """Initialize database tables"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # User table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            can_approve INTEGER DEFAULT 0,
            created_at DATETIME
        )
    ''')

    # Add can_approve column if it doesn't exist (for existing databases)
    cursor.execute("PRAGMA table_info(user)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'can_approve' not in columns:
        cursor.execute("ALTER TABLE user ADD COLUMN can_approve INTEGER DEFAULT 0")
        # Set admin user can_approve = 1
        cursor.execute("UPDATE user SET can_approve = 1 WHERE username = 'admin'")

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
            quantity REAL NOT NULL,
            unit_price REAL DEFAULT 0,
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
            quantity REAL NOT NULL,
            unit_price REAL DEFAULT 0,
            remark TEXT,
            requested_quantity REAL DEFAULT 0,
            actual_quantity REAL DEFAULT 0,
            returned_quantity REAL DEFAULT 0,
            initial_gross_weight REAL,
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
            initial_gross_weight REAL,
            initial_weight_time DATETIME,
            initial_operator_id INTEGER,
            return_gross_weight REAL,
            return_weight_time DATETIME,
            return_operator_id INTEGER,
            actual_net_weight REAL,
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
            quantity REAL DEFAULT 0,
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
            return_quantity REAL NOT NULL,
            remark TEXT,
            return_gross_weight REAL,
            actual_net_weight REAL,
            FOREIGN KEY (return_order_id) REFERENCES return_order(id),
            FOREIGN KEY (out_order_item_id) REFERENCES out_order_item(id),
            FOREIGN KEY (material_id) REFERENCES material(id)
        )
    ''')

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
        WHEN NEW.updated_at IS OLD.updated_at
        BEGIN
            UPDATE inventory SET updated_at = datetime('now', 'localtime') WHERE rowid = NEW.rowid;
        END
    ''')

    # Insert default users if not exists
    # Level 1 (查看): view / view123
    # Level 2 (编辑): edit / edit123
    # Level 3 (管理): admin / admin123
    cursor.execute("SELECT id FROM user WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO user (username, password, can_approve, permission_level) VALUES (?, ?, ?, ?)",
            ('admin', 'admin123', 1, 3)
        )
    cursor.execute("SELECT id FROM user WHERE username = 'view'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO user (username, password, can_approve, permission_level) VALUES (?, ?, ?, ?)",
            ('view', 'view123', 0, 1)
        )
    cursor.execute("SELECT id FROM user WHERE username = 'edit'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO user (username, password, can_approve, permission_level) VALUES (?, ?, ?, ?)",
            ('edit', 'edit123', 0, 2)
        )

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully!")
