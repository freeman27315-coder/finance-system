"""时间工具：所有系统时间统一使用中国时区(UTC+8)。

设计原则：
1. 所有写入 DB 的 datetime 都是 ``china_now()`` 返回的 naive 中国本地时间
   （tzinfo=None,但语义为 UTC+8）
2. 来自千牛 Excel 的 confirmed_at / shipped_at 等天然就是中国本地,不再转换
3. 不再使用 ``func.now()`` (SQLite CURRENT_TIMESTAMP 是 UTC) 和
   ``datetime.now(timezone.utc)``,以避免和 Excel 数据混 8 小时
4. 用 ``timezone(timedelta(hours=8))`` 而非 ZoneInfo("Asia/Shanghai"),
   避免 Windows Python 缺 tzdata 的问题（中国不再实施夏令时,固定偏移即可）
5. ``DateTime(timezone=True)`` 列定义保留（在 SQLite 上是 no-op,
   PostgreSQL 兼容时再考虑）
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

CHINA_TZ = timezone(timedelta(hours=8), name="UTC+8")


def china_now() -> datetime:
    """返回当前中国时间（naive datetime,无 tz 信息,但语义为中国本地）。

    用固定 UTC+8 取时,即便服务器在非中国时区也能得到中国时间。
    返回 naive 是为了与千牛 Excel 时间（也是 naive 中国）保持比较语义一致。
    """
    return datetime.now(CHINA_TZ).replace(tzinfo=None)
