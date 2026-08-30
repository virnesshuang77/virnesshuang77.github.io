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
# 1. TWSE + TPEx
# 2. 依成交金額取得 Top 100
# 3. 三大法人
# 4. 歷史收盤價 / 成交量
# 5. 計算：
#       - change_percent
#       - 5 / 20 / 60 / 120 / 250 日報酬
#       - MA5 / MA20 / MA60 / MA120
#       - 20 日平均成交量
#       - 20 日成交量比
#
# 歷史資料會保存於：
#       tw_history.json
#
# Top 100 結果：
#       tw_top100.json
#
# ============================================================


TOP_N = 100

OUTPUT_FILE = Path("tw_top100.json")

HISTORY_FILE = Path("tw_history.json")

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

    symbol = clean_symbol(symbol)

    return (
        len(symbol) == 4
        and symbol.isdigit()
    )


# ============================================================
# 日期
# ============================================================

def get_candidate_dates(days_back=10):

    today = datetime.now()

    dates = []

    for i in range(days_back + 1):

        d = today - timedelta(days=i)

        dates.append({

            "twse": d.strftime("%Y%m%d"),

            "tpex": d.strftime("%Y/%m/%d"),

            "display":
                d.strftime("%Y-%m-%d"),

        })

    return dates


# ============================================================
# TWSE 當日行情
# ============================================================

def fetch_twse(date_string):

    url = (
        "https://www.twse.com.tw/"
        "exchangeReport/MI_INDEX"
    )

    params = {

        "response": "json",

        "type": "ALLBUT0999",

        "date": date_string,

    }

    print(
        f"[TWSE] 取得資料：{date_string}"
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

    tables = data.get(
        "tables",
        []
    )

    if not tables:

        print(
            "[TWSE] 找不到 tables"
        )

        return []

    target_table = None

    for table in tables:

        fields = table.get(
            "fields",
            []
        )

        if "成交金額" in fields:

            target_table = table

            break

    if target_table is None:

        print(
            "[TWSE] 找不到成交金額表格"
        )

        return []

    fields = target_table.get(
        "fields",
        []
    )

    rows = target_table.get(
        "data",
        []
    )

    field_index = {

        field: index

        for index, field in enumerate(
            fields
        )

    }

    required = [

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

    for field in required:

        if field not in field_index:

            print(
                f"[TWSE] 缺少欄位：{field}"
            )

            return []

    result = []

    for row in rows:

        try:

            symbol = clean_symbol(
                row[
                    field_index[
                        "證券代號"
                    ]
                ]
            )

            if not is_common_stock(symbol):
                continue

            trading_value = clean_number(
                row[
                    field_index[
                        "成交金額"
                    ]
                ]
            )

            if trading_value is None:
                continue

            result.append({

                "market": "TWSE",

                "symbol": symbol,

                "name":
                    str(
                        row[
                            field_index[
                                "證券名稱"
                            ]
                        ]
                    ).strip(),

                "volume":
                    clean_number(
                        row[
                            field_index[
                                "成交股數"
                            ]
                        ]
                    ),

                "trading_value":
                    trading_value,

                "open":
                    clean_number(
                        row[
                            field_index[
                                "開盤價"
                            ]
                        ]
                    ),

                "high":
                    clean_number(
                        row[
                            field_index[
                                "最高價"
                            ]
                        ]
                    ),

                "low":
                    clean_number(
                        row[
                            field_index[
                                "最低價"
                            ]
                        ]
                    ),

                "close":
                    clean_number(
                        row[
                            field_index[
                                "收盤價"
                            ]
                        ]
                    ),

                "change":
                    clean_number(
                        row[
                            field_index[
                                "漲跌價差"
                            ]
                        ]
                    ),

                "pe":
                    clean_number(
                        row[
                            field_index[
                                "本益比"
                            ]
                        ]
                    ),

            })

        except (
            IndexError,
            TypeError
        ):

            continue

    print(
        f"[TWSE] 成功取得 {len(result)} 檔"
    )

    return result


# ============================================================
# TPEx 當日行情
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

    tables = data.get(
        "tables",
        []
    )

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

    rows = target_table.get(
        "data",
        []
    )

    field_index = {

        str(field): index

        for index, field in enumerate(
            fields
        )

    }

    def find_field(*names):

        for name in names:

            if name in field_index:

                return field_index[name]

        return None

    symbol_i = find_field(
        "證券代號",
        "代號"
    )

    name_i = find_field(
        "證券名稱",
        "名稱"
    )

    volume_i = find_field(
        "成交股數",
        "成交張數",
        "成交股數(股)"
    )

    value_i = find_field(
        "成交金額",
        "成交千元",
        "成交金額(元)"
    )

    open_i = find_field(
        "開盤",
        "開盤價"
    )

    high_i = find_field(
        "最高",
        "最高價"
    )

    low_i = find_field(
        "最低",
        "最低價"
    )

    close_i = find_field(
        "收盤",
        "收盤價"
    )

    change_i = find_field(
        "漲跌",
        "漲跌價差"
    )

    pe_i = find_field(
        "本益比"
    )

    if (
        symbol_i is None
        or name_i is None
        or value_i is None
    ):

        print(
            "[TPEx] 找不到必要欄位"
        )

        print(
            "[TPEx] Fields =",
            fields
        )

        return []

    result = []

    for row in rows:

        try:

            symbol = clean_symbol(
                row[symbol_i]
            )

            if not is_common_stock(symbol):
                continue

            trading_value = clean_number(
                row[value_i]
            )

            if trading_value is None:
                continue

            if (
                fields[value_i]
                == "成交千元"
            ):

                trading_value *= 1000

            result.append({

                "market": "TPEX",

                "symbol": symbol,

                "name":
                    str(
                        row[name_i]
                    ).strip(),

                "volume":
                    clean_number(
                        row[volume_i]
                    )
                    if volume_i is not None
                    else None,

                "trading_value":
                    trading_value,

                "open":
                    clean_number(
                        row[open_i]
                    )
                    if open_i is not None
                    else None,

                "high":
                    clean_number(
                        row[high_i]
                    )
                    if high_i is not None
                    else None,

                "low":
                    clean_number(
                        row[low_i]
                    )
                    if low_i is not None
                    else None,

                "close":
                    clean_number(
                        row[close_i]
                    )
                    if close_i is not None
                    else None,

                "change":
                    clean_number(
                        row[change_i]
                    )
                    if change_i is not None
                    else None,

                "pe":
                    clean_number(
                        row[pe_i]
                    )
                    if pe_i is not None
                    else None,

            })

        except (
            IndexError,
            TypeError
        ):

            continue

    print(
        f"[TPEx] 成功取得 {len(result)} 檔"
    )

    return result


# ============================================================
# TWSE 三大法人
# ============================================================

def fetch_twse_institutional(
    date_string
):

    url = (
        "https://www.twse.com.tw/"
        "rwd/zh/fund/T86"
    )

    params = {

        "response": "json",

        "date": date_string,

        "selectType":
            "ALLBUT0999",

    }

    print(
        f"[TWSE] 取得三大法人："
        f"{date_string}"
    )

    response = requests.get(

        url,

        params=params,

        headers=HEADERS,

        timeout=TIMEOUT,

    )

    response.raise_for_status()

    data = response.json()

    fields = data.get(
        "fields",
        []
    )

    rows = data.get(
        "data",
        []
    )

    if not fields or not rows:

        return {}

    field_index = {

        field: index

        for index, field in enumerate(
            fields
        )

    }

    required = [

        "證券代號",

        "外陸資買賣超股數(不含外資自營商)",

        "投信買賣超股數",

        "自營商買賣超股數",

        "三大法人買賣超股數",

    ]

    for field in required:

        if field not in field_index:

            print(
                f"[TWSE] 法人缺少："
                f"{field}"
            )

            return {}

    result = {}

    for row in rows:

        try:

            symbol = clean_symbol(
                row[
                    field_index[
                        "證券代號"
                    ]
                ]
            )

            if not is_common_stock(symbol):
                continue

            result[symbol] = {

                "foreign_net":
                    clean_number(
                        row[
                            field_index[
                                "外陸資買賣超股數(不含外資自營商)"
                            ]
                        ]
                    ),

                "trust_net":
                    clean_number(
                        row[
                            field_index[
                                "投信買賣超股數"
                            ]
                        ]
                    ),

                "dealer_net":
                    clean_number(
                        row[
                            field_index[
                                "自營商買賣超股數"
                            ]
                        ]
                    ),

                "institutional_net":
                    clean_number(
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
        f"[TWSE] 法人資料："
        f"{len(result)} 檔"
    )

    return result


# ============================================================
# TPEx 三大法人
# ============================================================

def fetch_tpex_institutional():

    url = (
        "https://www.tpex.org.tw/"
        "openapi/v1/"
        "tpex_3insti_daily_trading"
    )

    print(
        "[TPEx] 取得三大法人"
    )

    response = requests.get(

        url,

        headers=HEADERS,

        timeout=TIMEOUT,

    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):

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

        result[symbol] = {

            "foreign_net":
                clean_number(
                    row.get(
                        "Foreign Investors include Mainland Area Investors "
                        "(Foreign Dealers excluded)-Difference"
                    )
                ),

            "trust_net":
                clean_number(
                    row.get(
                        "SecuritiesInvestmentTrustCompanies-Difference"
                    )
                ),

            "dealer_net":
                clean_number(
                    row.get(
                        "Dealers-Difference"
                    )
                ),

            "institutional_net":
                clean_number(
                    row.get(
                        "TotalDifference"
                    )
                ),

        }

    print(
        f"[TPEx] 法人資料："
        f"{len(result)} 檔"
    )

    return result


# ============================================================
# 取得最新交易日
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

            twse = fetch_twse(
                candidate["twse"]
            )

            time.sleep(1)

            tpex = fetch_tpex(
                candidate["tpex"]
            )

            if twse and tpex:

                return (

                    candidate["display"],

                    candidate["twse"],

                    candidate["tpex"],

                    twse,

                    tpex,

                )

        except requests.RequestException as exc:

            print(
                f"[WARNING] API：{exc}"
            )

        except ValueError as exc:

            print(
                f"[WARNING] JSON：{exc}"
            )

        time.sleep(1)

    raise RuntimeError(
        "找不到最近交易日資料"
    )


# ============================================================
# 歷史資料：讀取
# ============================================================

def load_history():

    if not HISTORY_FILE.exists():

        return {}

    try:

        with HISTORY_FILE.open(
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if not isinstance(data, dict):

            return {}

        return data

    except (
        json.JSONDecodeError,
        OSError
    ):

        print(
            "[WARNING] 歷史資料讀取失敗，"
            "重新建立。"
        )

        return {}


# ============================================================
# 歷史資料：更新
# ============================================================

def update_history(
    history,
    date_string,
    twse_rows,
    tpex_rows
):

    if date_string not in history:

        history[date_string] = {}

    all_rows = (
        twse_rows +
        tpex_rows
    )

    for stock in all_rows:

        symbol = stock["symbol"]

        key = (
            stock["market"]
            + ":"
            + symbol
        )

        history[date_string][key] = {

            "market":
                stock["market"],

            "symbol":
                symbol,

            "name":
                stock["name"],

            "close":
                stock["close"],

            "volume":
                stock["volume"],

            "trading_value":
                stock["trading_value"],

        }

    return history


# ============================================================
# 歷史資料：取得股票序列
# ============================================================

def get_stock_history(
    history,
    market,
    symbol
):

    series = []

    for date_string in sorted(
        history.keys()
    ):

        key = (
            market
            + ":"
            + symbol
        )

        row = history[
            date_string
        ].get(key)

        if not row:
            continue

        close = row.get(
            "close"
        )

        volume = row.get(
            "volume"
        )

        if close is None:
            continue

        series.append({

            "date":
                date_string,

            "close":
                close,

            "volume":
                volume,

        })

    return series


# ============================================================
# 平均值
# ============================================================

def average(values):

    values = [
        x for x in values
        if x is not None
    ]

    if not values:
        return None

    return (
        sum(values)
        / len(values)
    )


# ============================================================
# 技術資料計算
# ============================================================

def calculate_metrics(
    history,
    stock
):

    market = stock[
        "market"
    ]

    symbol = stock[
        "symbol"
    ]

    current_close = stock[
        "close"
    ]

    current_volume = stock[
        "volume"
    ]

    series = get_stock_history(
        history,
        market,
        symbol
    )

    # --------------------------------------------------------
    # 如果歷史資料沒有今天
    # 使用目前 Top 100 的今天資料補進序列
    # --------------------------------------------------------

    if (
        not series
        or series[-1]["date"]
        != stock.get(
            "_date"
        )
    ):

        series.append({

            "date":
                stock.get(
                    "_date"
                ),

            "close":
                current_close,

            "volume":
                current_volume,

        })

    # 日期排序
    series.sort(
        key=lambda x:
            x["date"]
    )

    closes = [
        x["close"]
        for x in series
        if x["close"] is not None
    ]

    volumes = [
        x["volume"]
        for x in series
        if x["volume"] is not None
    ]

    metrics = {}

    # --------------------------------------------------------
    # 今日漲跌幅
    # --------------------------------------------------------

    change = stock.get(
        "change"
    )

    if (
        change is not None
        and current_close is not None
        and current_close != change
    ):

        previous_close = (
            current_close - change
        )

        if previous_close != 0:

            metrics[
                "change_percent"
            ] = round(

                change
                / previous_close
                * 100,

                4

            )

        else:

            metrics[
                "change_percent"
            ] = None

    else:

        metrics[
            "change_percent"
        ] = None

    # --------------------------------------------------------
    # 報酬率
    # --------------------------------------------------------

    periods = {

        "return_5d": 5,

        "return_20d": 20,

        "return_60d": 60,

        "return_120d": 120,

        "return_250d": 250,

    }

    for name, days in periods.items():

        if len(closes) > days:

            old_close = (
                closes[-days - 1]
            )

            if (
                old_close is not None
                and old_close != 0
            ):

                metrics[name] = round(

                    (
                        current_close
                        / old_close
                        - 1
                    )
                    * 100,

                    4

                )

            else:

                metrics[name] = None

        else:

            metrics[name] = None

    # --------------------------------------------------------
    # 移動平均線
    # --------------------------------------------------------

    moving_averages = {

        "ma5": 5,

        "ma20": 20,

        "ma60": 60,

        "ma120": 120,

    }

    for name, days in (
        moving_averages.items()
    ):

        if len(closes) >= days:

            values = closes[-days:]

            metrics[name] = round(

                average(values),

                4

            )

        else:

            metrics[name] = None

    # --------------------------------------------------------
    # 20 日平均成交量
    # --------------------------------------------------------

    if len(volumes) >= 20:

        avg_volume_20d = average(
            volumes[-20:]
        )

        metrics[
            "avg_volume_20d"
        ] = round(
            avg_volume_20d,
            2
        )

        if (
            avg_volume_20d
            and current_volume
            is not None
        ):

            metrics[
                "volume_ratio_20d"
            ] = round(

                current_volume
                / avg_volume_20d,

                4

            )

        else:

            metrics[
                "volume_ratio_20d"
            ] = None

    else:

        metrics[
            "avg_volume_20d"
        ] = None

        metrics[
            "volume_ratio_20d"
        ] = None

    return metrics


# ============================================================
# 建立 Top 100
# ============================================================

def build_top100(
    date_string,
    twse_rows,
    tpex_rows,
    twse_institutional,
    tpex_institutional,
    history
):

    all_stocks = (
        twse_rows
        + tpex_rows
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
    # 成交金額排序
    # --------------------------------------------------------

    all_stocks.sort(

        key=lambda x:
            x["trading_value"]
            or 0,

        reverse=True,

    )

    top100 = all_stocks[
        :TOP_N
    ]

    # --------------------------------------------------------
    # 加入法人 + 技術資料
    # --------------------------------------------------------

    for stock in top100:

        symbol = stock[
            "symbol"
        ]

        market = stock[
            "market"
        ]

        if market == "TWSE":

            institution = (
                twse_institutional
                .get(symbol)
            )

        else:

            institution = (
                tpex_institutional
                .get(symbol)
            )

        if institution is None:

            institution = {

                "foreign_net":
                    None,

                "trust_net":
                    None,

                "dealer_net":
                    None,

                "institutional_net":
                    None,

            }

        stock.update(
            institution
        )

        # 今天日期只供計算使用
        stock["_date"] = date_string

        metrics = calculate_metrics(
            history,
            stock
        )

        stock.update(
            metrics
        )

        # 移除內部欄位
        stock.pop(
            "_date",
            None
        )

    # --------------------------------------------------------
    # 排名
    # --------------------------------------------------------

    for index, stock in enumerate(
        top100,
        start=1
    ):

        stock["rank"] = index

    return top100


# ============================================================
# 儲存歷史
# ============================================================

def save_history(history):

    # --------------------------------------------------------
    # 只保留最近 300 個交易日附近的資料，
    # 避免 GitHub JSON 無限膨脹。
    #
    # 250 日需要約一年資料，
    # 所以保留 300 天。
    # --------------------------------------------------------

    dates = sorted(
        history.keys()
    )

    if len(dates) > 300:

        dates = dates[-300:]

        history = {

            date:
                history[date]

            for date in dates

        }

    with HISTORY_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(

            history,

            file,

            ensure_ascii=False,

            indent=2,

        )


# ============================================================
# 儲存 Top 100
# ============================================================

def save_json(
    date_string,
    stocks
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

        "technical_data": {

            "return_unit":
                "percent",

            "moving_average_unit":
                "price",

            "volume_ratio":
                "today_volume_divided_by_20d_average",

        },

        "stocks":
            stocks,

    }

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(

            output,

            file,

            ensure_ascii=False,

            indent=2,

        )


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

    # --------------------------------------------------------
    # 取得當日資料
    # --------------------------------------------------------

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
    # 讀取歷史
    # --------------------------------------------------------

    history = load_history()

    # --------------------------------------------------------
    # 更新今天的歷史資料
    # --------------------------------------------------------

    history = update_history(

        history,

        date_string,

        twse_rows,

        tpex_rows

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

        history

    )

    if len(top100) < TOP_N:

        print(
            "[WARNING] Top 100 只有 "
            f"{len(top100)} 檔"
        )

    # --------------------------------------------------------
    # 儲存
    # --------------------------------------------------------

    save_history(
        history
    )

    save_json(

        date_string,

        top100

    )

    # --------------------------------------------------------
    # 顯示前 10 名
    # --------------------------------------------------------

    print()
    print(
        "前 10 名："
    )

    for stock in top100[:10]:

        print()

        print(

            f'{stock["rank"]:>3}. '

            f'{stock["symbol"]} '

            f'{stock["name"]:<10} '

            f'{stock["market"]:<5} '

            f'成交金額='

            f'{stock["trading_value"]:,}'

        )

        print(

            f'    漲跌='

            f'{stock["change_percent"]}% '

            f'5日='

            f'{stock["return_5d"]}% '

            f'20日='

            f'{stock["return_20d"]}% '

            f'60日='

            f'{stock["return_60d"]}%'

        )

        print(

            f'    外資='

            f'{stock["foreign_net"]} '

            f'投信='

            f'{stock["trust_net"]} '

            f'自營商='

            f'{stock["dealer_net"]} '

            f'三大法人='

            f'{stock["institutional_net"]}'

        )

    print()

    print(
        "歷史資料檔案：",
        HISTORY_FILE
    )

    print(
        "Top 100 檔案：",
        OUTPUT_FILE
    )

    print()

    print(
        "完成。"
    )


if __name__ == "__main__":

    main()

