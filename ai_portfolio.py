import json
import os
from datetime import datetime
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import requests


# ============================================================
# 基本設定
# ============================================================

TOP100_FILE = "tw_top100.json"
FUNDAMENTALS_FILE = "tw_fundamentals.json"
PORTFOLIO_FILE = "ai_portfolio.json"

INITIAL_CAPITAL = 1_000_000

# 最多 5 檔
MAX_STOCKS = 5

# 每檔股票最多使用初始資金 20%
MAX_ALLOCATION_PER_STOCK = 0.20

# 第一筆買入 = 該檔目標部位的 30%
FIRST_BUY_ALLOCATION = 0.30


# ============================================================
# JSON
# ============================================================

def load_json(path, default=None):

    if default is None:
        default = {}

    if not Path(path).exists():
        return default

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as e:

        print(f"讀取 {path} 失敗：{e}")

        return default


def save_json(path, data):

    temp_path = f"{path}.tmp"

    with open(
        temp_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    os.replace(
        temp_path,
        path
    )


# ============================================================
# 工具
# ============================================================

def num(value, default=0.0):

    try:

        if value is None or value == "":
            return default

        return float(value)

    except (TypeError, ValueError):

        return default


TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def taipei_now():

    return datetime.now(TAIPEI_TZ)


def today_string():

    return taipei_now().strftime(
        "%Y-%m-%d"
    )


def now_string():

    return taipei_now().isoformat(
        timespec="seconds"
    )


def normalize_quote_date(value):

    """
    TWSE 的 d 欄位通常是 YYYYMMDD，例如 20260831。
    將它統一轉成 YYYY-MM-DD，避免日期比較失敗。
    """
    raw = str(value or "").strip()

    digits = re.sub(r"\\D", "", raw)

    if len(digits) == 8:
        return (
            f"{digits[:4]}-"
            f"{digits[4:6]}-"
            f"{digits[6:]}"
        )

    return raw.replace("/", "-")


# ============================================================
# 建立空白 Portfolio
# ============================================================

def default_portfolio():

    return {

        "version": 1,

        "initial_capital":
            INITIAL_CAPITAL,

        "cash":
            INITIAL_CAPITAL,

        "total_assets":
            INITIAL_CAPITAL,

        "total_profit":
            0,

        "total_return_percent":
            0,

        "date":
            today_string(),

        "updated_at":
            now_string(),

        "signal_queue":
            [],

        "holdings":
            [],

        "waiting":
            [],

        "transactions":
            [],

        "performance":
            []

    }


# ============================================================
# 基本面篩選
# ============================================================

def fundamental_pass(stock):

    if not stock:
        return False

    # 沒有基本面資料
    if stock.get(
        "fundamental_available"
    ) is False:

        return False

    # EPS 必須為正
    if num(
        stock.get("quarter_eps")
    ) <= 0:

        return False

    # TTM 營收必須為正
    if num(
        stock.get("ttm_revenue")
    ) <= 0:

        return False

    # TTM 淨利必須為正
    if num(
        stock.get("ttm_net_income")
    ) <= 0:

        return False

    # ROE 不接受負值
    if num(
        stock.get("roe_ttm")
    ) < 0:

        return False

    return True


# ============================================================
# 技術面分數
# ============================================================

def technical_score(stock):

    score = 0

    close = num(
        stock.get("close")
    )

    ma5 = num(
        stock.get("ma5")
    )

    ma20 = num(
        stock.get("ma20")
    )

    ma60 = num(
        stock.get("ma60")
    )

    volume_ratio = num(
        stock.get("volume_ratio_20d")
    )

    return5 = num(
        stock.get("return_5d")
    )

    return20 = num(
        stock.get("return_20d")
    )

    # 收盤站上 MA20
    if (
        close > 0
        and ma20 > 0
        and close > ma20
    ):

        score += 3

    # MA20 > MA60
    if (
        ma20 > 0
        and ma60 > 0
        and ma20 > ma60
    ):

        score += 3

    # MA5 > MA20
    if (
        ma5 > 0
        and ma20 > 0
        and ma5 > ma20
    ):

        score += 2

    # 5日報酬為正
    if return5 > 0:

        score += 1

    # 20日報酬為正
    if return20 > 0:

        score += 2

    # 成交量放大
    if volume_ratio >= 1.2:

        score += 1

    return score


# ============================================================
# 最終選股
#
# Top100
# ↓
# 基本面
# ↓
# 技術面
# ↓
# 最多 5 檔
# ============================================================

def select_final_stocks():

    top100_data = load_json(
        TOP100_FILE,
        {}
    )

    fundamentals_data = load_json(
        FUNDAMENTALS_FILE,
        {}
    )

    top100 = top100_data.get(
        "stocks",
        []
    )

    fundamentals = fundamentals_data.get(
        "stocks",
        []
    )

    print(
        f"Top 100 資料：{len(top100)} 檔"
    )

    print(
        f"基本面資料：{len(fundamentals)} 檔"
    )

    fundamental_map = {}

    for stock in fundamentals:

        symbol = str(
            stock.get(
                "symbol",
                ""
            )
        ).strip()

        if symbol:

            fundamental_map[
                symbol
            ] = stock

    candidates = []

    for stock in top100:

        symbol = str(
            stock.get(
                "symbol",
                ""
            )
        ).strip()

        if not symbol:
            continue

        fundamental = fundamental_map.get(
            symbol
        )

        if fundamental is None:
            continue

        if not fundamental_pass(
            fundamental
        ):

            continue

        merged = dict(stock)

        merged.update(
            fundamental
        )

        tech_score = technical_score(
            merged
        )

        # 技術面至少 4 分
        if tech_score < 4:
            continue

        merged[
            "_technical_score"
        ] = tech_score

        candidates.append(
            merged
        )

    # 排序
    candidates.sort(

        key=lambda x: (

            num(
                x.get(
                    "_technical_score"
                )
            ),

            num(
                x.get(
                    "roe_ttm"
                )
            ),

            num(
                x.get(
                    "trading_value"
                )
            )

        ),

        reverse=True

    )

    # 最多 5 檔
    final_stocks = candidates[
        :MAX_STOCKS
    ]

    print(
        f"基本面 + 技術面通過："
        f"{len(candidates)} 檔"
    )

    print(
        f"最終 AI 標的："
        f"{len(final_stocks)} 檔"
    )

    for index, stock in enumerate(
        final_stocks,
        start=1
    ):

        print(

            f"#{index} "
            f"{stock.get('symbol')} "
            f"{stock.get('name')} "
            f"技術分數="
            f"{stock.get('_technical_score')}"

        )

    return (
        top100_data,
        final_stocks
    )


# ============================================================
# 加入等待訊號
# ============================================================

def add_new_signals(
    portfolio,
    top100_data,
    final_stocks
):

    signal_date = top100_data.get(
        "date"
    )

    if not signal_date:

        print(
            "找不到 Top100 日期"
        )

        return

    signal_queue = portfolio.setdefault(
        "signal_queue",
        []
    )

    existing = {

        (
            str(
                item.get(
                    "symbol"
                )
            ),

            str(
                item.get(
                    "signal_date"
                )
            )

        )

        for item in signal_queue

    }

    holdings_symbols = {

        str(
            item.get(
                "symbol"
            )
        )

        for item in portfolio.get(
            "holdings",
            []
        )

    }

    for stock in final_stocks:

        symbol = str(
            stock.get(
                "symbol",
                ""
            )
        ).strip()

        if not symbol:
            continue

        key = (
            symbol,
            str(signal_date)
        )

        if key in existing:
            continue

        if symbol in holdings_symbols:
            continue

        reference_close = num(
            stock.get(
                "close"
            )
        )

        if reference_close <= 0:
            continue

        signal_queue.append(

            {

                "signal_date":
                    signal_date,

                "symbol":
                    symbol,

                "name":
                    stock.get(
                        "name",
                        ""
                    ),

                "market":
                    stock.get(
                        "market",
                        ""
                    ),

                "reference_close":
                    reference_close,

                "first_buy_trigger":
                    reference_close,

                "status":
                    "waiting",

                "first_buy_allocation":
                    FIRST_BUY_ALLOCATION,

                "created_at":
                    now_string()

            }

        )

        existing.add(
            key
        )

        print(

            f"新增等待訊號："
            f"{symbol} "
            f"{stock.get('name', '')} "
            f"參考收盤="
            f"{reference_close}"

        )


# ============================================================
# TWSE 即時行情
# ============================================================

def get_twse_quotes(
    symbols
):

    quotes = {}

    if not symbols:
        return quotes

    ex_ch = "|".join(

        f"tse_{symbol}.tw"

        for symbol in symbols

    )

    try:

        response = requests.get(

            "https://mis.twse.com.tw/"
            "stock/api/"
            "getStockInfo.jsp",

            params={

                "ex_ch":
                    ex_ch,

                "json":
                    "1",

                "delay":
                    "0",

                # 避免 GitHub Runner 取得快取中的舊行情
                "_":
                    int(datetime.now().timestamp() * 1000)

            },

            headers={

                "User-Agent":
                    "Mozilla/5.0"

            },

            timeout=20

        )

        response.raise_for_status()

        data = response.json()

        for item in data.get(
            "msgArray",
            []
        ):

            symbol = str(
                item.get(
                    "c",
                    ""
                )
            )

            if not symbol:
                continue

            price = None
            day_low = None

            # ------------------------------------------------
            # 最新成交價
            # ------------------------------------------------

            z = item.get("z")

            if z not in (
                None,
                "",
                "-"
            ):

                try:

                    price = float(z)

                except:

                    price = None

            # ------------------------------------------------
            # 今日最低價
            #
            # TWSE MIS:
            # l = today's low
            #
            # 用來判斷「今天盤中是否曾經觸發」
            # ------------------------------------------------

            low_value = item.get("l")

            if low_value not in (
                None,
                "",
                "-"
            ):

                try:

                    day_low = float(low_value)

                except:

                    day_low = None

            # ------------------------------------------------
            # 注意：
            #
            # 沒有真正成交價時，
            # 不使用昨收。
            #
            # 避免週末把昨收誤判成盤中價格。
            # ------------------------------------------------

            if (
                price is not None
                and price > 0
            ):

                quotes[symbol] = {

                    "price":
                        price,

                    "day_low":
                        day_low,

                    "market":
                        "TWSE",

                    "time":
                        item.get(
                            "t",
                            ""
                        ),

                    "date":
                        item.get(
                            "d",
                            ""
                        )

                }

    except Exception as e:

        print(
            f"TWSE 行情取得失敗：{e}"
        )

    return quotes


# ============================================================
# TPEx
# ============================================================

def get_tpex_quotes(
    symbols
):

    """
    櫃買股票盤中行情。

    TPEx 的免費 OpenAPI tpex_mainboard_quotes 是日行情快照，
    不適合拿來當 GitHub Actions 的盤中觸發器。

    因此櫃買股票改用 Yahoo Finance 的 1 分鐘 chart：
    - regularMarketPrice / close：目前價格
    - day low：今日最低價
    - timestamps：確認資料確實屬於今天

    Yahoo 是公開行情來源，這裡只做模擬交易的行情判斷，
    不執行任何真實下單。
    """

    quotes = {}

    if not symbols:
        return quotes

    for symbol in symbols:

        try:

            url = (
                "https://query1.finance.yahoo.com/"
                f"v8/finance/chart/{symbol}.TWO"
            )

            response = requests.get(

                url,

                params={

                    "range":
                        "1d",

                    "interval":
                        "1m",

                    "includePrePost":
                        "false",

                    "_":
                        int(
                            datetime.now().timestamp()
                            * 1000
                        )

                },

                headers={

                    "User-Agent":
                        "Mozilla/5.0"

                },

                timeout=20

            )

            response.raise_for_status()

            data = response.json()

            result_list = data.get(
                "chart",
                {}
            ).get(
                "result"
            )

            if not result_list:

                print(
                    f"TPEx/Yahoo {symbol} "
                    f"沒有盤中資料。"
                )

                continue

            result = result_list[0]

            meta = result.get(
                "meta",
                {}
            )

            timestamps = result.get(
                "timestamp"
            ) or []

            indicators = result.get(
                "indicators",
                {}
            ).get(
                "quote",
                []
            )

            if not indicators:

                print(
                    f"TPEx/Yahoo {symbol} "
                    f"沒有 quote 資料。"
                )

                continue

            quote_data = indicators[0]

            closes = quote_data.get(
                "close"
            ) or []

            lows = quote_data.get(
                "low"
            ) or []

            # ------------------------------------------------
            # 找最後一筆有效成交價
            # ------------------------------------------------

            current_price = None

            for value in reversed(closes):

                if value is None:
                    continue

                value = num(
                    value,
                    None
                )

                if (
                    value is not None
                    and value > 0
                ):

                    current_price = value
                    break

            if current_price is None:

                current_price = num(
                    meta.get(
                        "regularMarketPrice"
                    ),
                    None
                )

            if (
                current_price is None
                or current_price <= 0
            ):

                print(
                    f"TPEx/Yahoo {symbol} "
                    f"找不到有效現價。"
                )

                continue

            # ------------------------------------------------
            # 今日最低價
            # ------------------------------------------------

            valid_lows = []

            for value in lows:

                if value is None:
                    continue

                value = num(
                    value,
                    None
                )

                if (
                    value is not None
                    and value > 0
                ):

                    valid_lows.append(
                        value
                    )

            day_low = (
                min(valid_lows)
                if valid_lows
                else None
            )

            # Yahoo 的 meta 若有 regularMarketDayLow，
            # 也拿來補強今日最低價。
            meta_day_low = num(
                meta.get(
                    "regularMarketDayLow"
                ),
                None
            )

            if (
                meta_day_low is not None
                and meta_day_low > 0
            ):

                if (
                    day_low is None
                    or meta_day_low < day_low
                ):

                    day_low = meta_day_low

            # ------------------------------------------------
            # 日期
            #
            # range=1d 的 timestamp 是今日交易資料。
            # 若沒有 timestamp，使用台灣當地日期。
            # ------------------------------------------------

            quote_date = today_string()

            if timestamps:

                try:

                    # 不直接依賴 UTC 日期。
                    # Yahoo 的 1d 資料在交易時段代表當日。
                    quote_date = today_string()

                except Exception:

                    quote_date = today_string()

            quotes[symbol] = {

                "price":
                    current_price,

                "day_low":
                    day_low,

                "market":
                    "TPEX",

                "time":
                    "",

                "date":
                    quote_date

            }

            print(
                f"TPEx/Yahoo {symbol}: "
                f"price={current_price}, "
                f"day_low={day_low}"
            )

        except Exception as e:

            print(
                f"TPEx/Yahoo 行情取得失敗 "
                f"{symbol}：{e}"
            )

    return quotes


# ============================================================
# 取得行情
# ============================================================

def get_realtime_quotes(
    stocks
):

    quotes = {}

    twse_symbols = []
    tpex_symbols = []

    for stock in stocks:

        symbol = str(
            stock.get(
                "symbol",
                ""
            )
        )

        market = str(
            stock.get(
                "market",
                ""
            )
        ).upper()

        if not symbol:
            continue

        if market == "TWSE":

            twse_symbols.append(
                symbol
            )

        elif market in (
            "TPEX",
            "TPEx"
        ):

            tpex_symbols.append(
                symbol
            )

    quotes.update(
        get_twse_quotes(
            twse_symbols
        )
    )

    quotes.update(
        get_tpex_quotes(
            tpex_symbols
        )
    )

    return quotes


# ============================================================
# 是否允許今天進行交易
# ============================================================

def is_trading_day(date_string=None):

    if date_string:
        try:
            check_date = datetime.strptime(
                str(date_string),
                "%Y-%m-%d"
            ).date()
        except ValueError:
            return False
    else:
        check_date = taipei_now().date()

    # 5 = Saturday
    # 6 = Sunday
    return check_date.weekday() < 5


# ============================================================
# 歷史日行情
# ============================================================

def get_historical_daily_quotes(
    signals,
    end_date
):

    """
    取得等待訊號在「今天以前」的歷史日內最低價。

    用途：
    GitHub Actions 如果沒有剛好在觸價當下執行，
    下一次執行時仍可回頭檢查先前交易日是否曾經觸發。

    Yahoo Finance chart API 的日線 low 只用來判斷：
        當日最低價 <= 參考收盤價

    成交價仍固定使用 reference_close，
    不假裝知道盤中最低點就是成交價。
    """

    history = {}

    if not signals:
        return history

    today = str(end_date)

    for signal in signals:

        symbol = str(
            signal.get("symbol", "")
        ).strip()

        signal_date = str(
            signal.get("signal_date", "")
        ).strip()

        if not symbol or not signal_date:
            continue

        try:
            start_dt = datetime.strptime(
                signal_date,
                "%Y-%m-%d"
            )
            end_dt = datetime.strptime(
                today,
                "%Y-%m-%d"
            )
        except ValueError:
            continue

        # 選股日之後、今天之前才是可回補的歷史交易區間。
        if end_dt.date() <= start_dt.date():
            continue

        # Yahoo symbol：
        # TWSE -> .TW
        # TPEx -> .TWO
        market = str(
            signal.get("market", "")
        ).upper()

        suffix = ".TWO" if market in (
            "TPEX",
            "TPEX",
            "TPEX ",
            "TPEX"
        ) else ".TW"

        yahoo_symbol = f"{symbol}{suffix}"

        try:
            # period1 / period2 使用 UTC epoch。
            # 查詢範圍包含 signal_date 後一天到今天，
            # period2 設成今天台灣時間 00:00 後一天，
            # 以確保最後一個完整交易日被包含。
            query_start = start_dt.date()
            query_end = end_dt.date()

            start_local = datetime(
                query_start.year,
                query_start.month,
                query_start.day,
                tzinfo=TAIPEI_TZ
            )

            end_local = datetime(
                query_end.year,
                query_end.month,
                query_end.day,
                tzinfo=TAIPEI_TZ
            )

            period1 = int(
                start_local.timestamp()
            )

            period2 = int(
                (end_local.timestamp() + 86400)
            )

            response = requests.get(
                "https://query1.finance.yahoo.com/"
                f"/v8/finance/chart/{yahoo_symbol}",
                params={
                    "period1": period1,
                    "period2": period2,
                    "interval": "1d",
                    "includePrePost": "false",
                    "events": "div,splits",
                    "_": int(
                        taipei_now().timestamp() * 1000
                    )
                },
                headers={
                    "User-Agent": "Mozilla/5.0"
                },
                timeout=20
            )

            response.raise_for_status()
            data = response.json()

            result_list = data.get(
                "chart",
                {}
            ).get(
                "result"
            )

            if not result_list:
                print(
                    f"歷史行情 {symbol}：沒有資料。"
                )
                continue

            result = result_list[0]

            timestamps = result.get(
                "timestamp"
            ) or []

            quote_list = result.get(
                "indicators",
                {}
            ).get(
                "quote",
                []
            )

            if not quote_list:
                print(
                    f"歷史行情 {symbol}：沒有 quote。"
                )
                continue

            quote_data = quote_list[0]

            lows = quote_data.get(
                "low"
            ) or []

            rows = []

            for i, timestamp in enumerate(
                timestamps
            ):

                if i >= len(lows):
                    continue

                low = lows[i]

                if low is None:
                    continue

                low = num(
                    low,
                    None
                )

                if low is None or low <= 0:
                    continue

                try:
                    row_date = datetime.fromtimestamp(
                        int(timestamp),
                        tz=TAIPEI_TZ
                    ).strftime("%Y-%m-%d")
                except Exception:
                    continue

                # 絕對不能把選股日當成可交易日。
                if row_date <= signal_date:
                    continue

                # 只回補今天以前的完整交易日。
                if row_date >= today:
                    continue

                rows.append({
                    "date": row_date,
                    "day_low": low
                })

            rows.sort(
                key=lambda x: x["date"]
            )

            history[symbol] = rows

            print(
                f"歷史行情 {symbol}: "
                f"取得 {len(rows)} 個交易日"
            )

        except Exception as e:

            print(
                f"歷史行情取得失敗 {symbol}：{e}"
            )

    return history


# ============================================================
# 第一次買入
# ============================================================

def process_first_buy(
    portfolio,
    realtime_quotes,
    historical_quotes=None
):

    """
    處理第一筆買入。

    規則：
    1. AI 選股日不能買。
    2. 選股日之後，只要某個交易日曾經觸及 reference_close，
       就在「第一次觸發的交易日」模擬成交。
    3. 如果是今天，使用即時行情的 price / day_low。
    4. 如果是過去交易日，使用歷史日線 low 回補漏掉的觸價。
    5. 回補歷史交易時，成交價使用 reference_close。
    """

    today = today_string()

    historical_quotes = historical_quotes or {}

    # 週末不做今天的即時買入；
    # 但即使今天是週末，也不需要在這裡回補，
    # 因為歷史回補由今天以前的交易日處理。
    today_is_trading = is_trading_day(today)

    for signal in portfolio.get(
        "signal_queue",
        []
    ):

        if signal.get(
            "status"
        ) != "waiting":
            continue

        signal_date = str(
            signal.get("signal_date", "")
        ).strip()

        if not signal_date:
            continue

        # ----------------------------------------------------
        # 選股當天不能買
        # ----------------------------------------------------

        if signal_date >= today:
            continue

        symbol = str(
            signal.get(
                "symbol",
                ""
            )
        ).strip()

        if not symbol:
            continue

        reference_close = num(
            signal.get(
                "reference_close"
            )
        )

        if reference_close <= 0:
            continue

        triggered = False
        execution_price = None
        trigger_date = None
        trigger_reason = ""

        # ====================================================
        # A. 先檢查「今天以前」是否有漏掉的觸價日
        # ====================================================

        rows = historical_quotes.get(
            symbol,
            []
        )

        for row in rows:

            row_date = str(
                row.get("date", "")
            )

            day_low = num(
                row.get("day_low"),
                None
            )

            if not row_date:
                continue

            if row_date <= signal_date:
                continue

            if row_date >= today:
                continue

            if not is_trading_day(row_date):
                continue

            if (
                day_low is not None
                and day_low > 0
                and day_low <= reference_close
            ):

                triggered = True
                execution_price = reference_close
                trigger_date = row_date
                trigger_reason = (
                    f"{row_date} 歷史最低價 {day_low} "
                    f"≤ 觸發價格 {reference_close}；"
                    f"回補為觸發價限價單成交"
                )

                break

        # ====================================================
        # B. 如果今天是交易日，再檢查今天即時行情
        # ====================================================

        if not triggered and today_is_trading:

            quote = realtime_quotes.get(
                symbol
            )

            if quote is None:

                print(
                    f"{symbol} "
                    f"{signal.get('name', '')} "
                    f"找不到即時行情，"
                    f"跳過本次檢查。"
                )

            else:

                quote_date = str(
                    quote.get(
                        "date",
                        ""
                    )
                )

                # Yahoo TPEx 已經是 YYYY-MM-DD；
                # TWSE 則可能是 YYYYMMDD。
                if quote_date:

                    normalized_quote_date = normalize_quote_date(
                        quote_date
                    )

                    if normalized_quote_date != today:

                        print(
                            f"{symbol} "
                            f"行情日期 {quote_date} "
                            f"(標準化後 {normalized_quote_date}) "
                            f"不是今天 {today}，不買。"
                        )

                        quote = None

                if quote is not None:

                    current_price = num(
                        quote.get("price")
                    )

                    day_low = num(
                        quote.get("day_low"),
                        None
                    )

                    print(
                        f"檢查 {symbol} "
                        f"{signal.get('name', '')}: "
                        f"現價={current_price} "
                        f"今日最低={day_low} "
                        f"觸發價={reference_close}"
                    )

                    if current_price > 0 and current_price <= reference_close:

                        triggered = True
                        execution_price = current_price
                        trigger_date = today
                        trigger_reason = (
                            "即時價格 ≤ 觸發價格"
                        )

                    elif (
                        day_low is not None
                        and day_low > 0
                        and day_low <= reference_close
                    ):

                        triggered = True
                        execution_price = reference_close
                        trigger_date = today
                        trigger_reason = (
                            "今日最低價曾 ≤ 觸發價格；"
                            "以觸發價限價單模擬成交"
                        )

        if not triggered:

            print(
                f"{symbol} 尚未觸發："
                f"選股日={signal_date}, "
                f"觸發價={reference_close}"
            )

            continue

        print(
            f"★ {symbol} 已觸發："
            f"{trigger_reason}，"
            f"模擬成交日={trigger_date}，"
            f"成交價={execution_price}"
        )

        # ----------------------------------------------------
        # 每檔目標部位 = 初始資金 20%
        # ----------------------------------------------------

        target_budget = (
            INITIAL_CAPITAL
            * MAX_ALLOCATION_PER_STOCK
        )

        # ----------------------------------------------------
        # 第一筆 = 目標部位 30%
        # ----------------------------------------------------

        buy_budget = (
            target_budget
            * FIRST_BUY_ALLOCATION
        )

        cash = num(
            portfolio.get(
                "cash"
            )
        )

        if cash <= 0:

            print(
                "現金不足"
            )

            continue

        buy_budget = min(
            buy_budget,
            cash
        )

        quantity = int(
            buy_budget
            // execution_price
        )

        if quantity <= 0:

            print(
                f"{symbol} 資金不足以買入 1 股"
            )

            continue

        actual_amount = (
            quantity
            * execution_price
        )

        # ----------------------------------------------------
        # 扣現金
        # ----------------------------------------------------

        portfolio["cash"] = (
            cash
            - actual_amount
        )

        # ----------------------------------------------------
        # 建立持股
        # ----------------------------------------------------

        # 歷史回補時，若今天有即時價格就使用今天價格；
        # 否則先以成交價建立，之後下一次行情更新會修正。
        current_price = execution_price

        current_quote = realtime_quotes.get(
            symbol
        )

        if current_quote:
            current_price = num(
                current_quote.get("price"),
                execution_price
            )

            if current_price <= 0:
                current_price = execution_price

        portfolio.setdefault(
            "holdings",
            []
        ).append(
            {
                "symbol": symbol,
                "name": signal.get(
                    "name",
                    ""
                ),
                "market": signal.get(
                    "market",
                    ""
                ),
                "quantity": quantity,
                "average_cost": execution_price,
                "current_price": current_price,
                "invested": actual_amount,
                "market_value": quantity * current_price,
                "unrealized_profit": (
                    quantity * current_price
                    - actual_amount
                ),
                "unrealized_return_percent": (
                    (
                        (quantity * current_price)
                        - actual_amount
                    )
                    / actual_amount
                    * 100
                    if actual_amount > 0
                    else 0
                ),
                "first_buy_date": trigger_date,
                "signal_date": signal_date,
                "reference_close": reference_close,
                "buy_stage": 1,
                "allocation_used": FIRST_BUY_ALLOCATION
            }
        )

        # ----------------------------------------------------
        # 更新訊號
        # ----------------------------------------------------

        signal["status"] = "holding"
        signal["first_buy_date"] = trigger_date
        signal["first_buy_price"] = execution_price

        # ----------------------------------------------------
        # 交易紀錄
        # ----------------------------------------------------

        portfolio.setdefault(
            "transactions",
            []
        ).append(
            {
                "date": trigger_date,
                "symbol": symbol,
                "name": signal.get(
                    "name",
                    ""
                ),
                "action": "買入",
                "price": execution_price,
                "quantity": quantity,
                "amount": actual_amount,
                "allocation": "30%",
                "reason": trigger_reason,
                "signal_date": signal_date,
                "reference_close": reference_close
            }
        )

        print(
            f"★ 第一筆買入："
            f"{symbol} "
            f"{quantity} 股 @ "
            f"{execution_price} "
            f"成交日={trigger_date}"
        )


# ============================================================
# 更新持股價格
# ============================================================

def update_holdings(
    portfolio,
    realtime_quotes
):

    for holding in portfolio.get(
        "holdings",
        []
    ):

        symbol = str(
            holding.get(
                "symbol",
                ""
            )
        )

        quote = realtime_quotes.get(
            symbol
        )

        if quote is None:
            continue

        current_price = num(
            quote.get(
                "price"
            )
        )

        if current_price <= 0:
            continue

        quantity = num(
            holding.get(
                "quantity"
            )
        )

        average_cost = num(
            holding.get(
                "average_cost"
            )
        )

        market_value = (

            quantity
            * current_price

        )

        invested = (

            quantity
            * average_cost

        )

        profit = (

            market_value
            - invested

        )

        return_percent = 0

        if invested > 0:

            return_percent = (

                profit
                / invested
                * 100

            )

        holding[
            "current_price"
        ] = current_price

        holding[
            "market_value"
        ] = market_value

        holding[
            "invested"
        ] = invested

        holding[
            "unrealized_profit"
        ] = profit

        holding[
            "unrealized_return_percent"
        ] = return_percent


# ============================================================
# 更新等待名單
# ============================================================

def update_waiting(
    portfolio
):

    waiting = []

    holdings_symbols = {

        str(
            item.get(
                "symbol"
            )
        )

        for item in portfolio.get(
            "holdings",
            []
        )

    }

    for signal in portfolio.get(
        "signal_queue",
        []
    ):

        if signal.get(
            "status"
        ) != "waiting":

            continue

        symbol = str(
            signal.get(
                "symbol",
                ""
            )
        )

        if symbol in holdings_symbols:

            continue

        waiting.append(

            {

                "symbol":
                    symbol,

                "name":
                    signal.get(
                        "name",
                        ""
                    ),

                "signal_date":
                    signal.get(
                        "signal_date"
                    ),

                "trigger_price":
                    signal.get(
                        "reference_close"
                    ),

                "status":
                    "等待價格 ≤ 選股日收盤"

            }

        )

    portfolio["waiting"] = waiting


# ============================================================
# 總資產
# ============================================================

def update_total_assets(
    portfolio
):

    cash = num(
        portfolio.get(
            "cash"
        )
    )

    market_value = sum(

        num(
            holding.get(
                "market_value"
            )
        )

        for holding
        in portfolio.get(
            "holdings",
            []
        )

    )

    total_assets = (
        cash
        + market_value
    )

    initial_capital = num(
        portfolio.get(
            "initial_capital",
            INITIAL_CAPITAL
        )
    )

    total_profit = (
        total_assets
        - initial_capital
    )

    total_return = 0

    if initial_capital > 0:

        total_return = (

            total_profit
            / initial_capital
            * 100

        )

    portfolio[
        "total_assets"
    ] = total_assets

    portfolio[
        "total_profit"
    ] = total_profit

    portfolio[
        "total_return_percent"
    ] = total_return


# ============================================================
# 每日績效
# ============================================================

def update_daily_performance(
    portfolio
):

    today = today_string()

    total_assets = num(
        portfolio.get(
            "total_assets"
        )
    )

    initial_capital = num(
        portfolio.get(
            "initial_capital",
            INITIAL_CAPITAL
        )
    )

    return_percent = 0

    if initial_capital > 0:

        return_percent = (

            total_assets
            - initial_capital

        ) / initial_capital * 100

    performance = portfolio.setdefault(
        "performance",
        []
    )

    row = {

        "date":
            today,

        "total_assets":
            total_assets,

        "cash":
            portfolio.get(
                "cash",
                0
            ),

        "return_percent":
            return_percent,

        "holding_count":
            len(
                portfolio.get(
                    "holdings",
                    []
                )
            )

    }

    existing = None

    for item in performance:

        if item.get(
            "date"
        ) == today:

            existing = item

            break

    if existing is None:

        performance.append(
            row
        )

    else:

        existing.update(
            row
        )

    performance.sort(

        key=lambda x:
            str(
                x.get(
                    "date",
                    ""
                )
            )

    )


# ============================================================
# 主程式
# ============================================================

def main():

    print()
    print("=" * 65)
    print(
        "ChatGPT AI Trading Portfolio"
    )
    print(
        now_string()
    )
    print("=" * 65)
    print()

    # --------------------------------------------------------
    # 1. Portfolio
    # --------------------------------------------------------

    portfolio = load_json(
        PORTFOLIO_FILE,
        default_portfolio()
    )

    defaults = default_portfolio()

    for key, value in defaults.items():

        if key not in portfolio:

            portfolio[key] = value

    # --------------------------------------------------------
    # 2. AI 最終 0～5 檔
    # --------------------------------------------------------

    (
        top100_data,
        final_stocks
    ) = select_final_stocks()

    # --------------------------------------------------------
    # 3. 建立等待訊號
    # --------------------------------------------------------

    add_new_signals(

        portfolio,

        top100_data,

        final_stocks

    )

    # --------------------------------------------------------
    # 4. 建立監控清單
    # --------------------------------------------------------

    monitor = {}

    for signal in portfolio.get(
        "signal_queue",
        []
    ):

        if signal.get(
            "status"
        ) == "waiting":

            symbol = str(
                signal.get(
                    "symbol",
                    ""
                )
            )

            monitor[symbol] = {

                "symbol":
                    symbol,

                "market":
                    signal.get(
                        "market",
                        ""
                    )

            }

    for holding in portfolio.get(
        "holdings",
        []
    ):

        symbol = str(
            holding.get(
                "symbol",
                ""
            )
        )

        monitor[symbol] = {

            "symbol":
                symbol,

            "market":
                holding.get(
                    "market",
                    ""
                )

        }

    monitor_stocks = list(
        monitor.values()
    )

    print()

    print(
        "目前監控：",
        [
            item["symbol"]
            for item in monitor_stocks
        ]
    )

    # --------------------------------------------------------
    # 5. 只有交易日才取得行情
    # --------------------------------------------------------

    quotes = {}

    if is_trading_day():

        quotes = get_realtime_quotes(
            monitor_stocks
        )

        print(
            f"取得行情：{len(quotes)} 檔"
        )

        for symbol, quote in quotes.items():

            print(
                f"行情 {symbol}: "
                f"price={quote.get('price')} "
                f"day_low={quote.get('day_low')} "
                f"date={quote.get('date')} "
                f"time={quote.get('time')}"
            )

    else:

        print(
            "今天為週末，"
            "不取得行情、不買入。"
        )

    # --------------------------------------------------------
    # 6. 回補過去交易日的觸價
    # --------------------------------------------------------

    waiting_signals = [
        signal
        for signal in portfolio.get(
            "signal_queue",
            []
        )
        if signal.get("status") == "waiting"
        and str(signal.get("signal_date", "")) < today_string()
    ]

    historical_quotes = get_historical_daily_quotes(
        waiting_signals,
        today_string()
    )

    # --------------------------------------------------------
    # 7. 第一次買入
    # --------------------------------------------------------

    process_first_buy(

        portfolio,

        quotes,

        historical_quotes

    )

    # --------------------------------------------------------
    # 8. 更新持股
    # --------------------------------------------------------

    update_holdings(

        portfolio,

        quotes

    )

    # --------------------------------------------------------
    # 9. 更新等待名單
    # --------------------------------------------------------

    update_waiting(
        portfolio
    )

    # --------------------------------------------------------
    # 10. 更新總資產
    # --------------------------------------------------------

    update_total_assets(
        portfolio
    )

    # --------------------------------------------------------
    # 11. 更新每日績效
    # --------------------------------------------------------

    update_daily_performance(
        portfolio
    )

    # --------------------------------------------------------
    # 12. 更新時間
    # --------------------------------------------------------

    portfolio[
        "date"
    ] = today_string()

    portfolio[
        "updated_at"
    ] = now_string()

    # --------------------------------------------------------
    # 13. 儲存
    # --------------------------------------------------------

    save_json(

        PORTFOLIO_FILE,

        portfolio

    )

    # --------------------------------------------------------
    # 14. 顯示
    # --------------------------------------------------------

    print()
    print("=" * 65)

    print(
        "現金：",
        round(
            num(
                portfolio.get(
                    "cash"
                )
            ),
            2
        )
    )

    print(
        "總資產：",
        round(
            num(
                portfolio.get(
                    "total_assets"
                )
            ),
            2
        )
    )

    print(
        "累積損益：",
        round(
            num(
                portfolio.get(
                    "total_profit"
                )
            ),
            2
        )
    )

    print(
        "累積報酬率：",
        round(
            num(
                portfolio.get(
                    "total_return_percent"
                )
            ),
            4
        ),
        "%"
    )

    print(
        "目前持股：",
        len(
            portfolio.get(
                "holdings",
                []
            )
        )
    )

    print(
        "等待進場：",
        len(
            portfolio.get(
                "waiting",
                []
            )
        )
    )

    print(
        "歷史交易：",
        len(
            portfolio.get(
                "transactions",
                []
            )
        )
    )

    print("=" * 65)

    print(
        f"已更新 {PORTFOLIO_FILE}"
    )


# ============================================================
# 執行
# ============================================================

if __name__ == "__main__":

    main()
