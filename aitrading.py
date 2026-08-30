import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests


# ============================================================
# AI Trading - Taiwan Top 100
# ============================================================
#
# 功能：
# 1. 自動取得 TWSE 上市股票每日行情
# 2. 自動取得 TPEx 上櫃股票每日行情
# 3. 合併兩個市場
# 4. 依「成交金額」由高到低排序
# 5. 取前 100 檔
# 6. 自動加入三大法人買賣超資料
# 7. 輸出 tw_top100.json
#
# 本程式目前只負責建立「AI 候選股票池」
# 尚未接 AI API。
# ============================================================


TOP_N = 100

OUTPUT_FILE = Path("tw_top100.json")

TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}


# ============================================================
# 基本工具
# ============================================================

def clean_number(value):
    """
    把交易所回傳的：

        1,234,567
        1,234.56
        --
        -
        None

    轉成 Python 數字。
    """

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return value

    value = str(value).strip()

    if value in ("", "-", "--", "null", "None"):
        return None

    value = value.replace(",", "")

    try:
        if "." in value:
            return float(value)

        return int(value)

    except ValueError:
        return None


def clean_symbol(symbol):
    if symbol is None:
        return ""

    return str(symbol).strip()


def is_common_stock(symbol):
    """
    第一版只保留一般股票。

    台股常見：
    4 位數普通股票，例如 2330、2317、2454

    排除：
    ETF、權證、特別股、可轉債等非一般股票。
    """

    symbol = clean_symbol(symbol)

    return (
        len(symbol) == 4
        and symbol.isdigit()
    )


# ============================================================
# 找最近交易日
# ============================================================

def get_candidate_dates(days_back=10):
    """
    從今天往前找幾天。

    GitHub Actions 如果碰到：
        週末
        國定假日
        臨時休市

    不會直接失敗。

    會依序嘗試最近 10 天。
    """

    today = datetime.now()

    dates = []

    for i in range(days_back + 1):

        d = today - timedelta(days=i)

        dates.append({
            "twse": d.strftime("%Y%m%d"),
            "tpex": d.strftime("%Y/%m/%d"),
            "display": d.strftime("%Y-%m-%d"),
        })

    return dates


# ============================================================
# TWSE
# ============================================================

def fetch_twse(date_string):

    url = "https://www.twse.com.tw/exchangeReport/MI_INDEX"

    params = {
        "response": "json",
        "type": "ALLBUT0999",
        "date": date_string,
    }

    print(f"[TWSE] 取得資料：{date_string}")

    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    if not data:
        return []

    tables = data.get("tables", [])

    if not tables:

        print("[TWSE] 找不到 tables")

        return []

    rows = []

    target_table = None

    for table in tables:

        fields = table.get("fields", [])

        if "成交金額" in fields:

            target_table = table

            break

    if target_table is None:

        print(
            "[TWSE] 找不到包含成交金額的資料表"
        )

        return []

    fields = target_table.get(
        "fields",
        []
    )

    data_rows = target_table.get(
        "data",
        []
    )

    field_index = {
        field: index
        for index, field in enumerate(fields)
    }

    required_fields = [
        "證券代號",
        "證券名稱",
        "成交股數",
        "成交金額",
        "開盤價",
        "最高價",
        "最低價",
        "收盤價",
        "漲跌價差",
        "本益比",
    ]

    for field in required_fields:

        if field not in field_index:

            print(
                f"[TWSE] 缺少欄位：{field}"
            )

            return []

    for row in data_rows:

        try:

            symbol = clean_symbol(
                row[field_index["證券代號"]]
            )

            if not is_common_stock(symbol):
                continue

            name = str(
                row[field_index["證券名稱"]]
            ).strip()

            trading_volume = clean_number(
                row[field_index["成交股數"]]
            )

            trading_value = clean_number(
                row[field_index["成交金額"]]
            )

            close = clean_number(
                row[field_index["收盤價"]]
            )

            if trading_value is None:
                continue

            rows.append({

                "market": "TWSE",

                "symbol": symbol,

                "name": name,

                "volume": trading_volume,

                "trading_value": trading_value,

                "open": clean_number(
                    row[field_index["開盤價"]]
                ),

                "high": clean_number(
                    row[field_index["最高價"]]
                ),

                "low": clean_number(
                    row[field_index["最低價"]]
                ),

                "close": close,

                "change": clean_number(
                    row[field_index["漲跌價差"]]
                ),

                "pe": clean_number(
                    row[field_index["本益比"]]
                ),

            })

        except (
            IndexError,
            TypeError
        ):

            continue

    print(
        f"[TWSE] 成功取得 {len(rows)} 檔普通股票"
    )

    return rows


# ============================================================
# TPEx
# ============================================================

def fetch_tpex(date_string):

    url = (
        "https://www.tpex.org.tw/"
        "www/zh-tw/afterTrading/dailyQuotes"
    )

    params = {
        "response": "json",
        "date": date_string,
    }

    print(
        f"[TPEx] 取得資料：{date_string}"
    )

    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    if not data:
        return []

    tables = data.get("tables", [])

    if not tables:

        print(
            "[TPEx] 找不到 tables"
        )

        return []

    target_table = None

    for table in tables:

        fields = table.get(
            "fields",
            []
        )

        field_text = "|".join(
            str(x)
            for x in fields
        )

        if (
            "成交金額" in field_text
            or "成交千元" in field_text
        ):

            target_table = table

            break

    if target_table is None:

        target_table = tables[0]

    fields = target_table.get(
        "fields",
        []
    )

    data_rows = target_table.get(
        "data",
        []
    )

    field_index = {
        str(field): index
        for index, field in enumerate(fields)
    }

    print(
        f"[TPEx] 欄位：{fields}"
    )

    rows = []

    def find_field(*names):

        for name in names:

            if name in field_index:

                return field_index[name]

        return None

    symbol_index = find_field(
        "證券代號",
        "代號",
    )

    name_index = find_field(
        "證券名稱",
        "名稱",
    )

    volume_index = find_field(
        "成交股數",
        "成交張數",
        "成交股數(股)",
    )

    value_index = find_field(
        "成交金額",
        "成交千元",
        "成交金額(元)",
    )

    close_index = find_field(
        "收盤",
        "收盤價",
    )

    change_index = find_field(
        "漲跌",
        "漲跌價差",
    )

    open_index = find_field(
        "開盤",
        "開盤價",
    )

    high_index = find_field(
        "最高",
        "最高價",
    )

    low_index = find_field(
        "最低",
        "最低價",
    )

    pe_index = find_field(
        "本益比",
    )

    if (
        symbol_index is None
        or name_index is None
        or value_index is None
    ):

        print(
            "[TPEx] 無法辨識必要欄位"
        )

        print(
            "[TPEx] Fields =",
            fields
        )

        return []

    for row in data_rows:

        try:

            symbol = clean_symbol(
                row[symbol_index]
            )

            if not is_common_stock(symbol):
                continue

            name = str(
                row[name_index]
            ).strip()

            trading_value = clean_number(
                row[value_index]
            )

            if trading_value is None:
                continue

            if (
                fields[value_index]
                == "成交千元"
            ):

                trading_value *= 1000

            row_data = {

                "market": "TPEX",

                "symbol": symbol,

                "name": name,

                "volume": (
                    clean_number(
                        row[volume_index]
                    )
                    if volume_index is not None
                    else None
                ),

                "trading_value":
                    trading_value,

                "open": (
                    clean_number(
                        row[open_index]
                    )
                    if open_index is not None
                    else None
                ),

                "high": (
                    clean_number(
                        row[high_index]
                    )
                    if high_index is not None
                    else None
                ),

                "low": (
                    clean_number(
                        row[low_index]
                    )
                    if low_index is not None
                    else None
                ),

                "close": (
                    clean_number(
                        row[close_index]
                    )
                    if close_index is not None
                    else None
                ),

                "change": (
                    clean_number(
                        row[change_index]
                    )
                    if change_index is not None
                    else None
                ),

                "pe": (
                    clean_number(
                        row[pe_index]
                    )
                    if pe_index is not None
                    else None
                ),

            }

            rows.append(row_data)

        except (
            IndexError,
            TypeError
        ):

            continue

    print(
        f"[TPEx] 成功取得 {len(rows)} 檔普通股票"
    )

    return rows


# ============================================================
# TWSE 三大法人
# ============================================================

def fetch_twse_institutional(date_string):

    """
    TWSE T86：
    三大法人買賣超日報。

    date_string：
        YYYYMMDD

    回傳：
        {
            "2330": {
                "foreign_net": ...,
                "trust_net": ...,
                "dealer_net": ...,
                "institutional_net": ...
            }
        }
    """

    url = (
        "https://www.twse.com.tw/"
        "rwd/zh/fund/T86"
    )

    params = {
        "response": "json",
        "date": date_string,
        "selectType": "ALLBUT0999",
    }

    print(
        f"[TWSE] 取得三大法人：{date_string}"
    )

    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    if not data:

        return {}

    fields = data.get(
        "fields",
        []
    )

    rows = data.get(
        "data",
        []
    )

    if not fields or not rows:

        print(
            "[TWSE] 三大法人沒有資料"
        )

        return {}

    field_index = {
        field: index
        for index, field in enumerate(fields)
    }

    required_fields = [

        "證券代號",

        "外陸資買賣超股數(不含外資自營商)",

        "投信買賣超股數",

        "自營商買賣超股數",

        "三大法人買賣超股數",

    ]

    for field in required_fields:

        if field not in field_index:

            print(
                f"[TWSE] 三大法人缺少欄位：{field}"
            )

            print(
                "[TWSE] 實際欄位：",
                fields
            )

            return {}

    result = {}

    for row in rows:

        try:

            symbol = clean_symbol(
                row[field_index["證券代號"]]
            )

            if not is_common_stock(symbol):
                continue

            result[symbol] = {

                "foreign_net": clean_number(
                    row[
                        field_index[
                            "外陸資買賣超股數(不含外資自營商)"
                        ]
                    ]
                ),

                "trust_net": clean_number(
                    row[
                        field_index[
                            "投信買賣超股數"
                        ]
                    ]
                ),

                "dealer_net": clean_number(
                    row[
                        field_index[
                            "自營商買賣超股數"
                        ]
                    ]
                ),

                "institutional_net": clean_number(
                    row[
                        field_index[
                            "三大法人買賣超股數"
                        ]
                    ]
                ),

            }

        except (
            IndexError,
            TypeError
        ):

            continue

    print(
        f"[TWSE] 成功取得 "
        f"{len(result)} 檔法人資料"
    )

    return result


# ============================================================
# TPEx 三大法人
# ============================================================

def fetch_tpex_institutional():

    """
    TPEx OpenAPI：

    tpex_3insti_daily_trading

    回傳上櫃股票三大法人買賣超。
    """

    url = (
        "https://www.tpex.org.tw/"
        "openapi/v1/"
        "tpex_3insti_daily_trading"
    )

    print(
        "[TPEx] 取得三大法人資料"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):

        print(
            "[TPEx] 三大法人資料格式異常"
        )

        return {}

    result = {}

    for row in data:

        if not isinstance(row, dict):
            continue

        symbol = clean_symbol(
            row.get(
                "SecuritiesCompanyCode",
                ""
            )
        )

        if not is_common_stock(symbol):
            continue

        foreign_net = clean_number(
            row.get(
                "Foreign Investors include Mainland Area Investors "
                "(Foreign Dealers excluded)-Difference"
            )
        )

        trust_net = clean_number(
            row.get(
                "SecuritiesInvestmentTrustCompanies-Difference"
            )
        )

        dealer_net = clean_number(
            row.get(
                "Dealers-Difference"
            )
        )

        institutional_net = clean_number(
            row.get(
                "TotalDifference"
            )
        )

        result[symbol] = {

            "foreign_net": foreign_net,

            "trust_net": trust_net,

            "dealer_net": dealer_net,

            "institutional_net":
                institutional_net,

        }

    print(
        f"[TPEx] 成功取得 "
        f"{len(result)} 檔法人資料"
    )

    return result


# ============================================================
# 找最近真正有資料的交易日
# ============================================================

def fetch_latest_market_data():

    for candidate in get_candidate_dates(10):

        print()
        print("=" * 60)
        print(
            "嘗試交易日：",
            candidate["display"]
        )
        print("=" * 60)

        try:

            twse_rows = fetch_twse(
                candidate["twse"]
            )

            time.sleep(1)

            tpex_rows = fetch_tpex(
                candidate["tpex"]
            )

            if twse_rows and tpex_rows:

                return (
                    candidate["display"],
                    candidate["twse"],
                    candidate["tpex"],
                    twse_rows,
                    tpex_rows,
                )

        except requests.RequestException as exc:

            print(
                f"[WARNING] API 連線失敗：{exc}"
            )

        except ValueError as exc:

            print(
                f"[WARNING] JSON 解析失敗：{exc}"
            )

        time.sleep(1)

    raise RuntimeError(
        "最近 10 天找不到有效的 TWSE / TPEx 交易資料。"
    )


# ============================================================
# 建立 Top 100
# ============================================================

def build_top100(
    date_string,
    twse_rows,
    tpex_rows,
    twse_institutional,
    tpex_institutional,
):

    all_stocks = (
        twse_rows +
        tpex_rows
    )

    unique = {}

    for stock in all_stocks:

        key = (
            stock["market"],
            stock["symbol"],
        )

        unique[key] = stock

    all_stocks = list(
        unique.values()
    )

    # --------------------------------------------------------
    # 先依成交金額排序
    # --------------------------------------------------------

    all_stocks.sort(
        key=lambda x: (
            x["trading_value"] or 0
        ),
        reverse=True,
    )

    top100 = all_stocks[:TOP_N]

    # --------------------------------------------------------
    # 加入法人資料
    # --------------------------------------------------------

    for stock in top100:

        symbol = stock["symbol"]

        if stock["market"] == "TWSE":

            institution = (
                twse_institutional.get(
                    symbol
                )
            )

        else:

            institution = (
                tpex_institutional.get(
                    symbol
                )
            )

        if institution is None:

            institution = {

                "foreign_net": None,

                "trust_net": None,

                "dealer_net": None,

                "institutional_net": None,

            }

        stock.update(
            institution
        )

    # --------------------------------------------------------
    # 加入排名
    # --------------------------------------------------------

    for index, stock in enumerate(
        top100,
        start=1
    ):

        stock["rank"] = index

    return top100


# ============================================================
# 輸出 JSON
# ============================================================

def save_json(
    date_string,
    stocks,
):

    output = {

        "generated_at":
            datetime.now().isoformat(
                timespec="seconds"
            ),

        "date":
            date_string,

        "market":
            "TW",

        "ranking_method":
            "trading_value",

        "ranking_method_name":
            "成交金額",

        "top_n":
            TOP_N,

        "source": [

            "TWSE",

            "TPEx",

            "TWSE T86",

            "TPEx 3insti",

        ],

        "institutional_data": {

            "unit":
                "shares",

            "positive":
                "net_buy",

            "negative":
                "net_sell",

        },

        "stocks":
            stocks,

    }

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print("=" * 60)
    print(
        f"完成：{OUTPUT_FILE}"
    )
    print(
        f"交易日：{date_string}"
    )
    print(
        f"股票數量：{len(stocks)}"
    )
    print("=" * 60)


# ============================================================
# 主程式
# ============================================================

def main():

    print()
    print("=" * 60)
    print(
        "AI Trading - Taiwan Top 100"
    )
    print("=" * 60)

    (
        date_string,
        twse_date,
        tpex_date,
        twse_rows,
        tpex_rows,
    ) = fetch_latest_market_data()

    # --------------------------------------------------------
    # 三大法人
    # --------------------------------------------------------

    time.sleep(1)

    twse_institutional = (
        fetch_twse_institutional(
            twse_date
        )
    )

    time.sleep(1)

    tpex_institutional = (
        fetch_tpex_institutional()
    )

    # --------------------------------------------------------
    # 建立 Top 100
    # --------------------------------------------------------

    top100 = build_top100(

        date_string,

        twse_rows,

        tpex_rows,

        twse_institutional,

        tpex_institutional,

    )

    if len(top100) < TOP_N:

        print(
            f"[WARNING] Top 100 只有 "
            f"{len(top100)} 檔"
        )

    save_json(
        date_string,
        top100,
    )

    # --------------------------------------------------------
    # 顯示前 10 名
    # --------------------------------------------------------

    print()
    print(
        "前 10 名："
    )

    for stock in top100[:10]:

        value = stock[
            "trading_value"
        ]

        foreign = stock[
            "foreign_net"
        ]

        trust = stock[
            "trust_net"
        ]

        dealer = stock[
            "dealer_net"
        ]

        total = stock[
            "institutional_net"
        ]

        print()

        print(
            f'{stock["rank"]:>3}. '
            f'{stock["symbol"]} '
            f'{stock["name"]:<10} '
            f'{stock["market"]:<5} '
            f'成交金額={value:,}'
        )

        print(
            f'    外資={foreign} '
            f'投信={trust} '
            f'自營商={dealer} '
            f'三大法人={total}'
        )

    print()
    print(
        "完成。"
    )


if __name__ == "__main__":

    main()
