def escape_like(keyword):
    """转义 SQL LIKE 通配符 % 和 _，防止用户输入被当作通配符"""
    return keyword.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


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
