# credit.py
# -*- coding: utf-8 -*-

"""
TWSE 融資融券每日排名資料產生器

本版本重點：
1. MI_MARGN：取得個股融資融券資料
2. MI_INDEX：取得個股收盤價
3. 「頁面最上方」的融資增減金額、融券增減張數
   直接使用 TWSE MI_MARGN 的「今日餘額 - 前日餘額」
   不再把個股的「融資張數 × 收盤價」加總當成市場總額。

公式：
    市場融資增減金額
        = (今日融資金額 - 前日融資金額) × 1000

    市場融券增減張數
        = 今日融券交易單位 - 前日融券交易單位

    個股融資增減金額（供排名）
        = (今日融資餘額 - 前日融資餘額)
          × 收盤價 × 1000

輸出：
    credit_rank.json
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
    TWSE_BASE + "/exchangeReport/MI_MARGN",
    TWSE_BASE + "/rwd/zh/marginTrading/MI_MARGN",
    OPENAPI_BASE + "/exchangeReport/MI_MARGN",
]

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
            f"HTTP={response.status_code}; "
            f"Content-Type={response.headers.get('Content-Type')}; "
            f"內容開頭={preview!r}"
        ) from exc


def request_first_success(endpoints, params):
    last_error = None

    for endpoint in endpoints:
        try:
            print(f"[INFO] 嘗試 API：{endpoint}")

            data = request_json(
                endpoint,
                params=params,
                timeout=30,
            )

            print(f"[OK] API 回應成功：{endpoint}")

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
    normalized_fields = [
        normalize_text(x)
        for x in fields
    ]

    normalized_aliases = [
        normalize_text(x)
        for x in aliases
    ]

    # 完全比對
    for alias in normalized_aliases:
        for index, field in enumerate(normalized_fields):
            if field == alias:
                return index

    # 包含比對
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
# MI_MARGN：個股資料
# ============================================================

def parse_margin_table(fields, rows):
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

    # ========================================================
    # TWSE MI_MARGN 實際欄位位置備援
    #
    # 官方 MI_MARGN 個股欄位：
    #
    # 0  代號
    # 1  名稱
    # 2  融資買進
    # 3  融資賣出
    # 4  融資現金償還
    # 5  融資前日餘額
    # 6  融資今日餘額
    # 7  融資次一營業日限額
    # 8  融券買進
    # 9  融券賣出
    # 10 融券現券償還
    # 11 融券前日餘額
    # 12 融券今日餘額
    # 13 融券次一營業日限額
    # 14 資券互抵
    # 15 註記
    #
    # 之前版本把融資前日餘額誤抓成 index 2，
    # 那其實是「融資買進」，因此會讓 margin_change
    # 幾乎全部變成正數。
    # ========================================================

    if stock_id_idx is None and len(fields) >= 13:
        stock_id_idx = 0

    if stock_name_idx is None and len(fields) >= 13:
        stock_name_idx = 1

    # ★ 修正：融資前日餘額 = index 5
    if margin_previous_idx is None and len(fields) >= 13:
        margin_previous_idx = 5

    # ★ 融資今日餘額 = index 6
    if margin_today_idx is None and len(fields) >= 13:
        margin_today_idx = 6

    # ★ 修正：融券前日餘額 = index 11
    if short_previous_idx is None and len(fields) >= 13:
        short_previous_idx = 11

    # ★ 融券今日餘額 = index 12
    if short_today_idx is None and len(fields) >= 13:
        short_today_idx = 12

    required = [
        stock_id_idx,
        margin_previous_idx,
        margin_today_idx,
        short_previous_idx,
        short_today_idx,
    ]

    if any(x is None for x in required):
        return []

    # 第一次解析時把實際欄位位置印出來，方便 Action log 驗證
    print(
        "[INFO] MI_MARGN 個股欄位位置："
        f"stock_id={stock_id_idx}, "
        f"stock_name={stock_name_idx}, "
        f"margin_previous={margin_previous_idx}, "
        f"margin_today={margin_today_idx}, "
        f"short_previous={short_previous_idx}, "
        f"short_today={short_today_idx}"
    )

    result = []

    max_index = max(required)

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
    result = []

    # 新式 fields/data
    for table in collect_tables(data):

        parsed = parse_margin_table(
            table["fields"],
            table["data"],
        )

        if parsed:
            result.extend(parsed)

    # 舊式 creditList
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

    # 去重
    unique = {}

    for row in result:
        unique[row["stock_id"]] = row

    return list(unique.values())


# ============================================================
# ★ 新增：從 MI_MARGN 讀取「市場總額」
# ============================================================

def parse_market_totals(data):
    """
    TWSE MI_MARGN 頂端有一個「信用交易統計」總表。

    典型內容：

        融資(交易單位)
        買進
        賣出
        現金(券)償還
        前日餘額
        今日餘額

        融券(交易單位)
        ...

        融資金額(仟元)
        買進
        賣出
        現金(券)償還
        前日餘額
        今日餘額

    我們要的不是個股加總，而是：

        融資增減金額
        = 融資金額今日餘額 - 前日餘額
          × 1000 元

        融券增減張數
        = 融券今日餘額 - 前日餘額
    """

    tables = collect_tables(data)

    margin_amount_total = None
    short_total = None

    # --------------------------------------------------------
    # 嘗試辨識「總表」
    # --------------------------------------------------------

    for table in tables:

        fields = table["fields"]
        rows = table["data"]

        normalized_fields = [
            normalize_text(x)
            for x in fields
        ]

        # 必須至少有「前日餘額」與「今日餘額」
        previous_idx = find_column(
            fields,
            ["前日餘額"],
        )

        today_idx = find_column(
            fields,
            ["今日餘額"],
        )

        if (
            previous_idx is None
            or today_idx is None
        ):
            continue

        # ----------------------------------------------------
        # 情況 A：欄位本身就是「項目 / 買進 / 賣出...」
        # ----------------------------------------------------

        item_idx = find_column(
            fields,
            [
                "項目",
                "名稱",
                "類別",
            ],
        )

        if item_idx is None:
            # 有些 TWSE 結構可能直接用第一欄當項目
            if len(fields) >= 5:
                item_idx = 0

        if item_idx is None:
            continue

        for row in rows:

            if not isinstance(row, list):
                continue

            max_index = max(
                item_idx,
                previous_idx,
                today_idx,
            )

            if len(row) <= max_index:
                continue

            item_name = normalize_text(
                row[item_idx]
            )

            previous_value = to_number(
                row[previous_idx]
            )

            today_value = to_number(
                row[today_idx]
            )

            # ------------------------------------------------
            # 融券交易單位
            # ------------------------------------------------

            if (
                "融券" in item_name
                and "金額" not in item_name
            ):
                short_total = (
                    today_value
                    -
                    previous_value
                )

            # ------------------------------------------------
            # 融資金額
            # ------------------------------------------------

            if (
                "融資金額" in item_name
            ):
                margin_amount_total = (
                    today_value
                    -
                    previous_value
                ) * 1000

    # --------------------------------------------------------
    # 找不到時，再嘗試舊式 creditList
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

                fields = block[0]
                rows = block[1:]

                if not isinstance(fields, list):
                    continue

                previous_idx = find_column(
                    fields,
                    ["前日餘額"],
                )

                today_idx = find_column(
                    fields,
                    ["今日餘額"],
                )

                item_idx = find_column(
                    fields,
                    [
                        "項目",
                        "名稱",
                        "類別",
                    ],
                )

                if (
                    previous_idx is None
                    or today_idx is None
                ):
                    continue

                if item_idx is None:
                    item_idx = 0

                for row in rows:

                    if not isinstance(row, list):
                        continue

                    max_index = max(
                        item_idx,
                        previous_idx,
                        today_idx,
                    )

                    if len(row) <= max_index:
                        continue

                    item_name = normalize_text(
                        row[item_idx]
                    )

                    previous_value = to_number(
                        row[previous_idx]
                    )

                    today_value = to_number(
                        row[today_idx]
                    )

                    if (
                        "融券" in item_name
                        and "金額" not in item_name
                    ):
                        short_total = (
                            today_value
                            -
                            previous_value
                        )

                    if (
                        "融資金額" in item_name
                    ):
                        margin_amount_total = (
                            today_value
                            -
                            previous_value
                        ) * 1000

    # --------------------------------------------------------
    # 嚴格驗證
    # --------------------------------------------------------

    if margin_amount_total is None:
        raise RuntimeError(
            "無法從 MI_MARGN 找到「融資金額」的前日/今日餘額。"
        )

    if short_total is None:
        raise RuntimeError(
            "無法從 MI_MARGN 找到「融券」的前日/今日餘額。"
        )

    return (
        round(margin_amount_total, 2),
        int(short_total),
    )


# ============================================================
# 取得最新交易日
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
                    "MI_MARGN 有回應，"
                    "但解析後為 0 筆個股資料。"
                )

            print(
                f"[OK] 成功解析 {len(rows)} 筆融資融券股票"
            )

            # ★ 市場總額直接從 TWSE 總表取得
            margin_total, short_total = (
                parse_market_totals(data)
            )

            print(
                "[OK] TWSE 市場總額解析成功"
            )

            print(
                f"[INFO] 融資增減金額：{margin_total}"
            )

            print(
                f"[INFO] 融券增減張數：{short_total}"
            )

            print(
                f"[OK] 找到交易日：{date}"
            )

            return (
                date,
                data,
                rows,
                margin_total,
                short_total,
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
# MI_INDEX：收盤價
# ============================================================

def parse_price_table(fields, rows):

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
# 建立 JSON
# ============================================================

def build_json():

    (
        date,
        margin_data,
        margin_rows,
        margin_total,
        short_total,
    ) = fetch_latest_margin()

    print(
        f"[INFO] 融資融券資料："
        f"{len(margin_rows)} 筆"
    )

    # --------------------------------------------------------
    # 收盤價
    # --------------------------------------------------------

    prices = fetch_prices(
        date
    )

    if not prices:
        raise RuntimeError(
            "完全取得不到 MI_INDEX 收盤價，停止輸出。"
        )

    # --------------------------------------------------------
    # 個股排名資料
    # --------------------------------------------------------

    stocks = []

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

        if (
            not stock_name
            and price_info.get(
                "stock_name"
            )
        ):
            stock_name = price_info[
                "stock_name"
            ]

        # 個股融資餘額變化
        margin_change_shares = (
            item["margin_today"]
            -
            item["margin_previous"]
        )

        # 個股融資增減金額
        margin_change_amount = (
            margin_change_shares
            *
            close_price
            *
            1000
        )

        # 個股融券增減張數
        short_change = (
            item["short_today"]
            -
            item["short_previous"]
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

    if not stocks:
        raise RuntimeError(
            "融資融券有資料，"
            "但沒有任何股票能與 MI_INDEX 收盤價對應。"
        )

    # --------------------------------------------------------
    # ★ 注意：
    # margin_total / short_total
    # 已經是 TWSE 總表的官方增減數字。
    # 這裡不再重新加總個股。
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
            margin_total,

        "short_total":
            short_total,

        "credit":
            stocks,
    }

    # --------------------------------------------------------
    # 暫存後取代正式 JSON
    # --------------------------------------------------------

    temp_file = OUTPUT_FILE.with_name(
        OUTPUT_FILE.name + ".tmp"
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
        f"【官方市場】融資增減金額："
        f"{output['margin_total']:,} 元"
    )

    print(
        f"【官方市場】融券增減張數："
        f"{output['short_total']:,} 張"
    )

    print(
        f"個股資料：{len(margin_rows)} 筆"
    )

    print(
        f"成功對應收盤價：{len(stocks)} 筆"
    )

    print(
        f"沒有對應收盤價：{no_price_count} 筆"
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
