# credit.py
# -*- coding: utf-8 -*-

"""
每天抓取 TWSE 上市融資融券資料
--------------------------------
輸出：
    credit_rank.json

資料來源：
    TWSE MI_MARGN
    TWSE STOCK_DAY_ALL

主要功能：
    1. 取得上市股票融資融券餘額
    2. 取得上市股票收盤價
    3. 計算個股融資增減金額
    4. 計算個股融券增減張數
    5. 計算全市場融資增減金額
    6. 計算全市場融券增減張數
    7. 輸出給 credit.html 使用

重要：
    - 不再假設 MI_MARGN 一定有 creditList。
    - 優先處理 TWSE 新式 tables / fields / data 結構。
    - 同時相容舊式 creditList 結構。
    - 如果解析不到任何股票，直接讓程式失敗。
      不會再把 credit_rank.json 寫成空資料。
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests


# ============================================================
# 基本設定
# ============================================================

TWSE_BASE = "https://www.twse.com.tw"

# 新式官方 OpenAPI
OPENAPI_BASE = "https://openapi.twse.com.tw/v1"

MARGIN_URLS = [
    OPENAPI_BASE + "/exchangeReport/MI_MARGN",
    TWSE_BASE + "/exchangeReport/MI_MARGN",
    TWSE_BASE + "/rwd/zh/marginTrading/MI_MARGN",
]

PRICE_URLS = [
    OPENAPI_BASE + "/exchangeReport/STOCK_DAY_ALL",
    TWSE_BASE + "/exchangeReport/STOCK_DAY_ALL",
    TWSE_BASE + "/rwd/zh/afterTrading/STOCK_DAY_ALL",
]

OUTPUT_FILE = Path("credit_rank.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
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

    return response.json()


def get_first_working_json(urls, params=None):
    last_error = None

    for url in urls:
        try:
            print(f"[INFO] 嘗試 API：{url}")

            data = get_json(
                url,
                params=params,
                timeout=30,
            )

            if data is not None:
                print(f"[OK] API 回應成功：{url}")
                return data

        except Exception as e:
            last_error = e
            print(
                f"[WARN] API 失敗：{url} -> {e}"
            )

    raise RuntimeError(
        f"所有 API 都無法取得資料：{last_error}"
    )


# ============================================================
# 找最近交易日
# ============================================================

def get_candidate_dates():
    today = datetime.now()

    dates = []

    for i in range(0, 10):
        d = today - timedelta(days=i)

        if d.weekday() >= 5:
            continue

        dates.append(
            d.strftime("%Y%m%d")
        )

    return dates


# ============================================================
# 取得融資融券資料
# ============================================================

def fetch_margin(date):

    params_list = [
        {
            "date": date,
            "selectType": "ALL",
            "response": "json",
        },
        {
            "date": date,
            "selectType": "STOCK",
            "response": "json",
        },
    ]

    last_error = None

    for params in params_list:

        try:
            data = get_first_working_json(
                MARGIN_URLS,
                params=params,
            )

            if is_valid_margin_response(data):
                return data

            print(
                f"[WARN] {date} API 有回應，但沒有可解析的融資融券資料"
            )

        except Exception as e:
            last_error = e
            print(
                f"[WARN] {date} 融資融券取得失敗：{e}"
            )

    if last_error:
        raise RuntimeError(
            f"{date} 融資融券 API 失敗：{last_error}"
        )

    return None


# ============================================================
# 數字轉換
# ============================================================

def to_number(value):

    if value is None:
        return 0.0

    text = str(value).strip()

    if text == "":
        return 0.0

    text = (
        text
        .replace(",", "")
        .replace("--", "0")
        .replace(" ", "")
    )

    # TWSE 有時會使用括號表示負數
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]

    try:
        return float(text)
    except Exception:
        return 0.0


# ============================================================
# 清理欄位名稱
# ============================================================

def normalize_header(value):

    if value is None:
        return ""

    return (
        str(value)
        .strip()
        .replace("\n", "")
        .replace("\r", "")
        .replace(" ", "")
        .replace("　", "")
    )


# ============================================================
# 欄位搜尋
# ============================================================

def find_field_index(fields, aliases):

    normalized = [
        normalize_header(x)
        for x in fields
    ]

    # 先完全相等
    for alias in aliases:
        alias_n = normalize_header(alias)

        for i, field in enumerate(normalized):
            if field == alias_n:
                return i

    # 再做包含判斷
    for alias in aliases:
        alias_n = normalize_header(alias)

        for i, field in enumerate(normalized):
            if alias_n and alias_n in field:
                return i

    return None


# ============================================================
# 判斷是否像股票資料
# ============================================================

def looks_like_stock_id(value):

    text = str(value).strip()

    if not text:
        return False

    # 上市股票通常是 4~6 碼數字
    return (
        text.isdigit()
        and 3 <= len(text) <= 6
    )


# ============================================================
# 從 fields + data 解析
# ============================================================

def parse_table_object(table):

    if not isinstance(table, dict):
        return []

    fields = (
        table.get("fields")
        or table.get("columns")
        or table.get("header")
        or []
    )

    rows = (
        table.get("data")
        or table.get("rows")
        or []
    )

    if not isinstance(fields, list):
        return []

    if not isinstance(rows, list):
        return []

    if not fields or not rows:
        return []

    # --------------------------------------------------------
    # 找股票代號、名稱
    # --------------------------------------------------------

    stock_id_idx = find_field_index(
        fields,
        [
            "證券代號",
            "股票代號",
            "代號",
            "有價證券代號",
            "Code",
            "code",
        ],
    )

    stock_name_idx = find_field_index(
        fields,
        [
            "證券名稱",
            "股票名稱",
            "名稱",
            "有價證券名稱",
            "Name",
            "name",
        ],
    )

    if stock_id_idx is None:
        return []

    # --------------------------------------------------------
    # 融資欄位
    # --------------------------------------------------------

    margin_previous_idx = find_field_index(
        fields,
        [
            "融資前日餘額",
            "融資前日餘額(張)",
            "融資前日餘額(交易單位)",
            "融資前日餘額(交易單位數)",
        ],
    )

    margin_today_idx = find_field_index(
        fields,
        [
            "融資今日餘額",
            "融資今日餘額(張)",
            "融資今日餘額(交易單位)",
            "融資今日餘額(交易單位數)",
        ],
    )

    # --------------------------------------------------------
    # 融券欄位
    # --------------------------------------------------------

    short_previous_idx = find_field_index(
        fields,
        [
            "融券前日餘額",
            "融券前日餘額(張)",
            "融券前日餘額(交易單位)",
            "融券前日餘額(交易單位數)",
        ],
    )

    short_today_idx = find_field_index(
        fields,
        [
            "融券今日餘額",
            "融券今日餘額(張)",
            "融券今日餘額(交易單位)",
            "融券今日餘額(交易單位數)",
        ],
    )

    # --------------------------------------------------------
    # 如果沒有「前日 / 今日」欄位，
    # 嘗試用常見欄位位置。
    #
    # 標準 MI_MARGN：
    # 0 代號
    # 1 名稱
    # 2 融資前日餘額
    # 3 融資買進
    # 4 融資賣出
    # 5 現金償還
    # 6 融資今日餘額
    # 7 融資限額
    # 8 融券前日餘額
    # 9 融券賣出
    # 10 融券買進
    # 11 現券償還
    # 12 融券今日餘額
    # --------------------------------------------------------

    if (
        margin_previous_idx is None
        and len(fields) >= 13
    ):
        margin_previous_idx = 2

    if (
        margin_today_idx is None
        and len(fields) >= 13
    ):
        margin_today_idx = 6

    if (
        short_previous_idx is None
        and len(fields) >= 13
    ):
        short_previous_idx = 8

    if (
        short_today_idx is None
        and len(fields) >= 13
    ):
        short_today_idx = 12

    if (
        margin_previous_idx is None
        or margin_today_idx is None
        or short_previous_idx is None
        or short_today_idx is None
    ):
        print(
            "[WARN] 找不到完整融資融券欄位"
        )
        print(
            "[DEBUG] fields =",
            fields
        )
        return []

    result = []

    for row in rows:

        if not isinstance(row, list):
            continue

        max_idx = max(
            stock_id_idx,
            margin_previous_idx,
            margin_today_idx,
            short_previous_idx,
            short_today_idx,
        )

        if len(row) <= max_idx:
            continue

        stock_id = str(
            row[stock_id_idx]
        ).strip()

        if not looks_like_stock_id(stock_id):
            continue

        if (
            stock_name_idx is not None
            and stock_name_idx < len(row)
        ):
            stock_name = str(
                row[stock_name_idx]
            ).strip()
        else:
            stock_name = ""

        result.append(
            {
                "stock_id": stock_id,
                "stock_name": stock_name,
                "margin_previous": to_number(
                    row[margin_previous_idx]
                ),
                "margin_today": to_number(
                    row[margin_today_idx]
                ),
                "short_previous": to_number(
                    row[short_previous_idx]
                ),
                "short_today": to_number(
                    row[short_today_idx]
                ),
            }
        )

    return result


# ============================================================
# 舊式 creditList 解析
# ============================================================

def parse_credit_list(credit_list):

    if not isinstance(credit_list, list):
        return []

    result = []

    for block in credit_list:

        if not isinstance(block, list):
            continue

        if len(block) < 2:
            continue

        header = block[0]
        rows = block[1:]

        if not isinstance(header, list):
            continue

        table = {
            "fields": header,
            "data": rows,
        }

        parsed = parse_table_object(
            table
        )

        result.extend(parsed)

    return result


# ============================================================
# 遞迴搜尋 tables
# ============================================================

def extract_tables_from_object(obj):

    tables = []

    if isinstance(obj, dict):

        if (
            isinstance(obj.get("fields"), list)
            and isinstance(obj.get("data"), list)
        ):
            tables.append(obj)

        for key in (
            "tables",
            "data",
            "result",
            "results",
        ):

            value = obj.get(key)

            if isinstance(value, list):
                for item in value:
                    tables.extend(
                        extract_tables_from_object(
                            item
                        )
                    )

            elif isinstance(value, dict):
                tables.extend(
                    extract_tables_from_object(
                        value
                    )
                )

    elif isinstance(obj, list):

        for item in obj:
            tables.extend(
                extract_tables_from_object(
                    item
                )
            )

    return tables


# ============================================================
# 解析融資融券
# ============================================================

def parse_margin(data):

    if not isinstance(data, (dict, list)):
        return []

    # --------------------------------------------------------
    # 1. 舊式 creditList
    # --------------------------------------------------------

    if isinstance(data, dict):

        credit_list = data.get(
            "creditList"
        )

        if credit_list:
            parsed = parse_credit_list(
                credit_list
            )

            if parsed:
                return deduplicate_stocks(
                    parsed
                )

    # --------------------------------------------------------
    # 2. 新式 tables / fields / data
    # --------------------------------------------------------

    tables = extract_tables_from_object(
        data
    )

    all_rows = []

    for table in tables:

        parsed = parse_table_object(
            table
        )

        if parsed:
            all_rows.extend(
                parsed
            )

    if all_rows:
        return deduplicate_stocks(
            all_rows
        )

    return []


# ============================================================
# 去除重複股票
# ============================================================

def deduplicate_stocks(rows):

    result = {}
    order = []

    for row in rows:

        stock_id = row["stock_id"]

        if stock_id not in result:
            order.append(stock_id)

        result[stock_id] = row

    return [
        result[stock_id]
        for stock_id in order
    ]


# ============================================================
# 判斷 API 是否真的有融資融券資料
# ============================================================

def is_valid_margin_response(data):

    rows = parse_margin(data)

    if rows:
        print(
            f"[OK] 成功解析 {len(rows)} 筆融資融券股票"
        )
        return True

    return False


# ============================================================
# 找最新交易日
# ============================================================

def find_latest_data():

    for date in get_candidate_dates():

        try:

            print()
            print(
                "======================================"
            )
            print(
                f"[INFO] 測試日期：{date}"
            )
            print(
                "======================================"
            )

            data = fetch_margin(
                date
            )

            if data:

                rows = parse_margin(
                    data
                )

                if rows:

                    print(
                        f"[OK] 找到交易日：{date}"
                    )

                    return (
                        date,
                        data,
                        rows,
                    )

                print(
                    f"[WARN] {date} API 有資料，但解析後為 0 筆"
                )

        except Exception as e:

            print(
                f"[WARN] {date} 無資料：{e}"
            )

        time.sleep(0.5)

    raise RuntimeError(
        "找不到最近的有效融資融券資料"
    )


# ============================================================
# 取得上市股票收盤價
# ============================================================

def fetch_prices(date):

    params = {
        "date": date,
        "response": "json",
    }

    last_error = None

    for url in PRICE_URLS:

        try:

            print(
                f"[INFO] 取得收盤價：{date}"
            )

            data = get_json(
                url,
                params=params,
                timeout=30,
            )

            # ------------------------------------------------
            # 新式 / 舊式可能是：
            # 1. list[dict]
            # 2. {"data": [...], "fields": [...]}
            # 3. {"tables": [...]}
            # ------------------------------------------------

            prices = parse_price_response(
                data
            )

            if prices:

                print(
                    f"[OK] 收盤價：{len(prices)} 筆"
                )

                return prices

            print(
                f"[WARN] 收盤價 API 回應但沒有解析到價格：{url}"
            )

        except Exception as e:

            last_error = e

            print(
                f"[WARN] 收盤價 API 失敗：{url} -> {e}"
            )

    print(
        f"[WARN] 所有收盤價 API 都失敗：{last_error}"
    )

    return {}


# ============================================================
# 解析收盤價
# ============================================================

def parse_price_response(data):

    prices = {}

    # --------------------------------------------------------
    # list[dict]
    # --------------------------------------------------------

    if isinstance(data, list):

        for row in data:

            if not isinstance(row, dict):
                continue

            stock_id = str(
                row.get("Code")
                or row.get("證券代號")
                or row.get("股票代號")
                or ""
            ).strip()

            close_price = (
                row.get("ClosingPrice")
                if "ClosingPrice" in row
                else row.get("收盤價")
            )

            if not stock_id:
                continue

            price = to_number(
                close_price
            )

            if price > 0:
                prices[stock_id] = price

        return prices

    # --------------------------------------------------------
    # fields + data
    # --------------------------------------------------------

    if isinstance(data, dict):

        fields = (
            data.get("fields")
            or data.get("columns")
            or []
        )

        rows = (
            data.get("data")
            or []
        )

        if isinstance(fields, list) and isinstance(rows, list):

            code_idx = find_field_index(
                fields,
                [
                    "Code",
                    "證券代號",
                    "股票代號",
                ],
            )

            price_idx = find_field_index(
                fields,
                [
                    "ClosingPrice",
                    "收盤價",
                ],
            )

            if (
                code_idx is not None
                and price_idx is not None
            ):

                for row in rows:

                    if not isinstance(row, list):
                        continue

                    if (
                        len(row) <= max(
                            code_idx,
                            price_idx,
                        )
                    ):
                        continue

                    stock_id = str(
                        row[code_idx]
                    ).strip()

                    price = to_number(
                        row[price_idx]
                    )

                    if (
                        stock_id
                        and price > 0
                    ):
                        prices[stock_id] = price

        if prices:
            return prices

    # --------------------------------------------------------
    # tables
    # --------------------------------------------------------

    tables = extract_tables_from_object(
        data
    )

    for table in tables:

        fields = table.get(
            "fields",
            []
        )

        rows = table.get(
            "data",
            []
        )

        code_idx = find_field_index(
            fields,
            [
                "Code",
                "證券代號",
                "股票代號",
            ],
        )

        price_idx = find_field_index(
            fields,
            [
                "ClosingPrice",
                "收盤價",
            ],
        )

        if (
            code_idx is None
            or price_idx is None
        ):
            continue

        for row in rows:

            if not isinstance(row, list):
                continue

            if (
                len(row)
                <= max(
                    code_idx,
                    price_idx,
                )
            ):
                continue

            stock_id = str(
                row[code_idx]
            ).strip()

            price = to_number(
                row[price_idx]
            )

            if (
                stock_id
                and price > 0
            ):
                prices[stock_id] = price

    return prices


# ============================================================
# 日期
# ============================================================

def format_date(date):

    return (
        f"{date[:4]}/"
        f"{date[4:6]}/"
        f"{date[6:8]}"
    )


# ============================================================
# 建立 credit_rank.json
# ============================================================

def build_json():

    date, margin_data, margin_rows = (
        find_latest_data()
    )

    print(
        f"[INFO] 融資融券資料："
        f"{len(margin_rows)} 筆"
    )

    # --------------------------------------------------------
    # 強制保護
    # --------------------------------------------------------

    if len(margin_rows) == 0:
        raise RuntimeError(
            "融資融券解析結果為 0 筆，"
            "為避免覆蓋正常資料，本次停止輸出。"
        )

    # --------------------------------------------------------
    # 收盤價
    # --------------------------------------------------------

    prices = fetch_prices(
        date
    )

    if not prices:
        raise RuntimeError(
            "完全取得不到收盤價，"
            "為避免產生錯誤的融資金額，本次停止輸出。"
        )

    # --------------------------------------------------------
    # 建立個股資料
    # --------------------------------------------------------

    stocks = []

    margin_total = 0.0
    short_total = 0.0

    skipped_price = 0

    for item in margin_rows:

        stock_id = item[
            "stock_id"
        ]

        stock_name = item[
            "stock_name"
        ]

        close_price = prices.get(
            stock_id,
            0
        )

        if close_price <= 0:
            skipped_price += 1
            continue

        margin_previous = item[
            "margin_previous"
        ]

        margin_today = item[
            "margin_today"
        ]

        short_previous = item[
            "short_previous"
        ]

        short_today = item[
            "short_today"
        ]

        # ----------------------------------------------------
        # 融資張數變化
        # ----------------------------------------------------

        margin_change_shares = (
            margin_today
            -
            margin_previous
        )

        # ----------------------------------------------------
        # 融資金額變化
        #
        # 1 張 = 1000 股
        # ----------------------------------------------------

        margin_change_amount = (
            margin_change_shares
            *
            close_price
            *
            1000
        )

        # ----------------------------------------------------
        # 融券張數變化
        # ----------------------------------------------------

        short_change = (
            short_today
            -
            short_previous
        )

        margin_total += (
            margin_change_amount
        )

        short_total += (
            short_change
        )

        stocks.append(
            {
                "stock_id":
                    stock_id,

                "stock_name":
                    stock_name,

                "close_price":
                    close_price,

                "margin_change":
                    round(
                        margin_change_amount,
                        2,
                    ),

                "short_change":
                    int(
                        short_change
                    ),
            }
        )

    # --------------------------------------------------------
    # 再次保護
    # --------------------------------------------------------

    if len(stocks) == 0:
        raise RuntimeError(
            "融資融券有資料，但沒有任何股票能對應到收盤價，"
            "本次停止輸出。"
        )

    # --------------------------------------------------------
    # 更新時間
    # --------------------------------------------------------

    update_time = (
        datetime.now()
        .strftime("%H:%M:%S")
    )

    output = {

        "data_date":
            format_date(date),

        "update_time":
            update_time,

        "margin_total":
            round(
                margin_total,
                2,
            ),

        "short_total":
            int(
                short_total
            ),

        "credit":
            stocks,
    }

    # --------------------------------------------------------
    # 先寫暫存檔
    #
    # 成功後再取代正式 JSON，
    # 避免寫到一半造成損壞。
    # --------------------------------------------------------

    temp_file = OUTPUT_FILE.with_suffix(
        ".tmp"
    )

    with open(
        temp_file,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2,
        )

        f.write("\n")

    temp_file.replace(
        OUTPUT_FILE
    )

    # --------------------------------------------------------
    # 完成
    # --------------------------------------------------------

    print()
    print(
        "======================================"
    )

    print(
        " credit_rank.json 建立完成"
    )

    print(
        "======================================"
    )

    print(
        "資料日期：",
        output["data_date"]
    )

    print(
        "更新時間：",
        output["update_time"]
    )

    print(
        "融資增減金額：",
        output["margin_total"]
    )

    print(
        "融券增減張數：",
        output["short_total"]
    )

    print(
        "股票數量：",
        len(stocks)
    )

    print(
        "沒有股價而略過：",
        skipped_price
    )

    print(
        "輸出檔案：",
        OUTPUT_FILE
    )


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":

    try:

        build_json()

    except Exception as e:

        print()
        print(
            "❌ credit.py 執行失敗"
        )

        print(
            str(e)
        )

        raise
