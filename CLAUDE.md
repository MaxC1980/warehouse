# CLAUDE.md

Flask + SQLite 仓库管理系统。默认账号：`admin` / `admin12345`

## 运行

```
python run.py      # 开发环境（端口5001）
python app.py      # 生产环境（端口5000，用 waitress）
```

## 架构

- **Routes** (`routes/`) - Flask Blueprint 端点
- **Services** (`services/`) - 业务逻辑
- **Database** (`database.py`) - SQLite 连接，`get_db_connection()`
- **Templates** (`templates/`) - Jinja2 模板

## API 调用

`apiRequest()` 在 `static/js/app.js`，**自动前缀 `/api`**，发送 session cookie：

```javascript
const data = await apiRequest('/in-orders/detail?page=1');  // 正确
// const data = await apiRequest('/api/in-orders/detail');   // 错误
```

## 数据库

```
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("PRAGMA foreign_keys = ON")
# 使用 cursor.execute()，操作后 conn.commit() 再 conn.close()
# sqlite3.Row 不支持 .get()，用 row['col'] 直接访问
```

## 3级权限


| 级别 | 权限                       |
|--------|------------------------------|
| 1      | 查看                       |
| 2      | 编辑（无审核）        |
| 3      | 管理（增删改+审核） |


权限存储在 `session['permission_level']`。

## 业务规则

### 出库审核

- **同一事务内**完成库存扣减，**不调用** `InventoryService.reduce_inventory()`（独立连接会死锁）
- 可回用物料跳过库存扣减

### 退库审核

- 防重复：同一出库单只能有一个审核通过的退库单

### 物料删除

- 有入库/出库记录或库存 > 0 → 不能删除

### 订单状态

- 入库单：`pending → approved`
- 出库单：`pending → approved → completed`
- 退库单：`pending → approved`，或 `cancelled`

## 字段

- **入库单**：supplier_id, receiver, receiver_date, purpose
- **出库单**：department, receiver, receiver_date, purpose
- **库存**：单表设计 (material_id, batch_no) UNIQUE

## 注意

1. 修改表结构后需手动 `ALTER TABLE` 或删除 `db/warehouse.db`
2. SQL LIKE：`code LIKE '0103%'`（前缀），`name LIKE '%关键词%'`（模糊）
3. `request.get_json()` 失败用 `request.get_json(silent=True) or {}`


## 调试

```
playwright-cli open http://localhost:5001/login --browser=chrome --persistent
playwright-cli screenshot
playwright-cli snapshot
```

调试产物放 `debug/` 目录。

 
