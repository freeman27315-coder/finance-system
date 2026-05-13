"""测试 Playwright 抓取里的纯解析函数 (CEO 2026-05-12 PR D)。

不需要真实浏览器, 只测正则 + 解析逻辑。真实端到端测试需要 CEO 的真账号
+ 信任设备的浏览器 user_data,在 CI 上跑不了。
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from src.services.xbox_playwright import (
    _DATE_RE,
    _ORDER_NO_RE,
    _PRICE_RE,
    _parse_one_card,
)


# 截图里看到的真实卡片文本(CEO 2026-05-12 截图)
SAMPLE_CARD_USD = """May 11, 2026 | Order number 8035392088
80 Robux
USD$0.99
Completed
Total USD$0.99
Paid with Microsoft account
Show details"""

SAMPLE_CARD_USD_500 = """May 11, 2026 | Order number 6420411507
500 Robux
USD$4.99
Completed
Total USD$4.99
Paid with Microsoft account
Show details"""

SAMPLE_CARD_GBP = """Jul 15, 2026 | Order number 1234567890
1000 Robux
GBP£8.49
Completed
Total GBP£8.49
Paid with Microsoft account
Show details"""


def test_regex_order_no():
    assert _ORDER_NO_RE.search(SAMPLE_CARD_USD).group(1) == "8035392088"
    assert _ORDER_NO_RE.search(SAMPLE_CARD_GBP).group(1) == "1234567890"


def test_regex_date():
    m = _DATE_RE.search(SAMPLE_CARD_USD)
    assert m.group(1) == "May"
    assert m.group(2) == "11"
    assert m.group(3) == "2026"


def test_regex_price_usd():
    m = _PRICE_RE.search(SAMPLE_CARD_USD)
    assert "USD" in m.group(1) or "$" in m.group(1)
    assert m.group(2) == "0.99"


def test_regex_price_gbp():
    m = _PRICE_RE.search(SAMPLE_CARD_GBP)
    assert "GBP" in m.group(1) or "£" in m.group(1)
    assert m.group(2) == "8.49"


def test_parse_one_card_usd():
    order = _parse_one_card(SAMPLE_CARD_USD)
    assert order is not None
    assert order.order_no == "8035392088"
    assert order.amount_local == Decimal("0.99")
    assert order.currency_local == "USD"
    assert order.order_at == datetime(2026, 5, 11, 12, 0, 0)
    # CEO 2026-05-12: 商品名也要抓到
    assert order.product_name == "80 Robux"


def test_parse_one_card_extracts_500_robux_product_name():
    order = _parse_one_card(SAMPLE_CARD_USD_500)
    assert order is not None
    assert order.product_name == "500 Robux"


def test_parse_one_card_gbp():
    order = _parse_one_card(SAMPLE_CARD_GBP)
    assert order is not None
    assert order.order_no == "1234567890"
    assert order.amount_local == Decimal("8.49")
    assert order.currency_local == "GBP"
    assert order.order_at == datetime(2026, 7, 15, 12, 0, 0)
    assert order.product_name == "1000 Robux"


def test_parse_one_card_500_robux():
    """金额带千分位的兼容(Microsoft 偶尔 4 位数订单显示 "USD$1,234.99")。"""
    order = _parse_one_card(SAMPLE_CARD_USD_500)
    assert order is not None
    assert order.order_no == "6420411507"
    assert order.amount_local == Decimal("4.99")


def test_parse_one_card_missing_fields_returns_none():
    assert _parse_one_card("garbage text") is None
    assert _parse_one_card("Order number 12345 (no date or price)") is None


def test_parse_one_card_thousand_separator():
    """4 位数金额带逗号(USD$1,234.56)解析。"""
    sample = "May 1, 2026 | Order number 9999999999\nXBOX Pass Ultimate\nUSD$1,234.56"
    order = _parse_one_card(sample)
    assert order is not None
    assert order.amount_local == Decimal("1234.56")
