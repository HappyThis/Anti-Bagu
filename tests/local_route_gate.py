from __future__ import annotations

import re


THINK_PHRASES = (
    "写代码",
    "写一段代码",
    "写一个",
    "写一条 sql",
    "实现一个",
    "算法求解",
    "输出什么",
    "执行结果",
    "计算过程",
    "请计算",
    "估算",
    "系统设计",
    "设计一个",
    "需要考虑",
    "给定一个无序数组",
    "给定若干区间",
)

NUMERIC_REASONING_PHRASES = (
    "哪个更大",
    "哪个大",
    "多少",
    "qps",
    "容量",
    "峰值",
    "概率",
)


def requires_thinking(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    if any(phrase in normalized for phrase in THINK_PHRASES):
        return True

    has_number = bool(re.search(r"\d|[一二三四五六七八九十百千万亿]", normalized))
    if has_number and any(phrase in normalized for phrase in NUMERIC_REASONING_PHRASES):
        return True

    return False
