import json
import os
import requests
from datetime import datetime, date, timedelta
from pathlib import Path


# ============================================================
# 基本設定
# ============================================================

TOP100_FILE = "tw_top100.json"
PORTFOLIO_FILE = "ai_portfolio.json"

INITIAL_CAPITAL = 1_000_000

# 第一筆買入配置
FIRST_BUY_ALLOCATION = 0.30

# 每檔最多持有的資金比例
# 目前最多 5 檔，因此每檔最高 20%
MAX_ALLOCATION_PER_STOCK = 0.20


# ============================================================
# TWSE / TPEx 即時行情
# ============================================================

def get_realtime_quotes(symbols):

    quotes = {}

    tse_symbols = []
    otc_symbols = []

    for stock in symbols:

        symbol = str(stock.get("symbol", "")).strip()
        market = str(stock.get("market", "")).upper()

        if not symbol:
            continue

        if market == "TWSE":
            tse_symbols.append(symbol)

        elif market == "TPEX":
            otc_symbols.append(symbol)

    # --------------------------------------------------------
    # TWSE
    # --------------------------------------------------------

    if tse_symbols:

        ex_ch = "|".join(
            f"tse_{symbol}.tw"
            for symbol in tse_symbols
        )

        url = (
            "https://mis.twse.com.tw/stock/api/"
            "getStockInfo.jsp"
        )

        try:

            response = requests.get(
                url,
                params={
                    "ex_ch": ex_ch,
                    "json": "1",
                    "delay": "0"
                },
                timeout=20,
                headers={
                    "User-Agent":
                        "Mozilla/5.0"
                }
            )

            response.raise_for_status()

            data = response.json()

            for item in data.get("msgArray", []):

                symbol = str(
                    item.get("c", "")
                )

                if not symbol:
                    continue

                price = parse_realtime_price(item)

                if price is not None:

                    quotes[symbol] = {
                        "price": price,
                        "market": "TWSE",
                        "time": item.get("t", "")
                    }

        except Exception as e:

            print(
                "TWSE realtime error:",
                e
            )


    # --------------------------------------------------------
    # TPEx
    # --------------------------------------------------------

    if otc_symbols:

        for symbol in otc_symbols:

            try:

                url = (
                    "https://www.tpex.org.tw/"
                    "openapi/v1.1/tpex_mainboard_quotes"
                )

                response = requests.get(
                    url,
                    timeout=20,
                    headers={
                        "User-Agent":
                            "Mozilla/5.0"
                    }
                )

                response.raise_for_status()

                data = response.json()

                for item in data:

                    code = str(
                        item.get("SecuritiesCompanyCode", "")
                    )

                    if code != symbol:
                        continue

                    price = (
                        item.get("Close")
                        or item.get("ClosingPrice")
                    )

                    try:
                        price = float(price)
                    except:
                        price = None

                    if price is not None:

                        quotes[symbol] = {
                            "price": price,
                            "market": "TPEX",
                            "time": ""
                        }

                    break

            except Exception as e:

                print(
                    f"TPEx realtime error {symbol}:",
                    e
                )

    return quotes


# ============================================================
# TWSE 即時價格解析
# ============================================================

def parse_realtime_price(item):

    # z = 最新成交價
    z = item.get("z")

    if z not in (None, "", "-"):
        try:
            return float(z)
        except:
            pass

    # 若沒有最新成交價
    # 使用最佳賣價 / 買價作為保守 fallback
    for key in ["a", "b"]:

        value = item.get(key)

        if not value:
            continue

        try:

            first_price = value.split("_")[0]

            if first_price not in ("", "-"):
                return float(first_price)

        except:
            pass

    return None


# ============================================================
# JSON
# ============================================================

def load_json(path, default):

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

        print(
            f"讀取 {path} 失敗:",
            e
        )

        return default


def save_json(path, data):

    temp_path = str(path) + ".tmp"

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
# 日期
# ============================================================

def today_string():

    return datetime.now().strftime(
        "%Y-%m-%d"
    )


# ============================================================
# 初始化 Portfolio
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

        "total_return_percent":
            0,

        "date":
            today_string(),

        "updated_at":
            datetime.now().isoformat(
                timespec="seconds"
            ),

        "signal_queue": [],

        "holdings": [],

        "waiting": [],

        "transactions": [],

        "performance": []

    }


# ============================================================
# 建立 / 更新 AI 選股訊號
# ============================================================

def update_signals(portfolio):

    top100_data =
        load_json(
            TOP100_FILE,
            {}
        )

    stocks = top100_data.get(
        "stocks",
        []
    )

    signal_date = top100_data.get(
        "date"
    )

    if not signal_date:
        print(
            "tw_top100.json 沒有 date"
        )
        return


    # --------------------------------------------------------
    # 只接受最多前 5 檔
    # --------------------------------------------------------

    selected = stocks[:5]


    existing_symbols = {
        str(x.get("symbol"))
        for x in portfolio.get(
            "signal_queue",
            []
        )
    }


    holdings_symbols = {
        str(x.get("symbol"))
        for x in portfolio.get(
            "holdings",
            []
        )
    }


    for stock in selected:

        symbol = str(
            stock.get("symbol", "")
        )

        if not symbol:
            continue

        if symbol in existing_symbols:
            continue

        if symbol in holdings_symbols:
            continue


        close = stock.get("close")

        try:
            close = float(close)
        except:
            continue


        signal = {

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

            # ★ 鎖定 AI 選股當日收盤價
            "reference_close":
                close,

            "status":
                "waiting",

            "first_buy_trigger":
                close,

            "first_buy_allocation":
                FIRST_BUY_ALLOCATION,

            "created_at":
                datetime.now().isoformat(
                    timespec="seconds"
                )

        }


        portfolio.setdefault(
            "signal_queue",
            []
        ).append(signal)


        existing_symbols.add(symbol)


        print(
            f"新增 AI 訊號: "
            f"{symbol} "
            f"{stock.get('name')} "
            f"@ {close}"
        )


# ============================================================
# 將等待訊號整理成 waiting
# ============================================================

def refresh_waiting(portfolio):

    waiting = []

    holdings_symbols = {
        str(x.get("symbol"))
        for x in portfolio.get(
            "holdings",
            []
        )
    }


    for signal in portfolio.get(
        "signal_queue",
        []
    ):

        if signal.get("status") != "waiting":
            continue

        symbol = str(
            signal.get("symbol")
        )

        if symbol in holdings_symbols:
            continue

        waiting.append({

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
                    "first_buy_trigger"
                ),

            "status":
                "等待價格 ≤ 前一交易日收盤"

        })


    portfolio["waiting"] = waiting


# ============================================================
# 執行第一次買入
# ============================================================

def process_first_buy(
    portfolio,
    realtime_quotes
):

    today = today_string()

    for signal in portfolio.get(
        "signal_queue",
        []
    ):

        if signal.get("status") != "waiting":
            continue


        symbol = str(
            signal.get("symbol")
        )


        quote =
            realtime_quotes.get(
                symbol
            )


        if not quote:
            continue


        current_price =
            quote.get("price")


        if current_price is None:
            continue


        trigger_price =
            float(
                signal.get(
                    "first_buy_trigger"
                )
            )


        # ====================================================
        # ★ 核心規則
        #
        # 盤中價格 <= AI 選股日收盤價
        # → 第一筆買入 30%
        # ====================================================

        if current_price > trigger_price:

            continue


        # ----------------------------------------------------
        # 每檔目標資金
        # ----------------------------------------------------

        stock_budget =
            INITIAL_CAPITAL * \
            MAX_ALLOCATION_PER_STOCK


        buy_amount =
            stock_budget * \
            FIRST_BUY_ALLOCATION


        # ----------------------------------------------------
        # 現金不足
        # ----------------------------------------------------

        cash =
            float(
                portfolio.get(
                    "cash",
                    0
                )
            )


        if cash <= 0:
            print(
                "現金不足，無法買入"
            )
            continue


        buy_amount =
            min(
                buy_amount,
                cash
            )


        quantity =
            int(
                buy_amount //
                current_price
            )


        if quantity <= 0:

            print(
                f"{symbol} 價格過高，"
                f"剩餘資金不足 1 股"
            )

            continue


        actual_amount =
            quantity * current_price


        # ----------------------------------------------------
        # 扣除現金
        # ----------------------------------------------------

        portfolio["cash"] =
            cash - actual_amount


        # ----------------------------------------------------
        # 建立持股
        # ----------------------------------------------------

        holding = {

            "symbol":
                symbol,

            "name":
                signal.get(
                    "name",
                    ""
                ),

            "market":
                signal.get(
                    "market",
                    ""
                ),

            "quantity":
                quantity,

            "average_cost":
                current_price,

            "current_price":
                current_price,

            "invested":
                actual_amount,

            "market_value":
                actual_amount,

            "unrealized_profit":
                0,

            "unrealized_return_percent":
                0,

            "first_buy_date":
                today,

            "signal_date":
                signal.get(
                    "signal_date"
                ),

            "reference_close":
                trigger_price,

            "buy_stage":
                1,

            "allocation_used":
                FIRST_BUY_ALLOCATION

        }


        portfolio.setdefault(
            "holdings",
            []
        ).append(
            holding
        )


        # ----------------------------------------------------
        # 更新訊號狀態
        # ----------------------------------------------------

        signal["status"] =
            "holding"

        signal["first_buy_date"] =
            today

        signal["first_buy_price"] =
            current_price


        # ----------------------------------------------------
        # 交易紀錄
        # ----------------------------------------------------

        portfolio.setdefault(
            "transactions",
            []
        ).append({

            "date":
                today,

            "symbol":
                symbol,

            "name":
                signal.get(
                    "name",
                    ""
                ),

            "action":
                "買入",

            "price":
                current_price,

            "quantity":
                quantity,

            "amount":
                actual_amount,

            "allocation":
                "30%",

            "reason":
                "盤中價格 ≤ AI 選股日前一交易日收盤價",

            "signal_date":
                signal.get(
                    "signal_date"
                ),

            "reference_close":
                trigger_price

        })


        print(
            f"★ 觸發買入 "
            f"{symbol} "
            f"{quantity} 股 "
            f"@ {current_price}"
        )


# ============================================================
# 更新持股市值
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
            holding.get("symbol")
        )


        quote =
            realtime_quotes.get(
                symbol
            )


        if not quote:
            continue


        current_price =
            quote.get("price")


        if current_price is None:
            continue


        quantity =
            float(
                holding.get(
                    "quantity",
                    0
                )
            )


        average_cost =
            float(
                holding.get(
                    "average_cost",
                    0
                )
            )


        market_value =
            quantity * current_price


        invested =
            quantity * average_cost


        profit =
            market_value - invested


        return_percent = 0

        if invested > 0:

            return_percent =
                profit /
                invested *
                100


        holding["current_price"] =
            current_price

        holding["market_value"] =
            market_value

        holding["invested"] =
            invested

        holding["unrealized_profit"] =
            profit

        holding[
            "unrealized_return_percent"
        ] = return_percent


# ============================================================
# 更新總資產
# ============================================================

def update_total_assets(portfolio):

    cash =
        float(
            portfolio.get(
                "cash",
                0
            )
        )


    market_value = sum(

        float(
            holding.get(
                "market_value",
                0
            )
        )

        for holding
        in portfolio.get(
            "holdings",
            []
        )

    )


    total_assets =
        cash + market_value


    initial_capital =
        float(
            portfolio.get(
                "initial_capital",
                INITIAL_CAPITAL
            )
        )


    total_profit =
        total_assets - initial_capital


    total_return = 0

    if initial_capital > 0:

        total_return =
            total_profit /
            initial_capital *
            100


    portfolio["cash"] =
        cash

    portfolio["total_assets"] =
        total_assets

    portfolio["total_profit"] =
        total_profit

    portfolio[
        "total_return_percent"
    ] = total_return


# ============================================================
# 每日績效
# ============================================================

def update_performance(portfolio):

    today = today_string()

    total_assets =
        float(
            portfolio.get(
                "total_assets",
                INITIAL_CAPITAL
            )
        )


    initial_capital =
        float(
            portfolio.get(
                "initial_capital",
                INITIAL_CAPITAL
            )
        )


    return_percent = 0

    if initial_capital > 0:

        return_percent =
            (
                total_assets -
                initial_capital
            ) / initial_capital * 100


    performance =
        portfolio.setdefault(
            "performance",
            []
        )


    # 同一天重跑就更新，不重複增加
    existing = None

    for row in performance:

        if row.get("date") == today:

            existing = row
            break


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


    if existing:

        existing.update(row)

    else:

        performance.append(row)


    performance.sort(
        key=lambda x:
            str(x.get("date", ""))
    )


# ============================================================
# 主程式
# ============================================================

def main():

    print("=" * 60)

    print(
        "ChatGPT AI Trading Portfolio"
    )

    print(
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    print("=" * 60)


    # --------------------------------------------------------
    # 載入 Portfolio
    # --------------------------------------------------------

    portfolio =
        load_json(
            PORTFOLIO_FILE,
            default_portfolio()
        )


    # --------------------------------------------------------
    # 每次執行先把最新 AI Top 5 加入訊號佇列
    # --------------------------------------------------------

    update_signals(
        portfolio
    )


    # --------------------------------------------------------
    # 準備監控股票
    # --------------------------------------------------------

    monitor_stocks = []


    for signal in portfolio.get(
        "signal_queue",
        []
    ):

        if signal.get("status") == "waiting":

            monitor_stocks.append({

                "symbol":
                    signal.get("symbol"),

                "market":
                    signal.get("market")

            })


    for holding in portfolio.get(
        "holdings",
        []
    ):

        monitor_stocks.append({

            "symbol":
                holding.get("symbol"),

            "market":
                holding.get("market")

        })


    # 去重
    unique = {}

    for stock in monitor_stocks:

        unique[
            str(stock["symbol"])
        ] = stock


    monitor_stocks =
        list(
            unique.values()
        )


    print(
        "監控股票:",
        [
            x["symbol"]
            for x in monitor_stocks
        ]
    )


    # --------------------------------------------------------
    # 即時行情
    # --------------------------------------------------------

    quotes =
        get_realtime_quotes(
            monitor_stocks
        )


    print(
        "取得即時行情:",
        len(quotes)
    )


    # --------------------------------------------------------
    # 第一筆買入
    # --------------------------------------------------------

    process_first_buy(
        portfolio,
        quotes
    )


    # --------------------------------------------------------
    # 更新持股
    # --------------------------------------------------------

    update_holdings(
        portfolio,
        quotes
    )


    # --------------------------------------------------------
    # 更新等待名單
    # --------------------------------------------------------

    refresh_waiting(
        portfolio
    )


    # --------------------------------------------------------
    # 更新總資產
    # --------------------------------------------------------

    update_total_assets(
        portfolio
    )


    # --------------------------------------------------------
    # 每日績效
    # --------------------------------------------------------

    update_performance(
        portfolio
    )


    # --------------------------------------------------------
    # 更新時間
    # --------------------------------------------------------

    portfolio["date"] =
        today_string()

    portfolio["updated_at"] =
        datetime.now().isoformat(
            timespec="seconds"
        )


    # --------------------------------------------------------
    # 保存
    # --------------------------------------------------------

    save_json(
        PORTFOLIO_FILE,
        portfolio
    )


    print()

    print(
        "現金:",
        portfolio["cash"]
    )

    print(
        "總資產:",
        portfolio["total_assets"]
    )

    print(
        "累積報酬:",
        portfolio[
            "total_return_percent"
        ],
        "%"
    )

    print(
        "目前持股:",
        len(
            portfolio.get(
                "holdings",
                []
            )
        )
    )

    print(
        "等待進場:",
        len(
            portfolio.get(
                "waiting",
                []
            )
        )
    )

    print()

    print(
        f"已更新 {PORTFOLIO_FILE}"
    )


if __name__ == "__main__":
    main()
