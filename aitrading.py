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
#
# 1. TWSE + TPEx 每日行情
# 2. 成交金額 Top 100
# 3. 三大法人
# 4. 歷史價格
# 5. 歷史資料初始化約 300 個交易日
# 6. 自動計算：
#
#       change_percent
#       return_5d
#       return_20d
#       return_60d
#       return_120d
#       return_250d
#       MA5
#       MA20
#       MA60
#       MA120
#       avg_volume_20d
#       volume_ratio_20d
#
#
# ============================================================
# History 儲存格式
# ============================================================
#
# 為了避免 tw_history.json 過大，
# 歷史資料只保存：
#
#       [close, volume]
#
# 例如：
#
# "TWSE:2330": [2420, 15025832]
#
# 不再重複保存：
#
#       market
#       symbol
#       name
#       trading_value
#
# 這些資料只需要存在 tw_top100.json。
#
# ============================================================


TOP_N = 100

HISTORY_DAYS = 300

MAX_HISTORY_DAYS = 320

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
# HTTP Session
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(HEADERS)


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


def is_tradeable_symbol(symbol):

    """
    目前允許：

    股票
    ETF

    原則：

    只要是一般 4 碼數字證券代號，就允許進入候選池。

    """

    symbol = clean_symbol(symbol)

    return (
        len(symbol) == 4
        and symbol.isdigit()
    )


# ============================================================
# 日期
# ============================================================

def get_candidate_dates(days_back=500):

    today = datetime.now()

    dates = []

    for i in range(days_back + 1):

        d = today - timedelta(days=i)

        dates.append({

            "twse":
                d.strftime("%Y%m%d"),

            "tpex":
                d.strftime("%Y/%m/%d"),

            "display":
                d.strftime("%Y-%m-%d"),

        })

    return dates


# ============================================================
# TWSE 每日行情
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

    response = SESSION.get(

        url,

        params=params,

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

        print("[TWSE] 找不到 tables")

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
            "[TWSE] 找不到成交金額資料表"
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

            if not is_tradeable_symbol(symbol):

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

                "market":
                    "TWSE",

                "symbol":
                    symbol,

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
# TPEx 每日行情
# ============================================================

def fetch_tpex(date_string):

    url = (
        "https://www.tpex.org.tw/"
        "www/zh-tw/afterTrading/dailyQuotes"
    )

    params = {

        "response":
            "json",

        "date":
            date_string,

    }

    print(
        f"[TPEx] 取得資料：{date_string}"
    )

    response = SESSION.get(

        url,

        params=params,

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

        return []

    target_table = None

    for table in tables:

        fields = table.get(
            "fields",
            []
        )

        text = "|".join(
            str(x)
            for x in fields
        )

        if (
            "成交金額" in text
            or "成交千元" in text
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
            "[TPEx] 缺少必要欄位"
        )

        return []

    result = []

    for row in rows:

        try:

            symbol = clean_symbol(
                row[symbol_i]
            )

            if not is_tradeable_symbol(symbol):

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

                "market":
                    "TPEX",

                "symbol":
                    symbol,

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
# 找最近交易日
# ============================================================

def fetch_latest_market_data():

    for candidate in get_candidate_dates(10):

        print()

        print(
            "=" * 60
        )

        print(
            "嘗試交易日：",
            candidate["display"]
        )

        print(
            "=" * 60
        )

        try:

            twse = fetch_twse(
                candidate["twse"]
            )

            time.sleep(0.5)

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

        except Exception as exc:

            print(
                "[WARNING]",
                exc
            )

        time.sleep(1)

    raise RuntimeError(
        "找不到最近交易日"
    )


# ============================================================
# 三大法人 - TWSE
# ============================================================

def fetch_twse_institutional(
    date_string
):

    print(
        f"[TWSE] 取得三大法人：{date_string}"
    )

    url = (
        "https://www.twse.com.tw/"
        "rwd/zh/fund/T86"
    )

    params = {

        "response":
            "json",

        "date":
            date_string,

        "selectType":
            "ALLBUT0999",

    }

    response = SESSION.get(

        url,

        params=params,

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

    index = {

        field: i

        for i, field in enumerate(
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

        if field not in index:

            return {}

    result = {}

    for row in rows:

        try:

            symbol = clean_symbol(
                row[
                    index[
                        "證券代號"
                    ]
                ]
            )

            if not is_tradeable_symbol(symbol):

                continue

            result[symbol] = {

                "foreign_net":
                    clean_number(
                        row[
                            index[
                                "外陸資買賣超股數(不含外資自營商)"
                            ]
                        ]
                    ),

                "trust_net":
                    clean_number(
                        row[
                            index[
                                "投信買賣超股數"
                            ]
                        ]
                    ),

                "dealer_net":
                    clean_number(
                        row[
                            index[
                                "自營商買賣超股數"
                            ]
                        ]
                    ),

                "institutional_net":
                    clean_number(
                        row[
                            index[
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
        f"[TWSE] 法人資料：{len(result)} 檔"
    )

    return result


# ============================================================
# 三大法人 - TPEx
# ============================================================

def fetch_tpex_institutional():

    print(
        "[TPEx] 取得三大法人"
    )

    url = (
        "https://www.tpex.org.tw/"
        "openapi/v1/"
        "tpex_3insti_daily_trading"
    )

    response = SESSION.get(

        url,

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

        if not is_tradeable_symbol(symbol):

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
        f"[TPEx] 法人資料：{len(result)} 檔"
    )

    return result


# ============================================================
# History
# ============================================================

def empty_history():

    return {

        "meta": {

            "version": 2,

            "format":
                "compact",

            "description":
                "close_and_volume_only",

            "initialized":
                False,

            "tracked_symbols":
                []

        },

        "dates": {}

    }


# ============================================================
# 舊 History 自動轉換
# ============================================================

def convert_old_history(data):

    """
    把舊版：

    "TWSE:2330": {
        "market": "TWSE",
        "symbol": "2330",
        "name": "台積電",
        "close": 2420,
        "volume": 15025832,
        "trading_value": 36465015980
    }

    轉成：

    "TWSE:2330": [
        2420,
        15025832
    ]

    """

    if not isinstance(data, dict):

        return empty_history()

    # 已經是新版
    if (
        data.get("meta", {})
        .get("version")
        == 2
    ):

        return data

    new_history = empty_history()

    old_dates = data.get(
        "dates",
        data
    )

    if not isinstance(old_dates, dict):

        return new_history

    tracked = set()

    for date_string, day_data in old_dates.items():

        if not isinstance(day_data, dict):

            continue

        new_day = {}

        for key, row in day_data.items():

            # ------------------------------------------------
            # 舊格式
            # ------------------------------------------------

            if isinstance(row, dict):

                close = row.get(
                    "close"
                )

                volume = row.get(
                    "volume"
                )

                if (
                    close is None
                    and volume is None
                ):

                    continue

                new_day[key] = [

                    close,

                    volume

                ]

                tracked.add(key)

            # ------------------------------------------------
            # 已經接近新版
            # ------------------------------------------------

            elif isinstance(row, list):

                if len(row) >= 2:

                    new_day[key] = [

                        row[0],

                        row[1]

                    ]

                    tracked.add(key)

        if new_day:

            new_history[
                "dates"
            ][date_string] = new_day

    new_history[
        "meta"
    ][
        "tracked_symbols"
    ] = sorted(tracked)

    print()

    print(
        "[HISTORY] 已將舊格式轉換為新版壓縮格式"
    )

    return new_history


# ============================================================
# 載入 History
# ============================================================

def load_history():

    if not HISTORY_FILE.exists():

        print(
            "[HISTORY] 找不到 history，建立新檔"
        )

        return empty_history()

    try:

        with HISTORY_FILE.open(
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        history = convert_old_history(
            data
        )

        return history

    except Exception as exc:

        print(
            "[HISTORY WARNING] "
            f"讀取失敗：{exc}"
        )

        print(
            "[HISTORY] 建立新的 history"
        )

        return empty_history()


# ============================================================
# 儲存 History
# ============================================================

def save_history(history):

    dates = history.get(
        "dates",
        {}
    )

    sorted_dates = sorted(
        dates.keys()
    )

    # --------------------------------------------------------
    # 最多保留 320 個交易日
    # --------------------------------------------------------

    if len(sorted_dates) > MAX_HISTORY_DAYS:

        keep_dates = sorted_dates[
            -MAX_HISTORY_DAYS:
        ]

        history["dates"] = {

            d:
                dates[d]

            for d in keep_dates

        }

    # --------------------------------------------------------
    # 更新 meta
    # --------------------------------------------------------

    history[
        "meta"
    ][
        "version"
    ] = 2

    history[
        "meta"
    ][
        "format"
    ] = "compact"

    history[
        "meta"
    ][
        "initialized"
    ] = (

        len(
            history[
                "dates"
            ]
        )
        >= HISTORY_DAYS

    )

    with HISTORY_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(

            history,

            file,

            ensure_ascii=False,

            separators=(",", ":")

        )

    # --------------------------------------------------------
    # 顯示檔案大小
    # --------------------------------------------------------

    try:

        size_mb = (
            HISTORY_FILE.stat().st_size
            / 1024
            / 1024
        )

        print(
            f"[HISTORY] 檔案大小："
            f"{size_mb:.2f} MB"
        )

    except OSError:

        pass


# ============================================================
# 加入一天歷史
# ============================================================

def add_history_day(
    history,
    date_string,
    twse_rows,
    tpex_rows,
    tracked_keys=None
):

    if "dates" not in history:

        history["dates"] = {}

    if date_string not in history["dates"]:

        history["dates"][date_string] = {}

    target = history[
        "dates"
    ][date_string]

    rows = (
        twse_rows
        + tpex_rows
    )

    for stock in rows:

        key = (

            stock["market"]
            + ":"
            + stock["symbol"]

        )

        if (
            tracked_keys is not None
            and key not in tracked_keys
        ):

            continue

        close = stock.get(
            "close"
        )

        volume = stock.get(
            "volume"
        )

        if (
            close is None
            and volume is None
        ):

            continue

        # ----------------------------------------------------
        # 壓縮格式
        # ----------------------------------------------------

        target[key] = [

            close,

            volume

        ]


# ============================================================
# 建立目前 Top 100
# ============================================================

def get_top100(
    twse_rows,
    tpex_rows
):

    all_rows = (
        twse_rows
        + tpex_rows
    )

    unique = {}

    for stock in all_rows:

        key = (

            stock["market"],

            stock["symbol"]

        )

        unique[key] = stock

    stocks = list(
        unique.values()
    )

    stocks.sort(

        key=lambda x:
            x["trading_value"]
            or 0,

        reverse=True

    )

    return stocks[
        :TOP_N
    ]


# ============================================================
# 取得股票歷史序列
# ============================================================

def get_series(
    history,
    market,
    symbol
):

    key = (
        market
        + ":"
        + symbol
    )

    result = []

    for date_string in sorted(
        history["dates"].keys()
    ):

        row = history[
            "dates"
        ][date_string].get(key)

        if not row:

            continue

        # ----------------------------------------------------
        # 新格式：
        #
        # [close, volume]
        # ----------------------------------------------------

        if isinstance(row, list):

            if len(row) < 2:

                continue

            close = row[0]

            volume = row[1]

        # ----------------------------------------------------
        # 保險：如果還有舊格式
        # ----------------------------------------------------

        elif isinstance(row, dict):

            close = row.get(
                "close"
            )

            volume = row.get(
                "volume"
            )

        else:

            continue

        if close is None:

            continue

        result.append({

            "date":
                date_string,

            "close":
                close,

            "volume":
                volume

        })

    return result


# ============================================================
# 平均值
# ============================================================

def average(values):

    values = [

        x

        for x in values

        if x is not None

    ]

    if not values:

        return None

    return sum(values) / len(values)


# ============================================================
# 計算技術資料
# ============================================================

def calculate_metrics(
    history,
    stock,
    date_string
):

    market = stock[
        "market"
    ]

    symbol = stock[
        "symbol"
    ]

    close = stock[
        "close"
    ]

    volume = stock[
        "volume"
    ]

    series = get_series(

        history,

        market,

        symbol

    )

    # --------------------------------------------------------
    # 確保今天資料存在
    # --------------------------------------------------------

    if (
        not series
        or series[-1]["date"]
        != date_string
    ):

        series.append({

            "date":
                date_string,

            "close":
                close,

            "volume":
                volume

        })

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

    # ========================================================
    # 今日漲跌幅
    # ========================================================

    change = stock.get(
        "change"
    )

    if (
        change is not None
        and close is not None
    ):

        previous_close = (
            close - change
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

    # ========================================================
    # 報酬率
    # ========================================================

    periods = {

        "return_5d": 5,

        "return_20d": 20,

        "return_60d": 60,

        "return_120d": 120,

        "return_250d": 250

    }

    for name, days in periods.items():

        if len(closes) > days:

            old_close = closes[
                -days - 1
            ]

            if (
                old_close is not None
                and old_close != 0
            ):

                metrics[name] = round(

                    (
                        close
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

    # ========================================================
    # 移動平均
    # ========================================================

    moving_averages = {

        "ma5": 5,

        "ma20": 20,

        "ma60": 60,

        "ma120": 120

    }

    for name, days in (
        moving_averages.items()
    ):

        if len(closes) >= days:

            values = closes[
                -days:
            ]

            metrics[name] = round(

                average(values),

                4

            )

        else:

            metrics[name] = None

    # ========================================================
    # 20 日平均成交量
    # ========================================================

    if len(volumes) >= 20:

        avg_volume = average(
            volumes[-20:]
        )

        metrics[
            "avg_volume_20d"
        ] = round(

            avg_volume,

            2

        )

        if (
            avg_volume
            and volume is not None
        ):

            metrics[
                "volume_ratio_20d"
            ] = round(

                volume
                / avg_volume,

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
# 歷史初始化
# ============================================================

def bootstrap_history(
    history,
    tracked_keys
):

    existing_dates = sorted(
        history.get(
            "dates",
            {}
        ).keys()
    )

    # --------------------------------------------------------
    # 已經足夠
    # --------------------------------------------------------

    if len(existing_dates) >= HISTORY_DAYS:

        print(
            f"[HISTORY] 已有 "
            f"{len(existing_dates)} 天資料"
        )

        return history

    print()

    print(
        "=" * 60
    )

    print(
        "[HISTORY] 開始初始化歷史資料"
    )

    print(
        f"[HISTORY] 目標：約 "
        f"{HISTORY_DAYS} 個交易日"
    )

    print(
        f"[HISTORY] 目前追蹤標的："
        f"{len(tracked_keys)}"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # 500 個日曆日
    # --------------------------------------------------------

    candidates = get_candidate_dates(
        500
    )

    # 舊 → 新
    candidates.reverse()

    collected = 0

    for candidate in candidates:

        if (
            len(
                history.get(
                    "dates",
                    {}
                )
            )
            >= HISTORY_DAYS
        ):

            break

        date_string = candidate[
            "display"
        ]

        # 已存在
        if date_string in history.get(
            "dates",
            {}
        ):

            continue

        try:

            twse = fetch_twse(
                candidate["twse"]
            )

            time.sleep(0.25)

            tpex = fetch_tpex(
                candidate["tpex"]
            )

            if not twse and not tpex:

                continue

            add_history_day(

                history,

                date_string,

                twse,

                tpex,

                tracked_keys

            )

            if history[
                "dates"
            ].get(date_string):

                collected += 1

                print(

                    f"[HISTORY] "
                    f"{date_string} "
                    f"第 {collected} 個交易日"

                )

        except Exception as exc:

            print(

                f"[HISTORY WARNING] "
                f"{date_string}: {exc}"

            )

        time.sleep(0.25)

    print()

    print(
        "[HISTORY] 初始化完成"
    )

    print(
        "[HISTORY] 日期數：",
        len(
            history.get(
                "dates",
                {}
            )
        )
    )

    return history


# ============================================================
# 建立 Top 100 JSON
# ============================================================

def build_output(
    date_string,
    top100
):

    return {

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

            "TPEx 3insti"

        ],

        "institutional_data": {

            "unit":
                "shares",

            "positive":
                "net_buy",

            "negative":
                "net_sell"

        },

        "technical_data": {

            "return_unit":
                "percent",

            "moving_average_unit":
                "price",

            "volume_ratio":
                "today_volume_divided_by_20d_average"

        },

        "stocks":
            top100

    }


# ============================================================
# 主程式
# ============================================================

def main():

    print()

    print(
        "=" * 60
    )

    print(
        "AI Trading - Taiwan Top 100"
    )

    print(
        "=" * 60
    )

    # ========================================================
    # 取得最近交易日
    # ========================================================

    (
        date_string,

        twse_date,

        tpex_date,

        twse_rows,

        tpex_rows

    ) = fetch_latest_market_data()

    print()

    print(
        f"[MARKET] 交易日："
        f"{date_string}"
    )

    # ========================================================
    # Top 100
    # ========================================================

    current_top100 = get_top100(

        twse_rows,

        tpex_rows

    )

    if len(current_top100) != TOP_N:

        raise RuntimeError(

            f"Top 100 異常："
            f"{len(current_top100)}"

        )

    # ========================================================
    # History
    # ========================================================

    history = load_history()

    if "meta" not in history:

        history["meta"] = {}

    if "tracked_symbols" not in (
        history["meta"]
    ):

        history[
            "meta"
        ][
            "tracked_symbols"
        ] = []

    tracked_keys = set(

        history[
            "meta"
        ][
            "tracked_symbols"
        ]

    )

    # --------------------------------------------------------
    # 新增目前 Top 100
    # --------------------------------------------------------

    for stock in current_top100:

        key = (

            stock["market"]
            + ":"
            + stock["symbol"]

        )

        tracked_keys.add(key)

    history[
        "meta"
    ][
        "tracked_symbols"
    ] = sorted(
        tracked_keys
    )

    # ========================================================
    # 初始化歷史
    # ========================================================

    history = bootstrap_history(

        history,

        tracked_keys

    )

    # ========================================================
    # 加入今天
    # ========================================================

    add_history_day(

        history,

        date_string,

        twse_rows,

        tpex_rows,

        tracked_keys

    )

    # ========================================================
    # 三大法人
    # ========================================================

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

    # ========================================================
    # 最終 Top 100
    # ========================================================

    final_top100 = []

    for stock in current_top100:

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
                    None

            }

        stock.update(
            institution
        )

        # ----------------------------------------------------
        # 技術資料
        # ----------------------------------------------------

        metrics = calculate_metrics(

            history,

            stock,

            date_string

        )

        stock.update(
            metrics
        )

        final_top100.append(
            stock
        )

    # ========================================================
    # 排名
    # ========================================================

    for index, stock in enumerate(

        final_top100,

        start=1

    ):

        stock["rank"] = index

    # ========================================================
    # History initialized 狀態
    # ========================================================

    history[
        "meta"
    ][
        "initialized"
    ] = (

        len(
            history[
                "dates"
            ]
        )
        >= HISTORY_DAYS

    )

    # ========================================================
    # 儲存 History
    # ========================================================

    save_history(
        history
    )

    # ========================================================
    # 儲存 Top 100
    # ========================================================

    output = build_output(

        date_string,

        final_top100

    )

    with OUTPUT_FILE.open(

        "w",

        encoding="utf-8"

    ) as file:

        json.dump(

            output,

            file,

            ensure_ascii=False,

            indent=2

        )

    # ========================================================
    # 顯示結果
    # ========================================================

    print()

    print(
        "=" * 60
    )

    print(
        "前 10 名："
    )

    print(
        "=" * 60
    )

    for stock in final_top100[:10]:

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
            f'{stock.get("change_percent")}% '

            f'5日='
            f'{stock.get("return_5d")}% '

            f'20日='
            f'{stock.get("return_20d")}% '

            f'60日='
            f'{stock.get("return_60d")}% '

            f'120日='
            f'{stock.get("return_120d")}% '

            f'250日='
            f'{stock.get("return_250d")}%'

        )

        print(

            f'    外資='
            f'{stock.get("foreign_net")} '

            f'投信='
            f'{stock.get("trust_net")} '

            f'自營商='
            f'{stock.get("dealer_net")} '

            f'三大法人='
            f'{stock.get("institutional_net")}'

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
