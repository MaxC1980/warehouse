# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]              
2. [Step] → verify: [check]              
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

# 以下是项目说明

Flask + SQLite 仓库管理系统。默认账号：`admin` / `admin12345`

## 运行

```
python run.py     # 开发环境（端口5001）                
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
# 使用 cursor.execute()，操作后 conn.commit() 再 conn.close()                
# sqlite3.Row 不支持 .get()，用 row['col'] 直接访问  
# 不使用 PRAGMA foreign_keys = ON，引用检查在 Service 层手动做
```

## 注意

1. 修改表结构后需手动 `ALTER TABLE` 或删除 `db/warehouse.db`
2. SQL LIKE：`code LIKE '0103%'`（前缀），`name LIKE '%关键词%'`（模糊）
3. `request.get_json()` 失败用 `request.get_json(silent=True) or {}`
4. 禁止使用`select *`
5. 不用外键约束，引用检查在业务层（Service）手动做


## 调试

```
playwright-cli open http://localhost:5001/login --browser=chrome --persistent                
playwright-cli screenshot                
playwright-cli snapshot
```

调试产物放 `debug/` 目录。

## 项目日志

会话结束前在 `changelog/`
对应日期文件追加条目总结本次做了什么（功能/修复/改动原因）。

## 业务逻辑查看@docs/业务逻辑.md

 
