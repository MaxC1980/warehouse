"""版本信息工具

通过 git 命令读取提交 hash 和日期,作为版本显示。
非 git 环境或命令失败时回退到静态版本。
"""
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# 静态版本号: 主版本号手动维护, 提交 hash/日期由 git 自动注入
STATIC_VERSION = 'v0.1.0'


def _run_git(*args):
    """在项目根目录执行 git 命令, 失败返回 None"""
    try:
        result = subprocess.run(
            ['git', *args],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug('git 命令失败: %s', e)
    return None


def get_version_info():
    """返回版本信息字典: version, commit, date, full

    commit: 短 hash (7 位) 或 None
    date:   提交日期 (YYYY-MM-DD) 或 None
    full:   显示用字符串, 例如 "v0.1.0 (a1b2c3d · 2026-06-15)"
    """
    commit = _run_git('rev-parse', '--short', 'HEAD')
    date = _run_git('log', '-1', '--format=%cd', '--date=short')

    if commit and date:
        full = f'{STATIC_VERSION} ({commit} · {date})'
    elif commit:
        full = f'{STATIC_VERSION} ({commit})'
    else:
        full = STATIC_VERSION

    return {
        'version': STATIC_VERSION,
        'commit': commit,
        'date': date,
        'full': full,
    }