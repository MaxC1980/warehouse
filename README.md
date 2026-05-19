# 仓库管理系统

Flask + SQLite 实现的仓库管理后台，支持入库、出库、退库、库存查询等核心功能。

## 快速开始

**默认账号：** `admin` / `admin12345`

### 开发环境

```bash
python run.py
```

访问 http://localhost:5001

### 生产环境

```bash
python app.py
```

访问 http://localhost:5000（使用 waitress）

## 项目结构

| 目录/文件 | 说明 |
|---------|------|
| `routes/` | Flask Blueprint 端点 |
| `services/` | 业务逻辑层 |
| `database.py` | SQLite 连接管理 |
| `templates/` | Jinja2 页面模板 |
| `static/js/app.js` | 前端 API 请求封装（`apiRequest()` 自动前缀 `/api`） |
| `db/warehouse.db` | SQLite 数据库文件 |

## 核心功能

- **入库管理** — 入库单新增、编辑、审核，支持按物料+批次入库
- **出库管理** — 出库单新增、编辑、审核，自动扣减库存
- **退库管理** — 可回用物料退库，净用量自动计算
- **库存查询** — 支持详情/汇总模式，按批次管理库存
- **报表** — 库存汇总、入库明细、出库明细、出入库流水

## 数据库

表结构见 `docs/数据字典.md`，业务逻辑说明见 `docs/业务逻辑.md`。

**注意：** 修改表结构后需删除 `db/warehouse.db` 重建，或手动 `ALTER TABLE`。

## 注意事项

1. SQL LIKE 写法：`code LIKE '0103%'`（前缀匹配），`name LIKE '%关键词%'`（模糊匹配）
2. `sqlite3.Row` 不支持 `.get()`，用 `row['col']` 直接访问
3. 不用外键约束，引用检查在 Service 层手动做
4. 禁止使用 `select *`