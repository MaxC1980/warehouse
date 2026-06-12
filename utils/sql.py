def escape_like(keyword):
    """转义 SQL LIKE 通配符 % 和 _，防止用户输入被当作通配符"""
    return keyword.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
