#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
cash.py
-------
每個工作日由 GitHub Actions 執行，
抓取 TWSE「三大法人買賣金額統計表」。

資料來源：
https://www.twse.com.tw/rwd/zh/fund/BFI82U

輸出：
cash.json

主要欄位：
- foreign：外資淨買賣（億元）
- trust：投信淨買賣（億元）
- dealer：自營商合計淨買賣（億元）
- total：三大法人合計淨買賣（億元）

自營商 = 自營商（自行買賣）＋自營商（避險）
外資自營商不另外加到三大法人合計。
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


TWSE_URL = "https://www.twse.com.tw/rwd/zh/fund/BFI82U"

# 直接輸出到 Repository 根目錄
# foreign-cash.html 也會從這裡讀取
OUTPUT = Path("cash.json")

TZ = ZoneInfo("Asia/Taipei")

# 最多保留 60 個交易日
KEEP_DAYS = 60

# TWSE API 最多重試 4 次
RETRIES = 4
RETRY_SECONDS = 5


def fetch_twse(target: date) -> dict | None:
    """取得指定日期的 TWSE BFI82U JSON。"""

    params = {
        "date": target.strftime("%Y%m%d"),
        "dayDate": target.strftime("%Y%m%d"),
        "type": "day",
        "response": "json",
    }

    url = f"{TWSE_URL}?{urlencode(params)}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/151 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
    }

    for attempt in range(1, RETRIES + 1):
        try:
            print(
                f"[INFO] Fetch TWSE {target} "
                f"(attempt {attempt}/{RETRIES})"
            )

            req = Request(url, headers=headers)

            with urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8-sig")

            payload = json.loads(raw)

            if payload.get("stat") != "OK":
                print(
                    f"[INFO] TWSE has no data for {target}: "
                    f"{payload.get('stat')}"
                )
                return None

            if not payload.get("data"):
                print(f"[INFO] TWSE returned empty data for {target}")
                return None

            return payload

        except Exception as exc:
            print(
                f"[WARN] TWSE request failed "
                f"({attempt}/{RETRIES}): {exc}",
                file=sys.stderr,
            )

            if attempt < RETRIES:
                time.sleep(RETRY_SECONDS)

    raise RuntimeError(
        f"TWSE API unavailable after {RETRIES} retries"
    )


def to_number(value: str | int | float) -> float:
    """把 TWSE 的數字字串轉成 float。"""

    if isinstance(value, (int, float)):
        return float(value)

    text = (
        str(value)
        .strip()
        .replace(",", "")
        .replace(" ", "")
    )

    if text in {"", "-", "--"}:
        return 0.0

    return float(text)


def find_row(rows: list[list], keywords: tuple[str, ...]) -> list:
    """依名稱找資料列，兼容 TWSE 新舊名稱。"""

    for row in rows:
        if not row:
            continue

        name = str(row[0]).strip()

        if any(keyword in name for keyword in keywords):
            return row

    raise ValueError(
        f"找不到 TWSE 資料列：{keywords}"
    )


def parse_payload(payload: dict, target: date) -> dict:
    """解析 TWSE BFI82U 資料。"""

    rows = payload["data"]

    proprietary = find_row(
        rows,
        ("自營商(自行買賣)",)
    )

    hedge = find_row(
        rows,
        ("自營商(避險)",)
    )

    trust = find_row(
        rows,
        ("投信",)
    )

    foreign = find_row(
        rows,
        (
            "外資及陸資(不含外資自營商)",
            "外資及陸資",
        ),
    )

    # [名稱, 買進, 賣出, 買賣差額]
    proprietary_net = to_number(proprietary[3])
    hedge_net = to_number(hedge[3])
    trust_net = to_number(trust[3])
    foreign_net = to_number(foreign[3])

    dealer_net = proprietary_net + hedge_net
    total_net = foreign_net + trust_net + dealer_net

    result = {
        "date": target.isoformat(),

        "foreign": round(
            foreign_net / 100_000_000,
            2
        ),

        "trust": round(
            trust_net / 100_000_000,
            2
        ),

        "dealer": round(
            dealer_net / 100_000_000,
            2
        ),

        "total": round(
            total_net / 100_000_000,
            2
        ),

        "raw": {
            "foreign_net": int(foreign_net),
            "trust_net": int(trust_net),
            "dealer_proprietary_net": int(proprietary_net),
            "dealer_hedge_net": int(hedge_net),
            "dealer_net": int(dealer_net),
            "total_net": int(total_net),
        },
    }

    return result


def load_history() -> list[dict]:
    """讀取既有 cash.json。"""

    if not OUTPUT.exists():
        print("[INFO] cash.json does not exist yet.")
        return []

    try:
        obj = json.loads(
            OUTPUT.read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:
        print(
            f"[WARN] Cannot read existing cash.json: {exc}",
            file=sys.stderr,
        )
        return []

    history = obj.get("history", [])

    if not isinstance(history, list):
        return []

    return history


def save_history(history: list[dict]) -> None:
    """將資料寫入 Repository 根目錄 cash.json。"""

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # 新 → 舊
    history.sort(
        key=lambda x: x["date"],
        reverse=True
    )

    output = {
        "source": TWSE_URL,
        "unit": "億元",
        "updated_at": datetime.now(TZ).isoformat(),
        "latest": history[0] if history else None,
        "history": history[:KEEP_DAYS],
    }

    OUTPUT.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8",
    )

    print(
        f"[OK] Saved {len(history)} "
        f"trading days to {OUTPUT}"
    )


def main() -> None:

    # 使用台灣時間
    today = datetime.now(TZ).date()

    print(f"[INFO] Taiwan date: {today}")

    history = load_history()

    known_dates = {
        item.get("date")
        for item in history
        if item.get("date")
    }

    # =========================================================
    # 1. 先抓今天
    # =========================================================

    today_data = fetch_twse(today)

    if today_data is not None:

        parsed = parse_payload(
            today_data,
            today
        )

        history = [
            item
            for item in history
            if item.get("date") != parsed["date"]
        ]

        history.append(parsed)
        known_dates.add(parsed["date"])

        print(
            f"[OK] {today} "
            f"外資 {parsed['foreign']:+.2f} 億、"
            f"投信 {parsed['trust']:+.2f} 億、"
            f"自營商 {parsed['dealer']:+.2f} 億、"
            f"三大法人 {parsed['total']:+.2f} 億"
        )

    else:

        print(
            "[INFO] Today has no TWSE BFI82U data."
        )

    # =========================================================
    # 2. 如果不到 10 筆，往前回補
    # =========================================================

    if len(history) < 10:

        print(
            f"[INFO] Need backfill. "
            f"Current history: {len(history)} days"
        )

        cursor = today - timedelta(days=1)

        while len(history) < 10:

            # 最多往前找 60 個日曆日
            if (today - cursor).days > 60:
                print(
                    "[WARN] Backfill exceeded "
                    "60 calendar days."
                )
                break

            if cursor.isoformat() not in known_dates:

                payload = fetch_twse(cursor)

                if payload is not None:

                    parsed = parse_payload(
                        payload,
                        cursor
                    )

                    history = [
                        item
                        for item in history
                        if item.get("date")
                        != parsed["date"]
                    ]

                    history.append(parsed)

                    known_dates.add(
                        parsed["date"]
                    )

                    print(
                        f"[BACKFILL] {cursor} "
                        f"外資 {parsed['foreign']:+.2f} 億、"
                        f"投信 {parsed['trust']:+.2f} 億、"
                        f"自營商 {parsed['dealer']:+.2f} 億、"
                        f"三大法人 {parsed['total']:+.2f} 億"
                    )

            cursor -= timedelta(days=1)

    # =========================================================
    # 3. 排序並保留最近 60 個交易日
    # =========================================================

    history.sort(
        key=lambda x: x["date"],
        reverse=True
    )

    history = history[:KEEP_DAYS]

    # =========================================================
    # 4. 只要有任何歷史資料，就一定建立 cash.json
    # =========================================================

    if history:

        save_history(history)

    else:

        # 如果 TWSE 完全沒有資料，明確讓 Actions 失敗，
        # 不要默默結束造成網頁 404。
        raise RuntimeError(
            "No TWSE data available. "
            "cash.json was not created."
        )


if __name__ == "__main__":
    main()
