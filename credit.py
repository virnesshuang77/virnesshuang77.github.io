# credit.py
# -*- coding: utf-8 -*-

"""
每天抓取 TWSE 融資融券資料
--------------------------------
輸出：
    credit_rank.json

資料來源：
    TWSE MI_MARGN
    TWSE MI_INDEX

主要功能：
    1. 取得上市股票融資融券餘額
    2. 取得上市股票收盤價
    3. 計算個股融資增減金額
    4. 計算個股融券增減張數
    5. 計算全市場融資增減金額
    6. 計算全市場融券增減張數
    7. 輸出給 credit.html 使用

注意：
    融資增減金額 =
    (今日融資餘額 - 前日融資餘額)
    × 收盤價
    × 1000

    融券增減張數 =
    今日融券餘額 - 前日融券餘額
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

MARGIN_URL = (
    TWSE_BASE
    + "/rwd/zh/marginTrading/MI_MARGN"
)

PRICE_URL = (
    TWSE_BASE
    + "/rwd/zh/afterTrading/STOCK_DAY_ALL"
)

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


# ============================================================
# 找最近交易日
# ============================================================

def get_candidate_dates():

    today = datetime.now()

    dates = []

    for i in range(0, 10):

        d = today - timedelta(days=i)

        # 排除週末
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

    params = {
        "date": date,
        "selectType": "ALL",
        "response": "json",
    }

    print(
        f"[INFO] 取得融資融券：{date}"
    )

    data = get_json(
        MARGIN_URL,
        params=params,
    )

    if data.get("stat") != "OK":
        return None

    return data


# ============================================================
# 解析融資融券
# ============================================================

def parse_margin(data):

    """
    MI_MARGN 的 creditList 結構：

    每筆大致包含：

    股票代號
    股票名稱
    融資前日餘額
    融資買進
    融資賣出
    現金償還
    融資今日餘額
    ...
    融券前日餘額
    融券賣出
    融券買進
    現券償還
    融券今日餘額
    ...

    TWSE API 不同時期可能有些欄位變化，
    因此下面採用表頭定位，而不是硬寫 index。
    """

    credit_list = data.get(
        "creditList",
        []
    )

    result = []

    for block in credit_list:

        if not isinstance(block, list):
            continue

        # 第一列通常是表頭
        if len(block) < 2:
            continue

        header = block[0]
        rows = block[1:]

        if not isinstance(header, list):
            continue

        # 找欄位
        header_map = {}

        for index, name in enumerate(header):

            header_map[
                str(name).strip()
            ] = index

        # ----------------------------------------------------
        # 有些 API 會把股票資料再包一層
        # ----------------------------------------------------

        for row in rows:

            if not isinstance(row, list):
                continue

            if len(row) < 5:
                continue

            # ------------------------------------------------
            # 最穩定的方式：
            # 依常見 MI_MARGN 欄位位置解析
            # ------------------------------------------------

            try:

                stock_id = str(
                    row[0]
                ).strip()

                stock_name = str(
                    row[1]
                ).strip()

                if not stock_id:
                    continue

                # ------------------------------------------------
                # 標準 MI_MARGN：
                #
                # 0 證券代號
                # 1 證券名稱
                #
                # 2 融資前日餘額
                # 3 融資買進
                # 4 融資賣出
                # 5 現金償還
                # 6 融資今日餘額
                #
                # 7 融資限額
                #
                # 8 融券前日餘額
                # 9 融券賣出
                # 10 融券買進
                # 11 現券償還
                # 12 融券今日餘額
                # ------------------------------------------------

                margin_previous = to_number(
                    row[2]
                )

                margin_today = to_number(
                    row[6]
                )

                short_previous = to_number(
                    row[8]
                )

                short_today = to_number(
                    row[12]
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

            except Exception as e:

                print(
                    "[WARN] 解析個股失敗：",
                    row,
                    e
                )

    return result


# ============================================================
# 取得上市股票收盤價
# ============================================================

def fetch_prices(date):

    params = {
        "date": date,
        "response": "json",
    }

    print(
        f"[INFO] 取得收盤價：{date}"
    )

    data = get_json(
        PRICE_URL,
        params=params,
    )

    if not isinstance(data, list):
        return {}

    prices = {}

    for row in data:

        if not isinstance(row, dict):
            continue

        stock_id = str(
            row.get("Code", "")
        ).strip()

        close_price = (
            row.get("ClosingPrice")
        )

        if not stock_id:
            continue

        prices[stock_id] = to_number(
            close_price
        )

    return prices


# ============================================================
# 數字轉換
# ============================================================

def to_number(value):

    if value is None:
        return 0

    text = str(value).strip()

    if text == "":
        return 0

    text = (
        text
        .replace(",", "")
        .replace("--", "0")
        .replace(" ", "")
    )

    try:
        return float(text)
    except Exception:
        return 0


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
# 找最新交易日
# ============================================================

def find_latest_data():

    for date in get_candidate_dates():

        try:

            data = fetch_margin(
                date
            )

            if data:

                print(
                    f"[OK] 找到交易日：{date}"
                )

                return (
                    date,
                    data
                )

        except Exception as e:

            print(
                f"[WARN] {date} 無資料：{e}"
            )

        time.sleep(0.5)

    raise RuntimeError(
        "找不到最近的融資融券資料"
    )


# ============================================================
# 建立 credit_rank.json
# ============================================================

def build_json():

    date, margin_data = (
        find_latest_data()
    )

    margin_rows = parse_margin(
        margin_data
    )

    print(
        f"[INFO] 融資融券資料："
        f"{len(margin_rows)} 筆"
    )

    # --------------------------------------------------------
    # 收盤價
    # --------------------------------------------------------

    try:

        prices = fetch_prices(
            date
        )

    except Exception as e:

        print(
            "[WARN] 收盤價取得失敗：",
            e
        )

        prices = {}

    # --------------------------------------------------------
    # 建立個股資料
    # --------------------------------------------------------

    stocks = []

    margin_total = 0
    short_total = 0

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
                "stock_id": stock_id,
                "stock_name": stock_name,
                "close_price": close_price,

                "margin_change":
                    margin_change_amount,

                "short_change":
                    short_change,
            }
        )

    # --------------------------------------------------------
    # 移除沒有股價的資料
    # --------------------------------------------------------

    stocks = [
        x
        for x in stocks
        if x["close_price"] > 0
    ]

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
                2
            ),

        "short_total":
            int(
                short_total
            ),

        "credit":
            stocks,
    }

    # --------------------------------------------------------
    # 寫 JSON
    # --------------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2
        )

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
