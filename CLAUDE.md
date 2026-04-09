# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Flask + SQLite 仓库管理系统。默认登录账号：`admin` / `admin123`

## 运行应用

```bash
python run.py                      # 开发环境（debug模式）
gunicorn -w 4 -b 0.0.0.0:5000 app:app  # 生产环境
```

服务启动在 `http://localhost:5000`

**注意**：`app.py` 第一行设置了 `sys.dont_write_bytecode = True`，禁用字节码缓存，修改代码后立即生效。

**pytest 未安装**，如需运行测试先 `pip install pytest`。

## 测试

```
python -m pytest tests/test_modules.py
python -m pytest tests/test_modules.py::TestOrderService -v  # 运行指定测试类
```

## 架构概述

### 认证与用户

- 用户表 `user`：id, username, password, can_approve
- 登录：`POST /api/auth/login`
- 当前用户：`GET /api/auth/current_user` → `{id, username, can_approve}`
- 修改密码：`POST /api/auth/change_password` → `{old_password, new_password}`
- Session 保存在 Flask session 中，关闭浏览器后失效

### 分层架构

- **Routes** (`routes/`) - Flask Blueprint 端点，处理 HTTP 请求/响应
- **Services** (`services/`) - 业务逻辑、SQL 查询、数据库操作
- **Database** (`database.py`) - SQLite 连接管理，通过 `get_db_connection()`
- **Templates** (`templates/`) - Jinja2 HTML 模板，服务端渲染 + 客户端 JS

### API 路由注册模式

所有 Blueprint 注册在 `/api` 前缀下，页面路由在 `app.py` 中直接定义：

```
app.register_blueprint(in_order_bp, url_prefix='/api')
# API: /api/in-orders, /api/in-orders/<id>/approve
# 页面: GET /in-orders, GET /in-orders/new
```

### 前端 API 调用

`apiRequest()` 定义在 `static/js/app.js`，**自动前缀 `/api`**，且已设置 `credentials: 'include'` 发送 session cookie：

```javascript
// 正确 - apiRequest 会自动加 /api 前缀，且发送 cookies
const data = await apiRequest('/in-orders/detail?page=1');

// 错误 - 不要手动加 /api，会变成 /api/api/...
const data = await apiRequest('/api/in-orders/detail?page=1');
```

## 数据库访问模式

```
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT ...", params)
conn.commit()
conn.close()
```

- 使用原生 `sqlite3`，`Row` factory 返回字典式行（`row['col']` 而非 `row[0]`）
- 操作后必须先 `conn.commit()` 再 `conn.close()`
- `cursor.lastrowid` 获取自增 ID
- `cursor.execute("PRAGMA foreign_keys = ON")` 手动开启外键约束

## 可回用物料称重系统

### 概念

物料分为**普通物料**和**可回用物料**：

- 普通物料（`is_reusable = 0`）：审核时直接扣减库存
- 可回用物料（`is_reusable = 1`）：审核时不扣库存，记录毛重，退库时计算净用量扣减

### 关键表

- `material.is_reusable` - 物料是否可回用
- `out_order_item.initial_gross_weight` - 领用毛重
- `out_order_item.shipment_info` - 实发信息
- `reusable_material_weight` - 称重记录表
- `initial_gross_weight` / `return_gross_weight` - 领用/退回毛重
- `actual_net_weight` - 实际净用量 = 领用毛重 - 退回毛重
- `status` - `checked_out`（已领用）或 `returned`（已退回）

### 出库审核流程（可回用物料）

1. 审核时不扣减库存（跳过 `inventory` 更新）
2. 创建 `reusable_material_weight` 记录，状态为 `checked_out`


### 退库审核流程（可回用物料）

1. 根据 `退回毛重` 计算 `actual_net_weight = initial_gross_weight - return_gross_weight`
2. **回冲库存**：增加 `actual_net_weight` 到原批次库存
3. 更新原出库单 `actual_quantity` 为净用量
4. 更新 `reusable_material_weight` 状态为 `returned`


## 订单工作流

### 出库单状态流转

```
pending → approved → completed
```

### 退库单状态流转

```
pending → approved
    ↓
cancelled
```

## 关键业务规则

### 出库审核 - 批次扣减（同一事务内）

`approve_out_order()` 在单个事务中完成库存扣减，**不调用**
`InventoryService.reduce_inventory()`（后者会独立开连接，导致嵌套事务死锁）。

```
# 正确：在同一连接中内联扣减逻辑
for item in items:
cursor.execute("""UPDATE inventory SET quantity = quantity - ? WHERE material_id = ? AND batch_no = ?...""", (...))
if cursor.rowcount == 0:
conn.rollback(); conn.close()
raise Exception("库存不足")

# 错误：不要调用 InventoryService.reduce_inventory()（独立连接）
```

### 出库审核 - 可回用物料跳过库存扣减

```
# 检查物料是否可回用
cursor.execute("SELECT is_reusable FROM material WHERE id = ?", (item['material_id'],))
mat = cursor.fetchone()
if mat and mat['is_reusable'] == 1:
    continue  # 跳过库存扣减
```

### 明细校验

入库/出库单创建和更新时，**必须先校验 items 非空**（前端提示 + 后端 400 返回）。

## 字段说明

### 入库单 (in_order / in_order_item)

- 主表字段：supplier_id, receiver(经手人), receiver_date, purpose
- 明细字段：material_id, batch_no, production_date, expiry_date, quantity, unit_price

### 出库单 (out_order / out_order_item)

- 主表字段：department, receiver(领用人), receiver_date, purpose
- 明细字段：material_id, batch_no, quantity, requested_quantity, actual_quantity, returned_quantity, initial_gross_weight, shipment_info

### 库存 (inventory)

- 单表设计：(material_id, batch_no) UNIQUE 约束
- 包含 production_date, expiry_date, quantity

### 库存查询详情

`GET /api/inventory?summary=false`（detail 模式）返回每条记录的 `pending_in` 和 `pending_out`
字段，分别表示该物料有多少条待审核的入库单/出库单明细。

### 列表分页规范

所有列表页默认 15 条/页，支持 50 和 100 条选项。分页参数：`page` 和 `per_page`。

### 状态筛选即时生效

状态过滤下拉框（如入库单状态、出库单状态）选择后**立即触发查询**，不需要点击"搜索"按钮。
实现方式：下拉框 `onchange` 事件直接调用加载函数并重置页码为 1。

## 重要注意事项

1. **修改表结构后**：如果表已存在需手动 `ALTER TABLE` 或删除 `db/warehouse.db` 重新初始化
2. **SQL LIKE 匹配**：物料编码用前缀匹配 `code LIKE '0103%'`，物料名称/规格用模糊匹配 `name LIKE '%关键词%'`


## 踩过的坑（避免重蹈覆辙）

### Modal 弹窗样式

Modal 弹窗的 `.modal` 和 `.modal-content` CSS 样式应放在 `base.html` 中，确保所有页面弹窗居中显示。**不要在单个页面模板的 `<style>` 块中定义**，否则其他页面无法使用。

### JavaScript 语法错误导致功能失效

多余 `}` 或 `)` 会导致整个 `<script>`
块失效，页面显示"暂无数据"。**检查方法**：浏览器 F12 Console 看是否有 SyntaxError

### API 路径双重前缀

`apiRequest('/api/in-orders')` 会变成 `/api/api/in-orders`（404）。正确写法：`apiRequest('/in-orders')`

### SQLite 嵌套事务死锁

在已有 `conn = get_db_connection()` 的事务中调用 `InventoryService.reduce_inventory()`，后者会独立
`conn.commit()`，导致死锁。库存扣减必须在调用方的事务内联完成。

### 路由层未透传参数

修改带可选参数的业务逻辑时（如 `summary=True`），**必须同时修改 routes 层透传参数**，否则 service 永远收不到非默认值。先 curl 测通 API 再写前端。

### CREATE TABLE IF NOT EXISTS 不覆盖旧表

修改 `database.py` 表结构后，已存在的表不会被重建。需手动 `DROP TABLE` 或删除数据库文件。

### Excel 导入列索引偏移

`enumerate(headers, 1)` 从 1 开始计数，导致首列错位。应使用 `range(len(headers))` 配 `col_idx + 1` 读取单元格。

### request.get_json() 空请求体导致 500

POST 请求不带 body 或 `Content-Type` 不对时 `request.get_json()` 会抛异常。用 `request.get_json(silent=True)` 或 `request.get_json() or {}`。

### sqlite3.Row 没有 .get() 方法

使用 `cursor.fetchone()` 返回的 `sqlite3.Row` 对象不支持 `.get()` 方法，要用 `row['column']` 直接访问。

 
