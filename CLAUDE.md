# CLAUDE.md

Behavioral guidelines. Merge with project instructions as needed.

**Tradeoff:** Bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If simpler approach exists, say so. Push back when warranted.
- If something unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask: "Would senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

Test: Every changed line traces directly to user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**Guidelines working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

# 以下是项目说明

Flask + SQLite 仓库管理系统。默认账号：`admin` / `admin12345`

## 运行

```
先清除python进程再python run.py     # 开发环境（端口5001）
python app.py      # 生产环境（端口5000，用 waitress）
```

## 架构

- **create_app.py** - 应用工厂，`app.py` 和 `run.py` 调用 `create_app(config_class)`
- **Routes** (`routes/`) - Flask Blueprint 端点
  - 页面路由: `routes/pages.py` (Blueprint `pages_bp`)
  - API 路由: `routes/*.py` (Blueprint `*_bp`)
- **Services** (`services/`) - 业务逻辑
  - `permission_service.py` - RBAC 权限服务（角色 CRUD、权限查询、用户分配）
  - `user_service.py` - 用户管理（创建/删除/重置密码/角色分配）
- **Database** (`database.py`) - SQLite 连接，`get_db_connection()`
- **Templates** (`templates/`) - Jinja2 模板
- **utils/pagination.py** - `get_per_page(default, max_value)` 分页上限工具
- **utils/decorators.py` - `@require_permission(module, action)` 权限装饰器, `@login_required` 页面登录校验
- **utils/sql.py** - `escape_like()` 通配符转义, `build_update_sql()` 动态 UPDATE 工具
- **utils/page_permissions.py** - 页面 endpoint → (module, action) 权限映射

## 数据库

```
with get_db_connection() as conn:
    cursor = conn.cursor()
    # 操作后自动 conn.commit()
# 异常时 conn 自动关闭，无需手动 close()
# sqlite3.Row 不支持 .get()，用 row['col'] 直接访问
# 不使用 PRAGMA foreign_keys = ON，引用检查在 Service 层手动做
# 密码用 werkzeug hash 存储, 旧明文首次登录自动升级 (无新列)
# in_order_item 唯一约束: (order_id, material_id, batch_no) — 跨单允许, 单内禁止重复
```

## 权限（RBAC）

详见 @docs/权限管理.md（三层防护: 路由/页面/模板, 新增模块需改 5 个位置）

## 安全

- `SECRET_KEY`：不硬编码，每次启动随机生成（`secrets.token_hex(32)`），重启后 session 失效。设环境变量 `SECRET_KEY` 可持久化
- 登录限流：IP + 账号双维度，5 次失败锁定 15 分钟，LRUDict(maxsize=10000) 防内存泄漏
- 权限检查从 `session.permissions` 查, 不走 DB, 权限变更后需重登录生效（见 docs/代码质量改进记录.md §30）
- 密码用 werkzeug `generate_password_hash` 存储, 首次登录自动迁移明文 → hash

## 注意

1. 修改表结构后需手动 `ALTER TABLE` 或删除 `db/warehouse.db`
2. SQL LIKE：`code LIKE '0103%'`（前缀），`name LIKE '%关键词%'`（模糊）
3. 不用外键约束，引用检查在业务层（Service）手动做
4. 下拉框onchange()就load数据

## 调试

```
playwright-cli open http://localhost:5001/login --browser=chrome --persistent
playwright-cli screenshot
playwright-cli snapshot
```

调试产物放 `debug/` 目录。

## 业务逻辑查看@docs/业务逻辑.md
## 新增模块操作指南查看@docs/新增模块操作指南.md
## 权限管理查看@docs/权限管理.md
## 代码质量改进记录查看@docs/代码质量改进记录.md
## 通用开发规范查看@docs/通用开发规范.md