#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
cash.py
------
每個工作日由 GitHub Actions 執行，抓取 TWSE「三大法人買賣金額統計表」。

資料來源：
https://www.twse.com.tw/rwd/zh/fund/BFI82U

輸出：
data/three-institutions.json

主要欄位：
- foreign：外資淨買賣（億元）
- trust：投信淨買賣（億元）
- dealer：自營商合計淨買賣（億元）
- total：三大法人合計淨買賣（億元）

自營商 = 自營商（自行買賣）＋自營商（避險）
外資自營商不另外加到三大法人合計，依 TWSE 官方說明處理。
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


TWSE_URL = "https://www.twse.com.tw/rwd/zh/fund/BFI82U"
OUTPUT = Path("data/three-institutions.json")
TZ = ZoneInfo("Asia/Taipei")

# 最多保留 60 個交易日，網頁目前只需要最近 10 個。
KEEP_DAYS = 60

# TWSE 偶爾會短暫沒有回應；每次最多重試 4 次。
RETRIES = 4
RETRY_SECONDS = 5


def fetch_twse(target: date) -> dict | None:
    """取得指定日期的 TWSE BFI82U JSON。非交易日/尚無資料回傳 None。"""

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
            "AppleWebKit/537.36 Chrome/151 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
    }

    for attempt in range(1, RETRIES + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8-sig")

            payload = json.loads(raw)

            if payload.get("stat") != "OK":
                return None

            if not payload.get("data"):
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

    raise RuntimeError("TWSE API unavailable after retries")


def to_number(value: str | int | float) -> float:
    """把 TWSE 的千分位字串轉成數字。"""
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", "").replace(" ", "")

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

    raise ValueError(f"找不到 TWSE 資料列：{keywords}")


def parse_payload(payload: dict, target: date) -> dict:
    rows = payload["data"]

    # 2026/05/29 後 TWSE 格式有調整，因此用名稱找列，
    # 不依賴固定的 row index。
    proprietary = find_row(rows, ("自營商(自行買賣)",))
    hedge = find_row(rows, ("自營商(避險)",))
    trust = find_row(rows, ("投信",))
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
        "foreign": round(foreign_net / 100_000_000, 2),
        "trust": round(trust_net / 100_000_000, 2),
        "dealer": round(dealer_net / 100_000_000, 2),
        "total": round(total_net / 100_000_000, 2),

        # 保留原始元數字，之後若要核對資料會比較方便。
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
    if not OUTPUT.exists():
        return []

    try:
        obj = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except Exception:
        return []

    history = obj.get("history", [])

    if not isinstance(history, list):
        return []

    return history


def save_history(history: list[dict]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # 新 → 舊
    history.sort(key=lambda x: x["date"], reverse=True)

    output = {
        "source": TWSE_URL,
        "unit": "億元",
        "updated_at": __import__("datetime").datetime.now(TZ).isoformat(),
        "latest": history[0] if history else None,
        "history": history[:KEEP_DAYS],
    }

    OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    today = date.today()  # runner 的系統日期通常為 UTC；下面實際用台灣日期
    today = __import__("datetime").datetime.now(TZ).date()

    print(f"[INFO] Taiwan date: {today}")

    history = load_history()
    known_dates = {item.get("date") for item in history}

    # 先抓今天。
    today_data = fetch_twse(today)

    if today_data is not None:
        parsed = parse_payload(today_data, today)

        # 取代同一天舊資料。
        history = [
            item for item in history
            if item.get("date") != parsed["date"]
        ]
        history.append(parsed)

        print(
            f"[OK] {today} "
            f"外資 {parsed['foreign']:+.2f} 億、"
            f"投信 {parsed['trust']:+.2f} 億、"
            f"自營商 {parsed['dealer']:+.2f} 億、"
            f"三大法人 {parsed['total']:+.2f} 億"
        )
    else:
        # 週末、國定假日或資料尚未發布時，不建立假資料。
        print(
            "[INFO] Today has no TWSE BFI82U data. "
            "Likely non-trading day or data not published yet."
        )

    # 如果資料庫還沒有 10 筆，第一次執行時向前回補最近交易日。
    existing_trading_days = len(history)

    if existing_trading_days < 10:
        cursor = today - timedelta(days=1)

        while len(history) < 10:
            # 最多往前找 30 個日曆日，避免異常情況無限迴圈。
            if (today - cursor).days > 30:
                break

            if cursor.isoformat() not in known_dates:
                payload = fetch_twse(cursor)

                if payload is not None:
                    parsed = parse_payload(payload, cursor)
                    history = [
                        item for item in history
                        if item.get("date") != parsed["date"]
                    ]
                    history.append(parsed)
                    known_dates.add(parsed["date"])

                    print(
                        f"[BACKFILL] {cursor} "
                        f"{parsed['total']:+.2f} 億元"
                    )

            cursor -= timedelta(days=1)

    # 只保留最近 KEEP_DAYS 筆交易日。
    history.sort(key=lambda x: x["date"], reverse=True)
    history = history[:KEEP_DAYS]

    if history:
        save_history(history)
        print(f"[OK] Saved {len(history)} trading days to {OUTPUT}")
    else:
        print("[INFO] No data to save.")


if __name__ == "__main__":
    main()
