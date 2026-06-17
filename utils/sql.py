def escape_like(keyword):
    """转义 SQL LIKE 通配符 % 和 _，防止用户输入被当作通配符"""
    return keyword.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def build_like_clause(columns, keyword, params, prefix=False):
    """构造 LIKE ESCAPE 片段, 追加参数到 params

    Args:
        columns: 字段名列表 (e.g. ['m.code', 'm.name'])
        keyword: 用户输入
        params: 追加到该 list (inout)
        prefix: True 用 'kw%' 前缀匹配, False 用 '%kw%' 模糊匹配 (默认)

    Returns:
        SQL 片段 (含括号, 多列自动 OR)

    Examples:
        >>> params = []
        >>> build_like_clause(['m.code', 'm.name'], '钢', params)
        "(m.code LIKE ? ESCAPE '\\' OR m.name LIKE ? ESCAPE '\\')"
        >>> params
        ['%钢%', '%钢%']

    Note:
        返回的 SQL 中 ESCAPE 子句接 1 字符反斜杠 (SQL 字符串 '\\' 中含 1 字符 \\)。
        不要用 '\\\\' (Python 源 2 字符) — 会触发 SQLite 报 "ESCAPE expression must be a single character"。
    """
    if not columns:
        return ''
    kw = escape_like(keyword)
    pattern = f"{kw}%" if prefix else f"%{kw}%"
    or_parts = [f"{col} LIKE ? ESCAPE '\\'" for col in columns]
    clause = '(' + ' OR '.join(or_parts) + ')'
    for _ in columns:
        params.append(pattern)
    return clause


def build_update_sql(table, data, allowed_fields, id_column='id'):
    """动态构造 UPDATE SQL: 只更新 data 中存在且在白名单的字段

    Args:
        table: 表名
        data: 字段值字典, 必须含 id_column 对应键 (例如 data['id'])
        allowed_fields: 允许更新的字段白名单 (防 SQL 注入和误改敏感字段)
        id_column: WHERE 条件的列名, 默认 'id'

    Returns:
        (sql, params): SQL 字符串和参数列表;
                      若无字段可更新返回 (None, None)
    """
    updates = []
    params = []
    for field in allowed_fields:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])
    if not updates:
        return None, None
    set_clause = ', '.join(updates)
    id_value = data.get(id_column)
    if id_value is None:
        return None, None
    params.append(id_value)
    sql = f"UPDATE {table} SET {set_clause} WHERE {id_column} = ?"
    return sql, params
