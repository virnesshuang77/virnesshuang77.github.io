# -*- coding: utf-8 -*-
"""
credit.py
=========
TWSE 融資融券資料更新程式

輸出：
    credit_rank.json

本版重點修正：
1. 優先使用 TWSE 官方 MI_MARGN 網頁 API。
2. 不再把「HTTP 200 / stat=OK」誤判成「有可解析資料」。
3. 若某個 endpoint 回傳空資料，會繼續嘗試下一個 endpoint。
4. 個股融資增減：
       今日融資餘額 - 前日融資餘額
   2330 台積電 2026/08/26：
       27,677 - 27,969 = -292 張
5. 個股融資增減金額：
       融資增減張數 × 收盤價 × 1000
6. 個股融券增減：
       今日融券餘額 - 前日融券餘額
7. 全市場融資增減：
       官方「融資金額(仟元)」
       今日餘額 - 前日餘額，再 × 1000
8. 全市場融券增減：
       官方「融券(交易單位)」
       今日餘額 - 前日餘額
9. update_time 固定為 21:00:00。
"""

import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

import requests


# ============================================================
# 基本設定
# ============================================================

OUTPUT_FILE = Path("credit_rank.json")

# 注意：
# 官方 exchangeReport endpoint 放最前面。
# openapi.twse.com.tw 的 MI_MARGN 有時 HTTP 200，
# 但回傳結構不是這支程式需要的 tables 結構。
MARGIN_URLS = [
    "https://www.twse.com.tw/exchangeReport/MI_MARGN",
    "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN",
    "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN",
]

PRICE_URLS = [
    "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL",
    "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL",
    "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
    "https://www.twse.com.tw/exchangeReport/MI_INDEX",
    "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}


# ============================================================
# HTTP
# ============================================================

def get_json(url, params=None, timeout=30):
    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=timeout,
    )

    response.raise_for_status()

    text = response.text.strip()

    if not text:
        raise RuntimeError("API 回傳空白內容")

    if text.startswith("<"):
        raise RuntimeError("API 回傳 HTML，不是 JSON")

    return response.json()


# ============================================================
# 數字
# ============================================================

def to_number(value):
    if value is None:
        return 0.0

    text = str(value).strip()

    if text in (
        "",
        "--",
        "---",
        "—",
        "－",
        "None",
        "null",
    ):
        return 0.0

    text = (
        text
        .replace(",", "")
        .replace(" ", "")
        .replace("％", "")
        .replace("%", "")
    )

    try:
        return float(text)
    except Exception:
        return 0.0


def clean_stock_id(value):
    text = str(value or "").strip()

    if text.endswith(".0"):
        text = text[:-2]

    if not text.isdigit():
        return ""

    if not (4 <= len(text) <= 6):
        return ""

    return text


# ============================================================
# 最近工作日
# ============================================================

def get_candidate_dates():
    today = datetime.now()
    result = []

    for i in range(10):
        d = today - timedelta(days=i)

        if d.weekday() >= 5:
            continue

        result.append(d.strftime("%Y%m%d"))

    return result


# ============================================================
# TWSE tables 正規化
# ============================================================

def get_table_objects(data):
    result = []

    if not isinstance(data, dict):
        return result

    # --------------------------------------------------------
    # 新版 tables
    # --------------------------------------------------------
    tables = data.get("tables", [])

    if isinstance(tables, list):

        for table in tables:

            if not isinstance(table, dict):
                continue

            fields = table.get("fields", [])
            rows = table.get("data", [])

            if not isinstance(fields, list):
                continue

            if not isinstance(rows, list):
                rows = []

            result.append(
                {
                    "title": str(
                        table.get("title", "")
                    ),
                    "fields": [
                        str(x).strip()
                        for x in fields
                    ],
                    "data": rows,
                }
            )

    if result:
        return result

    # --------------------------------------------------------
    # 舊版 creditList
    # --------------------------------------------------------
    credit_list = data.get("creditList", [])

    if isinstance(credit_list, list):

        for block in credit_list:

            if not isinstance(block, list):
                continue

            if len(block) < 2:
                continue

            header = block[0]

            if not isinstance(header, list):
                continue

            result.append(
                {
                    "title": "",
                    "fields": [
                        str(x).strip()
                        for x in header
                    ],
                    "data": block[1:],
                }
            )

    return result


def find_indices(fields, name):
    return [
        i
        for i, value in enumerate(fields)
        if str(value).strip() == name
    ]


# ============================================================
# 判斷 MI_MARGN 是否真的有資料
# ============================================================

def is_valid_margin_payload(data):
    """
    很重要：

    不能只檢查：
        stat == OK

    因為 OpenAPI 有可能 HTTP 200 / stat OK，
    但內容不是本程式需要的完整 MI_MARGN tables。

    必須真的找到：
        1. 市場總表
        2. 融資融券彙總個股表
    """

    if not isinstance(data, dict):
        return False

    if data.get("stat") != "OK":
        return False

    tables = get_table_objects(data)

    if not tables:
        return False

    has_market = False
    has_stock = False

    for table in tables:

        fields = table["fields"]
        rows = table["data"]
        title = table["title"]

        # 市場總表
        if (
            "項目" in fields
            and "前日餘額" in fields
            and "今日餘額" in fields
        ):
            for row in rows:

                if not isinstance(row, list):
                    continue

                if "項目" not in fields:
                    continue

                idx = fields.index("項目")

                if idx >= len(row):
                    continue

                item = str(row[idx]).strip()

                if item in (
                    "融資(交易單位)",
                    "融券(交易單位)",
                    "融資金額(仟元)",
                ):
                    has_market = True
                    break

        # 個股表
        if (
            "代號" in fields
            and "名稱" in fields
            and len(find_indices(fields, "前日餘額")) >= 2
            and len(find_indices(fields, "今日餘額")) >= 2
        ):
            has_stock = True

        # title 也作為輔助
        if "融資融券彙總" in title:
            has_stock = True

    return has_market and has_stock


# ============================================================
# 取得 MI_MARGN
# ============================================================

def fetch_margin(date):

    params = {
        "date": date,
        "selectType": "ALL",
        "response": "json",
    }

    last_error = None

    for url in MARGIN_URLS:

        try:

            print(
                f"[INFO] 嘗試 API：{url}"
            )

            data = get_json(
                url,
                params=params,
                timeout=30,
            )

            if is_valid_margin_payload(data):

                print(
                    f"[OK] 取得完整 MI_MARGN："
                    f"{url}"
                )

                return data

            print(
                f"[WARN] {date} API 有回應，"
                f"但沒有可解析的完整 MI_MARGN 資料："
                f"{url}"
            )

            last_error = RuntimeError(
                "API 回應成功但缺少完整 MI_MARGN tables"
            )

        except Exception as e:

            last_error = e

            print(
                f"[WARN] API 失敗："
                f"{url} -> {e}"
            )

    raise RuntimeError(
        f"所有 MI_MARGN API 都無法取得完整資料："
        f"{last_error}"
    )


# ============================================================
# 市場總表
# ============================================================

def parse_market_summary(data):

    tables = get_table_objects(data)

    target = None

    for table in tables:

        fields = table["fields"]
        rows = table["data"]

        if (
            "項目" in fields
            and "前日餘額" in fields
            and "今日餘額" in fields
        ):

            item_idx = fields.index("項目")

            for row in rows:

                if not isinstance(row, list):
                    continue

                if item_idx >= len(row):
                    continue

                title = str(
                    row[item_idx]
                ).strip()

                if title in (
                    "融資(交易單位)",
                    "融券(交易單位)",
                    "融資金額(仟元)",
                ):
                    target = table
                    break

        if target is not None:
            break

    if target is None:
        raise RuntimeError(
            "找不到 MI_MARGN「信用交易統計」市場總表"
        )

    fields = target["fields"]
    rows = target["data"]

    item_idx = fields.index("項目")

    previous_indices = find_indices(
        fields,
        "前日餘額",
    )

    today_indices = find_indices(
        fields,
        "今日餘額",
    )

    if not previous_indices or not today_indices:
        raise RuntimeError(
            "市場總表缺少前日餘額/今日餘額"
        )

    previous_idx = previous_indices[0]
    today_idx = today_indices[0]

    short_row = None
    margin_amount_row = None

    for row in rows:

        if not isinstance(row, list):
            continue

        if max(
            item_idx,
            previous_idx,
            today_idx,
        ) >= len(row):
            continue

        title = str(
            row[item_idx]
        ).strip()

        if title == "融券(交易單位)":
            short_row = row

        elif title == "融資金額(仟元)":
            margin_amount_row = row

    if short_row is None:
        raise RuntimeError(
            "找不到市場「融券(交易單位)」"
        )

    if margin_amount_row is None:
        raise RuntimeError(
            "找不到市場「融資金額(仟元)」"
        )

    # --------------------------------------------------------
    # 全市場融資金額
    # TWSE 單位：仟元
    # 最後轉成元
    # --------------------------------------------------------

    margin_previous_k = to_number(
        margin_amount_row[previous_idx]
    )

    margin_today_k = to_number(
        margin_amount_row[today_idx]
    )

    margin_change_amount = (
        margin_today_k
        - margin_previous_k
    ) * 1000

    # --------------------------------------------------------
    # 全市場融券
    # --------------------------------------------------------

    short_previous = to_number(
        short_row[previous_idx]
    )

    short_today = to_number(
        short_row[today_idx]
    )

    short_change = (
        short_today
        - short_previous
    )

    print()
    print("======================================")
    print("官方市場總表")
    print("======================================")

    print(
        f"融資金額前日："
        f"{margin_previous_k:,.0f} 仟元"
    )

    print(
        f"融資金額今日："
        f"{margin_today_k:,.0f} 仟元"
    )

    print(
        f"融資增減："
        f"{margin_change_amount:+,.0f} 元"
    )

    print(
        f"融資增減："
        f"{margin_change_amount / 100_000_000:+,.2f} 億元"
    )

    print(
        f"融券前日："
        f"{short_previous:,.0f} 張"
    )

    print(
        f"融券今日："
        f"{short_today:,.0f} 張"
    )

    print(
        f"融券增減："
        f"{short_change:+,.0f} 張"
    )

    print("======================================")
    print()

    return {
        "margin_change_amount": (
            margin_change_amount
        ),
        "short_change": int(
            short_change
        ),
    }


# ============================================================
# 找個股表
# ============================================================

def find_stock_table(data):

    tables = get_table_objects(data)

    # 優先找 title
    for table in tables:

        title = table["title"]
        fields = table["fields"]

        if (
            "融資融券彙總" in title
            and "代號" in fields
            and "名稱" in fields
            and len(
                find_indices(
                    fields,
                    "前日餘額",
                )
            ) >= 2
            and len(
                find_indices(
                    fields,
                    "今日餘額",
                )
            ) >= 2
        ):
            return table

    # 再用欄位結構找
    for table in tables:

        fields = table["fields"]

        if (
            "代號" in fields
            and "名稱" in fields
            and len(
                find_indices(
                    fields,
                    "前日餘額",
                )
            ) >= 2
            and len(
                find_indices(
                    fields,
                    "今日餘額",
                )
            ) >= 2
            and "現金償還" in fields
            and "現券償還" in fields
        ):
            return table

    return None


# ============================================================
# 個股資料
# ============================================================

def parse_stock_rows(data):

    table = find_stock_table(data)

    if table is None:
        raise RuntimeError(
            "MI_MARGN 找不到「融資融券彙總 (全部)」個股表"
        )

    fields = table["fields"]
    rows = table["data"]

    stock_id_idx = fields.index("代號")
    stock_name_idx = fields.index("名稱")

    buy_indices = find_indices(
        fields,
        "買進",
    )

    sell_indices = find_indices(
        fields,
        "賣出",
    )

    previous_indices = find_indices(
        fields,
        "前日餘額",
    )

    today_indices = find_indices(
        fields,
        "今日餘額",
    )

    cash_redeem_indices = find_indices(
        fields,
        "現金償還",
    )

    short_redeem_indices = find_indices(
        fields,
        "現券償還",
    )

    if len(buy_indices) < 2:
        raise RuntimeError(
            "個股表缺少兩組「買進」欄位"
        )

    if len(sell_indices) < 2:
        raise RuntimeError(
            "個股表缺少兩組「賣出」欄位"
        )

    if len(previous_indices) < 2:
        raise RuntimeError(
            "個股表缺少兩組「前日餘額」欄位"
        )

    if len(today_indices) < 2:
        raise RuntimeError(
            "個股表缺少兩組「今日餘額」欄位"
        )

    if not cash_redeem_indices:
        raise RuntimeError(
            "個股表缺少「現金償還」欄位"
        )

    if not short_redeem_indices:
        raise RuntimeError(
            "個股表缺少「現券償還」欄位"
        )

    # --------------------------------------------------------
    # 第一組 = 融資
    # 第二組 = 融券
    # --------------------------------------------------------

    margin_buy_idx = buy_indices[0]
    short_buy_idx = buy_indices[1]

    margin_sell_idx = sell_indices[0]
    short_sell_idx = sell_indices[1]

    margin_previous_idx = previous_indices[0]
    short_previous_idx = previous_indices[1]

    margin_today_idx = today_indices[0]
    short_today_idx = today_indices[1]

    margin_redeem_idx = cash_redeem_indices[0]
    short_redeem_idx = short_redeem_indices[0]

    print(
        "[OK] 個股欄位位置："
    )

    print(
        f"代號={stock_id_idx}, "
        f"名稱={stock_name_idx}"
    )

    print(
        f"融資："
        f"買進={margin_buy_idx}, "
        f"賣出={margin_sell_idx}, "
        f"現償={margin_redeem_idx}, "
        f"前日={margin_previous_idx}, "
        f"今日={margin_today_idx}"
    )

    print(
        f"融券："
        f"買進={short_buy_idx}, "
        f"賣出={short_sell_idx}, "
        f"現券={short_redeem_idx}, "
        f"前日={short_previous_idx}, "
        f"今日={short_today_idx}"
    )

    result = []

    required = [
        stock_id_idx,
        stock_name_idx,
        margin_buy_idx,
        margin_sell_idx,
        margin_redeem_idx,
        margin_previous_idx,
        margin_today_idx,
        short_buy_idx,
        short_sell_idx,
        short_redeem_idx,
        short_previous_idx,
        short_today_idx,
    ]

    max_required = max(required)

    for row in rows:

        if not isinstance(row, list):
            continue

        if max_required >= len(row):
            continue

        stock_id = clean_stock_id(
            row[stock_id_idx]
        )

        if not stock_id:
            continue

        stock_name = str(
            row[stock_name_idx]
        ).strip()

        margin_buy = to_number(
            row[margin_buy_idx]
        )

        margin_sell = to_number(
            row[margin_sell_idx]
        )

        margin_redeem = to_number(
            row[margin_redeem_idx]
        )

        margin_previous = to_number(
            row[margin_previous_idx]
        )

        margin_today = to_number(
            row[margin_today_idx]
        )

        short_buy = to_number(
            row[short_buy_idx]
        )

        short_sell = to_number(
            row[short_sell_idx]
        )

        short_redeem = to_number(
            row[short_redeem_idx]
        )

        short_previous = to_number(
            row[short_previous_idx]
        )

        short_today = to_number(
            row[short_today_idx]
        )

        result.append(
            {
                "stock_id": stock_id,
                "stock_name": stock_name,

                "margin_buy": margin_buy,
                "margin_sell": margin_sell,
                "margin_redeem": margin_redeem,

                "margin_previous": margin_previous,
                "margin_today": margin_today,

                "short_buy": short_buy,
                "short_sell": short_sell,
                "short_redeem": short_redeem,

                "short_previous": short_previous,
                "short_today": short_today,
            }
        )

    print(
        f"[OK] 成功解析 "
        f"{len(result)} 筆融資融券股票"
    )

    # --------------------------------------------------------
    # 2330 台積電檢查
    # --------------------------------------------------------

    for item in result:

        if item["stock_id"] == "2330":

            margin_change = (
                item["margin_today"]
                - item["margin_previous"]
            )

            short_change = (
                item["short_today"]
                - item["short_previous"]
            )

            print()
            print("======================================")
            print("2330 台積電資料驗證")
            print("======================================")

            print(
                f"融資買進："
                f"{item['margin_buy']:,.0f} 張"
            )

            print(
                f"融資賣出："
                f"{item['margin_sell']:,.0f} 張"
            )

            print(
                f"融資現償："
                f"{item['margin_redeem']:,.0f} 張"
            )

            print(
                f"融資前日餘額："
                f"{item['margin_previous']:,.0f} 張"
            )

            print(
                f"融資今日餘額："
                f"{item['margin_today']:,.0f} 張"
            )

            print(
                f"融資增減："
                f"{margin_change:+,.0f} 張"
            )

            print(
                f"融券前日餘額："
                f"{item['short_previous']:,.0f} 張"
            )

            print(
                f"融券今日餘額："
                f"{item['short_today']:,.0f} 張"
            )

            print(
                f"融券增減："
                f"{short_change:+,.0f} 張"
            )

            print("======================================")
            print()

            break

    return result


# ============================================================
# 收盤價
# ============================================================

def parse_price_table(data):

    prices = {}

    # --------------------------------------------------------
    # STOCK_DAY_ALL / OpenAPI
    # --------------------------------------------------------

    if isinstance(data, list):

        for row in data:

            if not isinstance(row, dict):
                continue

            stock_id = clean_stock_id(
                row.get("Code")
                or row.get("證券代號")
            )

            if not stock_id:
                continue

            price = (
                row.get("ClosingPrice")
                or row.get("收盤價")
            )

            if price in (None, ""):
                continue

            value = to_number(price)

            if value > 0:
                prices[stock_id] = value

        return prices

    if not isinstance(data, dict):
        return prices

    # --------------------------------------------------------
    # MI_INDEX
    # --------------------------------------------------------

    tables = data.get("tables", [])

    if not isinstance(tables, list):
        return prices

    for table in tables:

        if not isinstance(table, dict):
            continue

        fields = table.get("fields", [])
        rows = table.get("data", [])

        if not isinstance(fields, list):
            continue

        if not isinstance(rows, list):
            continue

        fields = [
            str(x).strip()
            for x in fields
        ]

        code_idx = None
        price_idx = None

        for name in (
            "證券代號",
            "代號",
            "Code",
        ):
            if name in fields:
                code_idx = fields.index(name)
                break

        for name in (
            "收盤價",
            "成交價",
            "ClosingPrice",
        ):
            if name in fields:
                price_idx = fields.index(name)
                break

        if (
            code_idx is None
            or price_idx is None
        ):
            continue

        for row in rows:

            if not isinstance(row, list):
                continue

            if max(
                code_idx,
                price_idx,
            ) >= len(row):
                continue

            stock_id = clean_stock_id(
                row[code_idx]
            )

            if not stock_id:
                continue

            value = to_number(
                row[price_idx]
            )

            if value > 0:
                prices[stock_id] = value

    return prices


def fetch_prices(date):

    print(
        f"[INFO] 取得收盤價：{date}"
    )

    params_list = [
        {
            "date": date,
            "response": "json",
        },
        {
            "date": date,
            "response": "json",
            "type": "ALLBUT0999",
        },
    ]

    last_error = None

    for url in PRICE_URLS:

        for params in params_list:

            try:

                print(
                    f"[INFO] 嘗試收盤價 API："
                    f"{url}"
                )

                data = get_json(
                    url,
                    params=params,
                    timeout=30,
                )

                prices = parse_price_table(
                    data
                )

                if prices:

                    print(
                        f"[OK] 成功解析 "
                        f"{len(prices)} 筆收盤價"
                    )

                    return prices

                last_error = RuntimeError(
                    "API 成功但沒有收盤價"
                )

            except Exception as e:

                last_error = e

                print(
                    f"[WARN] 收盤價 API 失敗："
                    f"{url} -> {e}"
                )

    raise RuntimeError(
        f"完全取得不到收盤價："
        f"{last_error}"
    )


# ============================================================
# 找最近有效交易日
# ============================================================

def find_latest_data():
    """
    只抓台灣今天的融資融券資料。

    重要：
    不再自動往前尋找前一個交易日。
    如果今天的資料取得不到，直接讓程式失敗，
    避免網站顯示昨天資料卻看起來像今天已更新。
    """

    # GitHub Actions Runner 預設使用 UTC，
    # 因此明確使用台灣時區，確保資料日期永遠以台灣時間判斷。
    today = datetime.now(
        ZoneInfo("Asia/Taipei")
    ).strftime("%Y%m%d")

    print()
    print("======================================")
    print(f"[INFO] 只抓台灣今日資料：{today}")
    print("======================================")

    try:

        data = fetch_margin(today)

        api_date = str(
            data.get("date", "")
        ).strip()

        # TWSE API 正常情況下應該回傳 YYYYMMDD。
        # 如果沒有回傳日期，仍以我們要求的 today 作為預期日期，
        # 但下面仍會進一步確認資料結構已經有效。
        if (
            api_date.isdigit()
            and len(api_date) == 8
        ):
            actual_date = api_date
        else:
            actual_date = today

        # --------------------------------------------------------
        # 最重要的防呆：
        # API 如果回傳前一交易日資料，絕對不能接受。
        # --------------------------------------------------------

        if actual_date != today:
            raise RuntimeError(
                f"API 回傳日期 {actual_date} "
                f"不是台灣今天 {today}"
            )

        print(
            f"[OK] 成功取得今天資料："
            f"{actual_date}"
        )

        return actual_date, data

    except Exception as e:

        print()
        print("======================================")
        print("❌ 今天的融資融券資料取得失敗")
        print("======================================")
        print(f"日期：{today}")
        print(f"原因：{e}")
        print("不使用前一交易日資料。")
        print("======================================")
        print()

        raise RuntimeError(
            f"今天 {today} 沒有取得有效融資融券資料"
        ) from e


# ============================================================
# 建立 JSON
# ============================================================

def build_json():

    print()
    print("======================================")
    print("       TWSE CREDIT DATA")
    print("======================================")

    date, margin_data = find_latest_data()

    # --------------------------------------------------------
    # 市場總表
    # --------------------------------------------------------

    market = parse_market_summary(
        margin_data
    )

    # --------------------------------------------------------
    # 個股
    # --------------------------------------------------------

    stock_rows = parse_stock_rows(
        margin_data
    )

    print(
        f"[INFO] 融資融券資料："
        f"{len(stock_rows)} 筆"
    )

    # --------------------------------------------------------
    # 收盤價
    # --------------------------------------------------------

    prices = fetch_prices(date)

    print(
        f"[INFO] 收盤價資料："
        f"{len(prices)} 筆"
    )

    # --------------------------------------------------------
    # 建立個股 JSON
    # --------------------------------------------------------

    stocks = []

    matched_prices = 0
    missing_prices = 0

    margin_increase_count = 0
    margin_decrease_count = 0

    short_increase_count = 0
    short_decrease_count = 0

    for item in stock_rows:

        stock_id = item["stock_id"]
        stock_name = item["stock_name"]

        close_price = prices.get(
            stock_id,
            0
        )

        # ----------------------------------------------------
        # 個股融資增減
        #
        # 用官方前日/今日餘額。
        #
        # 2330：
        # 27,677 - 27,969 = -292 張
        # ----------------------------------------------------

        margin_change_shares = (
            item["margin_today"]
            - item["margin_previous"]
        )

        # ----------------------------------------------------
        # 個股融券增減
        # ----------------------------------------------------

        short_change = (
            item["short_today"]
            - item["short_previous"]
        )

        # ----------------------------------------------------
        # 個股融資增減金額
        # ----------------------------------------------------

        if close_price > 0:

            matched_prices += 1

            margin_change_amount = (
                margin_change_shares
                * close_price
                * 1000
            )

        else:

            missing_prices += 1
            margin_change_amount = 0

        if margin_change_shares > 0:
            margin_increase_count += 1

        elif margin_change_shares < 0:
            margin_decrease_count += 1

        if short_change > 0:
            short_increase_count += 1

        elif short_change < 0:
            short_decrease_count += 1

        stocks.append(
            {
                "stock_id": stock_id,
                "stock_name": stock_name,
                "close_price": close_price,

                # 單位：元
                "margin_change": round(
                    margin_change_amount,
                    2,
                ),

                # 單位：張
                "short_change": int(
                    short_change
                ),
            }
        )

    # --------------------------------------------------------
    # 2330 最終 JSON 驗證
    # --------------------------------------------------------

    for item in stocks:

        if item["stock_id"] == "2330":

            print()
            print("======================================")
            print("最終 JSON：2330 台積電")
            print("======================================")

            print(
                f"收盤價："
                f"{item['close_price']:,.2f}"
            )

            print(
                f"融資增減："
                f"{item['margin_change']:,.0f} 元"
            )

            print(
                f"融資增減："
                f"{item['margin_change'] / 100_000_000:+,.4f} 億元"
            )

            print(
                f"融券增減："
                f"{item['short_change']:+,} 張"
            )

            print("======================================")
            print()

            break

    # --------------------------------------------------------
    # 更新時間
    # --------------------------------------------------------
    #
    # 不再使用 GitHub Runner 執行時間。
    # 網頁固定顯示每個工作日 21:00。
    # --------------------------------------------------------

    update_time = "21:00:00"

    output = {
        "data_date": (
            f"{date[:4]}/"
            f"{date[4:6]}/"
            f"{date[6:8]}"
        ),

        "update_time": update_time,

        # 全市場融資增減，單位：元
        "margin_total": round(
            market["margin_change_amount"],
            2,
        ),

        # 全市場融券增減，單位：張
        "short_total": int(
            market["short_change"]
        ),

        "credit": stocks,
    }

    # --------------------------------------------------------
    # 寫 JSON
    # --------------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2,
        )

    # --------------------------------------------------------
    # 最終報告
    # --------------------------------------------------------

    print()
    print("======================================")
    print(" credit_rank.json 建立完成")
    print("======================================")

    print(
        f"資料日期："
        f"{output['data_date']}"
    )

    print(
        f"更新時間："
        f"{output['update_time']}"
    )

    print(
        "融資增減："
        f"{output['margin_total']:+,.0f} 元"
    )

    print(
        "融資增減："
        f"{output['margin_total'] / 100_000_000:+,.2f} 億元"
    )

    print(
        "融券增減："
        f"{output['short_total']:+,} 張"
    )

    print(
        f"融資增加個股："
        f"{margin_increase_count} 檔"
    )

    print(
        f"融資減少個股："
        f"{margin_decrease_count} 檔"
    )

    print(
        f"融券增加個股："
        f"{short_increase_count} 檔"
    )

    print(
        f"融券減少個股："
        f"{short_decrease_count} 檔"
    )

    print(
        f"成功對應收盤價："
        f"{matched_prices}"
    )

    print(
        f"沒有對應收盤價："
        f"{missing_prices}"
    )

    print(
        f"輸出檔案："
        f"{OUTPUT_FILE}"
    )


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":

    try:
        build_json()

    except Exception as e:

        print()
        print("❌ credit.py 執行失敗")
        print(str(e))
        raise
