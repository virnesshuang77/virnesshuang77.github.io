# credit.py
# -*- coding: utf-8 -*-

"""
TWSE 融資融券每日排名資料產生器

輸出：
    credit_rank.json

流程：
    1. 從 TWSE MI_MARGN 取得融資融券餘額
    2. 從 TWSE MI_INDEX 取得同一交易日收盤價
    3. 以股票代號合併兩份資料
    4. 計算：
         融資增減金額 = (今日融資餘額 - 前日融資餘額)
                       × 收盤價 × 1000
         融券增減張數 = 今日融券餘額 - 前日融券餘額
    5. 輸出 credit_rank.json

重要：
    - MI_MARGN 解析失敗會直接失敗。
    - MI_INDEX 解析不到收盤價會直接失敗。
    - 不會用空資料覆蓋原本正常的 credit_rank.json。
    - 寫入時先建立暫存檔，成功後才 replace 正式檔案。
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests


# ============================================================
# 設定
# ============================================================

TWSE_BASE = "https://www.twse.com.tw"
OPENAPI_BASE = "https://openapi.twse.com.tw/v1"

MARGIN_ENDPOINTS = [
    # 目前實際測試成功的來源放第一順位
    TWSE_BASE + "/exchangeReport/MI_MARGN",
    TWSE_BASE + "/rwd/zh/marginTrading/MI_MARGN",
    OPENAPI_BASE + "/exchangeReport/MI_MARGN",
]

# 不再使用 STOCK_DAY_ALL。
# 收盤價改由 MI_INDEX 取得。
INDEX_ENDPOINTS = [
    TWSE_BASE + "/rwd/zh/afterTrading/MI_INDEX",
    TWSE_BASE + "/exchangeReport/MI_INDEX",
]

OUTPUT_FILE = Path("credit_rank.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0 Safari/537.36"
    ),
    "Accept": (
        "application/json,text/plain,"
        "application/xhtml+xml,text/html;q=0.9,*/*;q=0.8"
    ),
    "Referer": "https://www.twse.com.tw/",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}


# ============================================================
# HTTP
# ============================================================

def request_json(url, params=None, timeout=30):
    """
    取得 TWSE JSON。

    不直接呼叫 response.json()，
    先檢查內容，讓錯誤訊息更容易判斷。
    """

    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=timeout,
    )

    response.raise_for_status()

    text = response.text.lstrip("\ufeff").strip()

    if not text:
        raise RuntimeError("TWSE 回傳空白內容")

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        preview = text[:200].replace("\n", " ")

        raise RuntimeError(
            "TWSE 回傳內容不是 JSON；"
            f"HTTP={response.status_code}；"
            f"Content-Type={response.headers.get('Content-Type')}; "
            f"內容開頭={preview!r}"
        ) from exc


def request_first_success(endpoints, params):
    last_error = None

    for endpoint in endpoints:
        try:
            print(
                f"[INFO] 嘗試 API：{endpoint}"
            )

            data = request_json(
                endpoint,
                params=params,
                timeout=30,
            )

            print(
                f"[OK] API 回應成功：{endpoint}"
            )

            return data

        except Exception as exc:
            last_error = exc

            print(
                f"[WARN] API 失敗：{endpoint} -> {exc}"
            )

            time.sleep(0.5)

    raise RuntimeError(
        f"所有 API 都失敗：{last_error}"
    )


# ============================================================
# 共用工具
# ============================================================

def normalize_text(value):
    if value is None:
        return ""

    return (
        str(value)
        .strip()
        .replace("\r", "")
        .replace("\n", "")
        .replace(" ", "")
        .replace("　", "")
    )


def to_number(value):
    if value is None:
        return 0.0

    text = str(value).strip()

    if not text:
        return 0.0

    text = (
        text
        .replace(",", "")
        .replace(" ", "")
        .replace("　", "")
    )

    if text in {"--", "---", "----", "N/A", "null"}:
        return 0.0

    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]

    try:
        return float(text)
    except (ValueError, TypeError):
        return 0.0


def is_stock_id(value):
    text = str(value).strip()

    return (
        text.isdigit()
        and 3 <= len(text) <= 6
    )


def find_column(fields, aliases):
    """
    先完全比對，再做包含比對。
    """

    normalized_fields = [
        normalize_text(x)
        for x in fields
    ]

    normalized_aliases = [
        normalize_text(x)
        for x in aliases
    ]

    for alias in normalized_aliases:
        for index, field in enumerate(normalized_fields):
            if field == alias:
                return index

    for alias in normalized_aliases:
        if not alias:
            continue

        for index, field in enumerate(normalized_fields):
            if alias in field:
                return index

    return None


# ============================================================
# 日期
# ============================================================

def candidate_dates():
    now = datetime.now()

    dates = []

    for offset in range(10):
        date = now - timedelta(days=offset)

        if date.weekday() >= 5:
            continue

        dates.append(
            date.strftime("%Y%m%d")
        )

    return dates


def format_date(date):
    return (
        f"{date[:4]}/"
        f"{date[4:6]}/"
        f"{date[6:8]}"
    )


# ============================================================
# 遞迴尋找 TWSE tables
# ============================================================

def collect_tables(obj):
    """
    TWSE 不同端點 / 時期可能出現：

        {
            "tables": [
                {
                    "fields": [...],
                    "data": [...]
                }
            ]
        }

    或：

        {
            "data": [...],
            "fields": [...]
        }

    這裡統一找出所有 fields + data。
    """

    result = []

    if isinstance(obj, dict):

        fields = (
            obj.get("fields")
            or obj.get("columns")
            or obj.get("header")
        )

        rows = (
            obj.get("data")
            or obj.get("rows")
        )

        if (
            isinstance(fields, list)
            and isinstance(rows, list)
        ):
            result.append(
                {
                    "fields": fields,
                    "data": rows,
                }
            )

        for value in obj.values():
            if isinstance(value, (dict, list)):
                result.extend(
                    collect_tables(value)
                )

    elif isinstance(obj, list):

        for item in obj:
            if isinstance(item, (dict, list)):
                result.extend(
                    collect_tables(item)
                )

    return result


# ============================================================
# MI_MARGN
# ============================================================

def parse_margin_table(fields, rows):
    """
    找到：

        股票代號
        股票名稱
        融資前日餘額
        融資今日餘額
        融券前日餘額
        融券今日餘額

    如果 TWSE 沒有提供完整表頭，
    再使用 MI_MARGN 常見欄位位置：

        0  證券代號
        1  證券名稱
        2  融資前日餘額
        3  融資買進
        4  融資賣出
        5  現金償還
        6  融資今日餘額
        ...
        8  融券前日餘額
        ...
        12 融券今日餘額
    """

    if not fields or not rows:
        return []

    stock_id_idx = find_column(
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

    stock_name_idx = find_column(
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

    margin_previous_idx = find_column(
        fields,
        [
            "融資前日餘額",
            "融資前日餘額(張)",
            "融資前日餘額(交易單位)",
            "融資前日餘額(交易單位數)",
        ],
    )

    margin_today_idx = find_column(
        fields,
        [
            "融資今日餘額",
            "融資今日餘額(張)",
            "融資今日餘額(交易單位)",
            "融資今日餘額(交易單位數)",
        ],
    )

    short_previous_idx = find_column(
        fields,
        [
            "融券前日餘額",
            "融券前日餘額(張)",
            "融券前日餘額(交易單位)",
            "融券前日餘額(交易單位數)",
        ],
    )

    short_today_idx = find_column(
        fields,
        [
            "融券今日餘額",
            "融券今日餘額(張)",
            "融券今日餘額(交易單位)",
            "融券今日餘額(交易單位數)",
        ],
    )

    # --------------------------------------------------------
    # 備援：標準 MI_MARGN 欄位位置
    # --------------------------------------------------------

    if (
        stock_id_idx is None
        and len(fields) >= 13
    ):
        stock_id_idx = 0

    if (
        stock_name_idx is None
        and len(fields) >= 13
    ):
        stock_name_idx = 1

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

    required = [
        stock_id_idx,
        margin_previous_idx,
        margin_today_idx,
        short_previous_idx,
        short_today_idx,
    ]

    if any(x is None for x in required):
        print(
            "[WARN] MI_MARGN 找不到必要欄位"
        )
        print(
            "[DEBUG] fields =",
            fields,
        )
        return []

    result = []

    max_index = max(
        required
    )

    for row in rows:

        if not isinstance(row, list):
            continue

        if len(row) <= max_index:
            continue

        stock_id = str(
            row[stock_id_idx]
        ).strip()

        if not is_stock_id(stock_id):
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


def parse_margin(data):
    """
    先處理新式 tables，
    再處理舊式 creditList。
    """

    result = []

    # --------------------------------------------------------
    # 新式 fields/data
    # --------------------------------------------------------

    for table in collect_tables(data):

        parsed = parse_margin_table(
            table["fields"],
            table["data"],
        )

        if parsed:
            result.extend(parsed)

    # --------------------------------------------------------
    # 舊式 creditList
    # --------------------------------------------------------

    if isinstance(data, dict):

        credit_list = data.get(
            "creditList",
            [],
        )

        if isinstance(credit_list, list):

            for block in credit_list:

                if not isinstance(block, list):
                    continue

                if len(block) < 2:
                    continue

                header = block[0]
                rows = block[1:]

                if not isinstance(header, list):
                    continue

                parsed = parse_margin_table(
                    header,
                    rows,
                )

                if parsed:
                    result.extend(parsed)

    # --------------------------------------------------------
    # 去重
    # --------------------------------------------------------

    unique = {}

    for row in result:
        unique[
            row["stock_id"]
        ] = row

    return list(
        unique.values()
    )


def fetch_margin(date):
    params = {
        "date": date,
        "selectType": "ALL",
        "response": "json",
    }

    data = request_first_success(
        MARGIN_ENDPOINTS,
        params,
    )

    rows = parse_margin(
        data
    )

    if not rows:
        raise RuntimeError(
            "MI_MARGN API 有回應，"
            "但解析後為 0 筆融資融券資料。"
        )

    print(
        f"[OK] 成功解析 {len(rows)} 筆融資融券股票"
    )

    return data, rows


# ============================================================
# 找最新交易日
# ============================================================

def fetch_latest_margin():

    for date in candidate_dates():

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

        try:

            data, rows = fetch_margin(
                date
            )

            print(
                f"[OK] 找到交易日：{date}"
            )

            return (
                date,
                data,
                rows,
            )

        except Exception as exc:

            print(
                f"[WARN] {date} 無法使用：{exc}"
            )

            time.sleep(0.5)

    raise RuntimeError(
        "最近 10 天找不到有效的 TWSE 融資融券資料。"
    )


# ============================================================
# MI_INDEX 收盤價
# ============================================================

def parse_price_table(fields, rows):
    """
    MI_INDEX 內有多個 table。

    我們只找同時包含：
        證券代號
        證券名稱
        收盤價

    的表。
    """

    if not fields or not rows:
        return {}

    code_idx = find_column(
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

    name_idx = find_column(
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

    close_idx = find_column(
        fields,
        [
            "收盤價",
            "ClosingPrice",
            "Closing Price",
        ],
    )

    if (
        code_idx is None
        or close_idx is None
    ):
        return {}

    result = {}

    max_index = max(
        code_idx,
        close_idx,
    )

    for row in rows:

        if not isinstance(row, list):
            continue

        if len(row) <= max_index:
            continue

        stock_id = str(
            row[code_idx]
        ).strip()

        if not is_stock_id(stock_id):
            continue

        close_price = to_number(
            row[close_idx]
        )

        if close_price <= 0:
            continue

        if (
            name_idx is not None
            and name_idx < len(row)
        ):
            stock_name = str(
                row[name_idx]
            ).strip()
        else:
            stock_name = ""

        result[stock_id] = {
            "close_price": close_price,
            "stock_name": stock_name,
        }

    return result


def parse_prices(data):
    result = {}

    for table in collect_tables(data):

        parsed = parse_price_table(
            table["fields"],
            table["data"],
        )

        if parsed:
            result.update(parsed)

    # --------------------------------------------------------
    # 有些回傳可能直接是 list[dict]
    # --------------------------------------------------------

    if isinstance(data, list):

        for item in data:

            if not isinstance(item, dict):
                continue

            stock_id = str(
                item.get("Code")
                or item.get("證券代號")
                or item.get("股票代號")
                or ""
            ).strip()

            close_price = (
                item.get("ClosingPrice")
                if "ClosingPrice" in item
                else item.get("收盤價")
            )

            if (
                is_stock_id(stock_id)
                and to_number(close_price) > 0
            ):
                result[stock_id] = {
                    "close_price":
                        to_number(close_price),
                    "stock_name":
                        str(
                            item.get("Name")
                            or item.get("證券名稱")
                            or item.get("股票名稱")
                            or ""
                        ).strip(),
                }

    return result


def fetch_prices(date):
    """
    只使用 MI_INDEX。
    不再呼叫 STOCK_DAY_ALL。
    """

    params = {
        "date": date,
        "type": "ALL",
        "response": "json",
    }

    last_error = None

    for endpoint in INDEX_ENDPOINTS:

        try:

            print(
                f"[INFO] 取得 MI_INDEX 收盤價：{date}"
            )

            data = request_json(
                endpoint,
                params=params,
                timeout=30,
            )

            prices = parse_prices(
                data
            )

            if prices:

                print(
                    f"[OK] MI_INDEX 成功解析 "
                    f"{len(prices)} 筆收盤價"
                )

                return prices

            raise RuntimeError(
                "MI_INDEX 有回應，"
                "但找不到包含「收盤價」的股票資料表。"
            )

        except Exception as exc:

            last_error = exc

            print(
                f"[WARN] MI_INDEX 失敗："
                f"{endpoint} -> {exc}"
            )

            time.sleep(0.5)

    raise RuntimeError(
        "所有 MI_INDEX 收盤價 API 都失敗："
        f"{last_error}"
    )


# ============================================================
# 建立結果
# ============================================================

def build_json():

    date, margin_data, margin_rows = (
        fetch_latest_margin()
    )

    print(
        f"[INFO] 融資融券資料："
        f"{len(margin_rows)} 筆"
    )

    if not margin_rows:
        raise RuntimeError(
            "融資融券解析為 0 筆，停止輸出。"
        )

    # --------------------------------------------------------
    # 取得同一天收盤價
    # --------------------------------------------------------

    prices = fetch_prices(
        date
    )

    if not prices:
        raise RuntimeError(
            "完全取得不到 MI_INDEX 收盤價，"
            "停止輸出。"
        )

    # --------------------------------------------------------
    # 計算
    # --------------------------------------------------------

    stocks = []

    margin_total = 0.0
    short_total = 0.0

    no_price_count = 0

    for item in margin_rows:

        stock_id = item[
            "stock_id"
        ]

        stock_name = item[
            "stock_name"
        ]

        price_info = prices.get(
            stock_id
        )

        if not price_info:
            no_price_count += 1
            continue

        close_price = price_info[
            "close_price"
        ]

        # 如果 MI_INDEX 有股票名稱，
        # 而 MI_MARGN 名稱空白，則補上。
        if (
            not stock_name
            and price_info.get(
                "stock_name"
            )
        ):
            stock_name = price_info[
                "stock_name"
            ]

        margin_change_shares = (
            item["margin_today"]
            -
            item["margin_previous"]
        )

        # 融資增減金額：
        # 張數 × 收盤價 × 1000
        margin_change_amount = (
            margin_change_shares
            *
            close_price
            *
            1000
        )

        short_change = (
            item["short_today"]
            -
            item["short_previous"]
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
    # 嚴格保護
    # --------------------------------------------------------

    if not stocks:
        raise RuntimeError(
            "融資融券有資料，"
            "但沒有任何股票能與 MI_INDEX 收盤價對應。"
        )

    # --------------------------------------------------------
    # 排序
    #
    # credit.html 自己會排序，
    # 這裡保持完整資料即可。
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
    # --------------------------------------------------------

    temp_file = OUTPUT_FILE.with_name(
        OUTPUT_FILE.name
        + ".tmp"
    )

    with open(
        temp_file,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2,
        )

        file.write("\n")

    # 只有完整寫完才取代正式檔案
    temp_file.replace(
        OUTPUT_FILE
    )

    # --------------------------------------------------------
    # 結果
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
        f"資料日期：{output['data_date']}"
    )

    print(
        f"更新時間：{output['update_time']}"
    )

    print(
        f"融資增減金額：{output['margin_total']}"
    )

    print(
        f"融券增減張數：{output['short_total']}"
    )

    print(
        f"融資融券股票數：{len(margin_rows)}"
    )

    print(
        f"成功對應收盤價：{len(stocks)}"
    )

    print(
        f"沒有對應收盤價：{no_price_count}"
    )

    print(
        f"輸出檔案：{OUTPUT_FILE}"
    )


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":

    try:

        build_json()

    except Exception as exc:

        print()
        print(
            "❌ credit.py 執行失敗"
        )

        print(
            f"錯誤：{exc}"
        )

        raise
