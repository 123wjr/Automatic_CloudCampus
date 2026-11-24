#!/usr/bin/env python3
"""
CC_Replayer 计价计算器
======================
输入账号密码，查询课程进度，返回未完成/总数 * 基准价格的金额

用法:
    python price_calculator.py -u 账号 -p 密码
    python price_calculator.py -u 账号 -p 密码 -c 11881 --base-price 20

依赖: pip install requests beautifulsoup4 lxml
"""

import argparse
import sys
from typing import Optional

import requests
from bs4 import BeautifulSoup

from replayer import (
    CLOUDCAMPUS_BASE,
    DEFAULT_COURSE_ID,
    GRADE_URL_TEMPLATE,
    USER_AGENT,
    login,
)

BASE_PRICE = 20.0


def query_progress(cookie_str: str, course_id: int) -> dict:
    headers = {
        "User-Agent": USER_AGENT,
        "Cookie": cookie_str,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    grade_url = GRADE_URL_TEMPLATE.format(base=CLOUDCAMPUS_BASE, course_id=course_id)

    try:
        resp = requests.get(grade_url, headers=headers, timeout=15, allow_redirects=False)
    except requests.RequestException:
        return {"error": "network_error", "incomplete": 0, "total": 0}

    if resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers.get("Location", "")
        if "login" in location.lower():
            return {"error": "cookie_expired", "incomplete": 0, "total": 0}

    if resp.status_code != 200:
        resp = requests.get(grade_url, headers=headers, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            return {"error": f"http_{resp.status_code}", "incomplete": 0, "total": 0}

    soup = BeautifulSoup(resp.text, "lxml")
    if soup.find("input", {"name": "logintoken"}):
        return {"error": "cookie_expired", "incomplete": 0, "total": 0}

    tbody = soup.find("tbody")
    if not tbody:
        return {"incomplete": 0, "total": 0}

    rows = tbody.find_all("tr")

    total_h5p = 0
    incomplete_h5p = 0

    for row in rows:
        if "lastrow" in (row.get("class") or []):
            break

        item_cell = row.select_one(".column-itemname")
        if not item_cell:
            continue

        h5p_span = item_cell.select_one("span[title='H5P']")
        if not h5p_span:
            continue

        total_h5p += 1

        pct_cell = row.select_one("td.column-percentage")
        pct_text = pct_cell.get_text(strip=True) if pct_cell else ""
        if "100.00" not in pct_text:
            incomplete_h5p += 1

    return {"incomplete": incomplete_h5p, "total": total_h5p}


def calculate_price(
    username: str, password: str, course_id: int, base_price: float
) -> Optional[float]:
    user_info = login(username, password)
    if not user_info:
        print(f"[错误] 登录失败: {username}", file=sys.stderr)
        return None

    print(f"[登录] {user_info['nickname']}")

    result = query_progress(user_info["cookie"], course_id)
    if result.get("error"):
        print(f"[错误] 查询进度失败: {result['error']}", file=sys.stderr)
        return None

    incomplete = result["incomplete"]
    total = result["total"]

    print(f"[进度] 未完成: {incomplete} / 总数: {total}")

    if total == 0:
        print("[结果] 无 H5P 任务，金额为 0")
        return 0.0

    price = (incomplete / total) * base_price
    return price


def main():
    parser = argparse.ArgumentParser(
        description="CC_Replayer 计价计算器 — 根据课程进度计算金额",
    )
    parser.add_argument("-u", "--username", required=True, help="账号用户名")
    parser.add_argument("-p", "--password", required=True, help="账号密码")
    parser.add_argument(
        "-c", "--course", type=int, default=DEFAULT_COURSE_ID, help="课程ID"
    )
    parser.add_argument(
        "--base-price",
        type=float,
        default=BASE_PRICE,
        help=f"基准价格 (默认: {BASE_PRICE})",
    )

    args = parser.parse_args()

    price = calculate_price(
        args.username, args.password, args.course, args.base_price
    )
    if price is None:
        sys.exit(1)

    print(f"\n{'=' * 40}")
    print(f"[金额] 未完成/总数 * 基准价格 = {price:.2f} 元")
    print(f"[计算] {price / args.base_price * 100:.1f}% 未完成 × {args.base_price} 元")
    print(f"{'=' * 40}")


if __name__ == "__main__":
    main()
