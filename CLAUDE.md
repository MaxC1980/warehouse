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

## 注意

1. 修改表结构后需手动 `ALTER TABLE` 或删除 `db/warehouse.db`
2. SQL LIKE：`code LIKE '0103%'`（前缀），`name LIKE '%关键词%'`（模糊）
3. `request.get_json()` 失败用 `request.get_json(silent=True) or {}`
4. 禁止使用select *


## 调试

```
playwright-cli open http://localhost:5001/login --browser=chrome --persistent
playwright-cli screenshot
playwright-cli snapshot
```

调试产物放 `debug/` 目录。

## 业务逻辑查看@docs/业务逻辑.md

## 编码规则查看@docs/编码规则.md

 
