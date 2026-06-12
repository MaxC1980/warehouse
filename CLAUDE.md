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
- **Services** (`services/`) - 业务逻辑
- **Database** (`database.py`) - SQLite 连接，`get_db_connection()`
- **Templates** (`templates/`) - Jinja2 模板
- **utils/pagination.py** - `get_per_page(default, max_value)` 分页上限工具
- **utils/decorators.py** - `@require_permission(module, action)` 权限装饰器
- **utils/sql.py** - `escape_like()` SQL LIKE 通配符转义
- **services/permission_service.py** - RBAC 权限服务（角色 CRUD、权限查询、用户分配）

## API 调用

`apiRequest()` 在 `static/js/app.js`，**自动前缀 `/api`**，发送 session cookie：

```javascript
const data = await apiRequest('/in-orders/detail?page=1');  // 正确
// const data = await apiRequest('/api/in-orders/detail');   // 错误
```

## 数据库

```
with get_db_connection() as conn:
    cursor = conn.cursor()
    # 操作后自动 conn.commit()
# 异常时 conn 自动关闭，无需手动 close()
# sqlite3.Row 不支持 .get()，用 row['col'] 直接访问
# 不使用 PRAGMA foreign_keys = ON，引用检查在 Service 层手动做
```

## 权限（RBAC）

基于角色的访问控制，替代旧的 3 级数值权限。

- 4 张表：`role`、`user_role`、`permission`、`role_permission`
- 29 条权限：13 模块 × 3 动作（view/edit/approve），部分模块只有 view 或 manage
- 默认角色：管理员（全部）、操作员（view+edit）、查看员（仅 view）
- 路由层：`@require_permission('module', 'action')` 装饰器
- 页面层：`before_request` 路径映射拦截无权限页面
- 模板层：`has_perm(module, 'action')` 控制菜单和按钮显隐
- 管理页面：`/admin/roles-page`（角色管理）、`/admin/users-page`（用户管理）
- 新增模块需改：`database.py`（种子数据）+ `create_app.py`（路径映射）+ `base.html`（菜单）+ 路由装饰器 + 模板按钮

## 安全

- `SECRET_KEY`：不硬编码，每次启动随机生成（`secrets.token_hex(32)`），重启后 session 失效。设环境变量 `SECRET_KEY` 可持久化
- 登录限流：IP + 账号双维度，5 次失败锁定 15 分钟
- 其他安全规范见 @docs/通用开发规范.md

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
## 代码质量改进记录查看@docs/代码质量改进记录.md
## 通用开发规范查看@docs/通用开发规范.md