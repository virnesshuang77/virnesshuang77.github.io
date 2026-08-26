# credit.py
# -*- coding: utf-8 -*-

"""
每日抓取 TWSE 融資融券資料
輸出：credit_rank.json

資料來源：
    TWSE MI_MARGN
    TWSE MI_INDEX / STOCK_DAY_ALL

核心規則：
    個股融資增減張數 =
        今日融資餘額 - 前日融資餘額

    個股融資增減金額 =
        融資增減張數 × 收盤價 × 1000

    個股融券增減張數 =
        今日融券餘額 - 前日融券餘額

    全市場融資增減金額 =
        TWSE 官方「融資金額(仟元)」
        今日餘額 - 前日餘額，再 × 1000

    全市場融券增減張數 =
        TWSE 官方「融券(交易單位)」
        今日餘額 - 前日餘額

重要：
    MI_MARGN 有「信用交易統計」與「融資融券彙總(全部)」兩張表。
    個股資料一定要從第二張「融資融券彙總」表取得。

    個股表欄位：
        代號
        名稱
        買進
        賣出
        現金償還
        前日餘額       <- 融資
        今日餘額       <- 融資
        次一營業日限額
        買進
        賣出
        現券償還
        前日餘額       <- 融券
        今日餘額       <- 融券
        ...
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests


# ============================================================
# 基本設定
# ============================================================

OUTPUT_FILE = Path("credit_rank.json")

MARGIN_URLS = [
    "https://www.twse.com.tw/exchangeReport/MI_MARGN",
    "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN",
    "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN",
]

PRICE_URLS = [
    "https://www.twse.com.tw/exchangeReport/MI_INDEX",
    "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
    "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL",
    "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL",
    "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
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

    # TWSE 偶爾會回傳空白/HTML；這裡直接讓錯誤浮出來
    return response.json()


# ============================================================
# 數字處理
# ============================================================

def to_number(value):
    if value is None:
        return 0.0

    text = str(value).strip()

    if text in ("", "--", "---", "—", "－"):
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

    if not text.isdigit():
        return ""

    # TWSE 上市股票/ETF 代號通常 4~6 碼
    if not (4 <= len(text) <= 6):
        return ""

    return text


# ============================================================
# 找最近交易日
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
# MI_MARGN
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
            print(f"[INFO] 嘗試 API：{url}")

            data = get_json(
                url,
                params=params,
                timeout=30,
            )

            if isinstance(data, dict) and data.get("stat") == "OK":
                print(f"[OK] API 回應成功：{url}")
                return data

            last_error = RuntimeError(
                f"API stat 非 OK："
                f"{data.get('stat') if isinstance(data, dict) else type(data)}"
            )

        except Exception as e:
            last_error = e
            print(f"[WARN] API 失敗：{url} -> {e}")

    raise RuntimeError(
        f"所有 MI_MARGN API 都失敗：{last_error}"
    )


# ============================================================
# 將 TWSE tables / creditList 正規化
# ============================================================

def get_table_objects(data):
    """
    回傳：
        [
            {
                "title": ...,
                "fields": [...],
                "data": [...]
            },
            ...
        ]

    支援：
        1. 新版 tables 結構
        2. 舊版 creditList 結構
    """

    result = []

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
                    "title": str(table.get("title", "")),
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

            # 可能是：
            # [header, row1, row2, ...]
            header = block[0]

            if not isinstance(header, list):
                continue

            fields = [
                str(x).strip()
                for x in header
            ]

            result.append(
                {
                    "title": "",
                    "fields": fields,
                    "data": block[1:],
                }
            )

    return result


# ============================================================
# 找欄位
# ============================================================

def find_indices(fields, name):
    return [
        i
        for i, value in enumerate(fields)
        if str(value).strip() == name
    ]


# ============================================================
# 解析官方市場總表
# ============================================================

def parse_market_summary(data):
    """
    第一張表：

        項目
        買進
        賣出
        現金(券)償還
        前日餘額
        今日餘額

    找：
        融資(交易單位)
        融券(交易單位)
        融資金額(仟元)
    """

    tables = get_table_objects(data)

    target = None

    for table in tables:
        fields = table["fields"]

        if "項目" in fields and "前日餘額" in fields:
            target = table
            break

    if target is None:
        raise RuntimeError(
            "找不到 MI_MARGN「信用交易統計」市場總表"
        )

    fields = target["fields"]
    rows = target["data"]

    item_idx = fields.index("項目")
    previous_idx = find_indices(fields, "前日餘額")
    today_idx = find_indices(fields, "今日餘額")

    if not previous_idx or not today_idx:
        raise RuntimeError(
            "市場總表缺少前日餘額/今日餘額"
        )

    previous_idx = previous_idx[0]
    today_idx = today_idx[0]

    margin_row = None
    short_row = None
    margin_amount_row = None

    for row in rows:
        if not isinstance(row, list):
            continue

        if max(item_idx, previous_idx, today_idx) >= len(row):
            continue

        title = str(row[item_idx]).strip()

        if title == "融資(交易單位)":
            margin_row = row

        elif title == "融券(交易單位)":
            short_row = row

        elif title == "融資金額(仟元)":
            margin_amount_row = row

    if margin_row is None:
        raise RuntimeError("找不到市場「融資(交易單位)」")

    if short_row is None:
        raise RuntimeError("找不到市場「融券(交易單位)」")

    if margin_amount_row is None:
        raise RuntimeError("找不到市場「融資金額(仟元)」")

    margin_previous_shares = to_number(
        margin_row[previous_idx]
    )
    margin_today_shares = to_number(
        margin_row[today_idx]
    )

    short_previous = to_number(
        short_row[previous_idx]
    )
    short_today = to_number(
        short_row[today_idx]
    )

    margin_previous_amount_k = to_number(
        margin_amount_row[previous_idx]
    )
    margin_today_amount_k = to_number(
        margin_amount_row[today_idx]
    )

    margin_change_amount = (
        margin_today_amount_k
        - margin_previous_amount_k
    ) * 1000

    short_change = (
        short_today
        - short_previous
    )

    print(
        "[OK] 官方市場融資金額："
        f"{margin_previous_amount_k:,.0f} 仟元"
        f" -> {margin_today_amount_k:,.0f} 仟元"
        f" -> 增減 {margin_change_amount:,.0f} 元"
    )

    print(
        "[OK] 官方市場融券："
        f"{short_previous:,.0f} 張"
        f" -> {short_today:,.0f} 張"
        f" -> 增減 {short_change:,.0f} 張"
    )

    return {
        "margin_change_amount": margin_change_amount,
        "short_change": short_change,
    }


# ============================================================
# 找個股融資融券表
# ============================================================

def find_stock_table(data):
    tables = get_table_objects(data)

    for table in tables:
        fields = table["fields"]

        # 個股表一定同時有：
        # 代號、名稱
        # 而且「前日餘額」「今日餘額」各出現兩次
        if (
            "代號" in fields
            and "名稱" in fields
            and len(find_indices(fields, "前日餘額")) >= 2
            and len(find_indices(fields, "今日餘額")) >= 2
        ):
            return table

    return None


# ============================================================
# 解析個股
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

    previous_indices = find_indices(
        fields,
        "前日餘額",
    )

    today_indices = find_indices(
        fields,
        "今日餘額",
    )

    # 第一組 = 融資
    # 第二組 = 融券
    margin_previous_idx = previous_indices[0]
    margin_today_idx = today_indices[0]

    short_previous_idx = previous_indices[1]
    short_today_idx = today_indices[1]

    print(
        "[OK] 個股欄位位置："
        f"代號={stock_id_idx}, "
        f"名稱={stock_name_idx}, "
        f"融資前日餘額={margin_previous_idx}, "
        f"融資今日餘額={margin_today_idx}, "
        f"融券前日餘額={short_previous_idx}, "
        f"融券今日餘額={short_today_idx}"
    )

    result = []

    for row in rows:
        if not isinstance(row, list):
            continue

        required = [
            stock_id_idx,
            stock_name_idx,
            margin_previous_idx,
            margin_today_idx,
            short_previous_idx,
            short_today_idx,
        ]

        if max(required) >= len(row):
            continue

        stock_id = clean_stock_id(
            row[stock_id_idx]
        )

        if not stock_id:
            continue

        stock_name = str(
            row[stock_name_idx]
        ).strip()

        margin_previous = to_number(
            row[margin_previous_idx]
        )

        margin_today = to_number(
            row[margin_today_idx]
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
                "margin_previous": margin_previous,
                "margin_today": margin_today,
                "short_previous": short_previous,
                "short_today": short_today,
            }
        )

    print(
        f"[OK] 成功解析 {len(result)} 筆融資融券股票"
    )

    # --------------------------------------------------------
    # 特別檢查 2330
    # --------------------------------------------------------
    for item in result:
        if item["stock_id"] == "2330":
            print(
                "[DEBUG] 2330 台積電："
                f"融資前日={item['margin_previous']:,.0f}，"
                f"融資今日={item['margin_today']:,.0f}，"
                f"融資張數增減="
                f"{item['margin_today'] - item['margin_previous']:,.0f}，"
                f"融券前日={item['short_previous']:,.0f}，"
                f"融券今日={item['short_today']:,.0f}，"
                f"融券張數增減="
                f"{item['short_today'] - item['short_previous']:,.0f}"
            )
            break

    return result


# ============================================================
# 收盤價
# ============================================================

def parse_price_table(data):
    """
    支援：
        STOCK_DAY_ALL：
            Code / ClosingPrice

        MI_INDEX：
            證券代號 / 證券名稱 / 收盤價
    """

    prices = {}

    # --------------------------------------------------------
    # STOCK_DAY_ALL / OpenAPI 類型：list[dict]
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
    # MI_INDEX / tables
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
                continue

            fields = [
                str(x).strip()
                for x in fields
            ]

            code_candidates = [
                "證券代號",
                "代號",
                "Code",
            ]

            price_candidates = [
                "收盤價",
                "成交價",
                "ClosingPrice",
            ]

            code_idx = None
            price_idx = None

            for name in code_candidates:
                if name in fields:
                    code_idx = fields.index(name)
                    break

            for name in price_candidates:
                if name in fields:
                    price_idx = fields.index(name)
                    break

            if code_idx is None or price_idx is None:
                continue

            for row in rows:
                if not isinstance(row, list):
                    continue

                if max(code_idx, price_idx) >= len(row):
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
    print(f"[INFO] 取得收盤價：{date}")

    params = {
        "date": date,
        "response": "json",
    }

    # MI_INDEX 需要 type=ALLBUT0999 的版本有時候才完整
    extra_params = [
        params,
        {
            "date": date,
            "response": "json",
            "type": "ALLBUT0999",
        },
    ]

    last_error = None

    for url in PRICE_URLS:
        for current_params in extra_params:
            try:
                print(
                    f"[INFO] 嘗試收盤價 API：{url}"
                )

                data = get_json(
                    url,
                    params=current_params,
                    timeout=30,
                )

                prices = parse_price_table(data)

                if prices:
                    print(
                        f"[OK] 成功解析 {len(prices)} 筆收盤價：{url}"
                    )
                    return prices

                last_error = RuntimeError(
                    "API 成功但沒有解析到收盤價"
                )

            except Exception as e:
                last_error = e
                print(
                    f"[WARN] 收盤價 API 失敗："
                    f"{url} -> {e}"
                )

    raise RuntimeError(
        f"完全取得不到收盤價：{last_error}"
    )


# ============================================================
# 找最近交易日
# ============================================================

def find_latest_data():
    for date in get_candidate_dates():
        try:
            data = fetch_margin(date)

            api_date = str(
                data.get("date", "")
            ).strip()

            if api_date.isdigit() and len(api_date) == 8:
                actual_date = api_date
            else:
                actual_date = date

            print(
                f"[OK] 找到交易日：{actual_date}"
            )

            return actual_date, data

        except Exception as e:
            print(
                f"[WARN] {date} 無資料：{e}"
            )

        time.sleep(0.5)

    raise RuntimeError(
        "找不到最近的融資融券資料"
    )


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
        f"[INFO] 融資融券個股資料："
        f"{len(stock_rows)} 筆"
    )

    # --------------------------------------------------------
    # 收盤價
    # --------------------------------------------------------
    prices = fetch_prices(date)

    # --------------------------------------------------------
    # 建立個股 JSON
    # --------------------------------------------------------
    stocks = []

    margin_increase_count = 0
    margin_decrease_count = 0
    short_increase_count = 0
    short_decrease_count = 0

    matched_prices = 0
    missing_prices = 0

    for item in stock_rows:
        stock_id = item["stock_id"]
        stock_name = item["stock_name"]

        close_price = prices.get(
            stock_id,
            0
        )

        margin_change_shares = (
            item["margin_today"]
            - item["margin_previous"]
        )

        short_change = (
            item["short_today"]
            - item["short_previous"]
        )

        # ----------------------------------------------------
        # 沒有收盤價仍保留資料，但 margin_change 金額設 0
        # 避免錯誤估算
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
                "margin_change": round(
                    margin_change_amount,
                    2,
                ),
                "short_change": int(
                    short_change
                ),
            }
        )

    # --------------------------------------------------------
    # 特別印出 2330 最終結果
    # --------------------------------------------------------
    for item in stocks:
        if item["stock_id"] == "2330":
            print()
            print(
                "[DEBUG] 最終 JSON 2330 台積電："
            )
            print(
                f"  收盤價：{item['close_price']}"
            )
            print(
                f"  融資增減金額："
                f"{item['margin_change']:,.0f}"
            )
            print(
                f"  融券增減張數："
                f"{item['short_change']:,}"
            )
            break

    # --------------------------------------------------------
    # 更新時間
    # --------------------------------------------------------
    update_time = datetime.now().strftime(
        "%H:%M:%S"
    )

    output = {
        "data_date": (
            f"{date[:4]}/{date[4:6]}/{date[6:8]}"
        ),
        "update_time": update_time,

        # 官方市場總表
        "margin_total": round(
            market["margin_change_amount"],
            2,
        ),
        "short_total": int(
            market["short_change"]
        ),

        # 個股
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
        f"資料日期：{output['data_date']}"
    )

    print(
        f"更新時間：{output['update_time']}"
    )

    print(
        "官方融資增減金額："
        f"{output['margin_total']:,.0f} 元"
    )

    print(
        "官方融券增減張數："
        f"{output['short_total']:,} 張"
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
        f"輸出檔案：{OUTPUT_FILE}"
    )

    # 如果真的完全沒有負的融資個股，直接警告
    if margin_decrease_count == 0:
        print()
        print(
            "[WARN] 融資減少個股 = 0。"
        )
        print(
            "[WARN] 請檢查 TWSE 個股表欄位是否異常。"
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
