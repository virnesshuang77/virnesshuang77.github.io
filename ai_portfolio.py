import json
import os
import requests
from datetime import datetime
from pathlib import Path


# ============================================================
# 基本設定
# ============================================================

TOP100_FILE = "tw_top100.json"
FUNDAMENTALS_FILE = "tw_fundamentals.json"
PORTFOLIO_FILE = "ai_portfolio.json"

INITIAL_CAPITAL = 1_000_000

# 每一檔股票最多使用初始資金的 20%
MAX_ALLOCATION_PER_STOCK = 0.20

# 第一筆買入使用該檔目標資金的 30%
FIRST_BUY_ALLOCATION = 0.30


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

        print(f"讀取 {path} 失敗：{e}")

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
# 數字
# ============================================================

def num(value, default=0):

    try:

        if value is None:
            return default

        return float(value)

    except:

        return default


# ============================================================
# Portfolio 初始結構
# ============================================================

def create_default_portfolio():

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
# 基本面篩選
#
# 這裡與 aitrading.html 保持一致
# ============================================================

def fundamental_pass(stock):

    if not stock:

        return False


    # 沒有基本面資料直接排除

    if stock.get(
        "fundamental_available"
    ) is False:

        return False


    eps = num(
        stock.get("quarter_eps")
    )

    revenue = num(
        stock.get("ttm_revenue")
    )

    net_income = num(
        stock.get("ttm_net_income")
    )

    roe = num(
        stock.get("roe_ttm")
    )


    # EPS 必須為正

    if eps <= 0:

        return False


    # TTM 營收必須存在

    if revenue <= 0:

        return False


    # TTM 淨利必須為正

    if net_income <= 0:

        return False


    # ROE 不接受負值

    if roe < 0:

        return False


    return True


# ============================================================
# 技術面分數
#
# 與 aitrading.html 保持一致
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
        stock.get(
            "volume_ratio_20d"
        )
    )

    return5 = num(
        stock.get("return_5d")
    )

    return20 = num(
        stock.get("return_20d")
    )


    # --------------------------------------------------------
    # 股價 > MA20
    # --------------------------------------------------------

    if (
        close > 0
        and ma20 > 0
        and close > ma20
    ):

        score += 3


    # --------------------------------------------------------
    # MA20 > MA60
    # --------------------------------------------------------

    if (
        ma20 > 0
        and ma60 > 0
        and ma20 > ma60
    ):

        score += 3


    # --------------------------------------------------------
    # MA5 > MA20
    # --------------------------------------------------------

    if (
        ma5 > 0
        and ma20 > 0
        and ma5 > ma20
    ):

        score += 2


    # --------------------------------------------------------
    # 5 日報酬為正
    # --------------------------------------------------------

    if return5 > 0:

        score += 1


    # --------------------------------------------------------
    # 20 日報酬為正
    # --------------------------------------------------------

    if return20 > 0:

        score += 2


    # --------------------------------------------------------
    # 成交量放大
    # --------------------------------------------------------

    if volume_ratio >= 1.2:

        score += 1


    return score


# ============================================================
# 建立真正的 AI 最終候選
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


    # --------------------------------------------------------
    # 建立基本面 Map
    # --------------------------------------------------------

    fundamental_map = {}


    for stock in fundamentals:

        symbol = str(
            stock.get("symbol", "")
        ).strip()


        if symbol:

            fundamental_map[
                symbol
            ] = stock


    candidates = []


    # --------------------------------------------------------
    # Top 100 → 基本面
    # --------------------------------------------------------

    for stock in top100:

        symbol = str(
            stock.get("symbol", "")
        ).strip()


        if not symbol:

            continue


        fundamental =
            fundamental_map.get(
                symbol
            )


        if not fundamental:

            continue


        # ----------------------------------------------------
        # 基本面篩選
        # ----------------------------------------------------

        if not fundamental_pass(
            fundamental
        ):

            continue


        # ----------------------------------------------------
        # 合併資料
        # ----------------------------------------------------

        merged = {

            **stock,

            **fundamental

        }


        # ----------------------------------------------------
        # 技術面
        # ----------------------------------------------------

        tech_score =
            technical_score(
                merged
            )


        # ----------------------------------------------------
        # 技術面最低門檻
        # ----------------------------------------------------

        if tech_score < 4:

            continue


        merged[
            "_technical_score"
        ] = tech_score


        candidates.append(
            merged
        )


    # --------------------------------------------------------
    # 排序
    #
    # 1. 技術面
    # 2. ROE
    # 3. 成交金額
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # 最多 5 檔
    # --------------------------------------------------------

    final_stocks =
        candidates[:5]


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
            f""
            f"技術分數="
            f"{stock.get('_technical_score')}"
        )


    return (
        top100_data,
        final_stocks
    )


# ============================================================
# 加入新的 AI 訊號
# ============================================================

def add_new_signals(
    portfolio,
    top100_data,
    final_stocks
):

    signal_date =
        top100_data.get(
            "date"
        )


    if not signal_date:

        print(
            "找不到 AI 選股日期"
        )

        return


    signal_queue =
        portfolio.setdefault(
            "signal_queue",
            []
        )


    # --------------------------------------------------------
    # 已經存在的訊號
    # --------------------------------------------------------

    existing = {

        (
            str(x.get("symbol")),
            str(x.get("signal_date"))
        )

        for x in signal_queue

    }


    # --------------------------------------------------------
    # 已持有股票
    # --------------------------------------------------------

    holdings_symbols = {

        str(
            x.get("symbol")
        )

        for x in portfolio.get(
            "holdings",
            []
        )

    }


    # --------------------------------------------------------
    # 加入最終 0～5 檔
    # --------------------------------------------------------

    for stock in final_stocks:

        symbol = str(
            stock.get("symbol", "")
        ).strip()


        if not symbol:

            continue


        key = (
            symbol,
            str(signal_date)
        )


        if key in existing:

            continue


        # 已經持有就不重新建立訊號

        if symbol in holdings_symbols:

            continue


        reference_close =
            num(
                stock.get("close")
            )


        if reference_close <= 0:

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

            # ★ 鎖定選股日收盤價
            "reference_close":
                reference_close,

            # ★ 第一筆買入觸發價
            "first_buy_trigger":
                reference_close,

            "status":
                "waiting",

            "first_buy_allocation":
                FIRST_BUY_ALLOCATION,

            "created_at":
                datetime.now().isoformat(
                    timespec="seconds"
                )

        }


        signal_queue.append(
            signal
        )


        existing.add(
            key
        )


        print(
            f"新增等待訊號："
            f"{symbol} "
            f"{stock.get('name')} "
            f""
            f"參考收盤="
            f"{reference_close}"
        )


# ============================================================
# 即時行情
# ============================================================

def get_realtime_quotes(
    stocks
):

    quotes = {}


    # --------------------------------------------------------
    # TWSE
    # --------------------------------------------------------

    twse_symbols = [

        str(
            x.get("symbol")
        )

        for x in stocks

        if str(
            x.get("market", "")
        ).upper() == "TWSE"

    ]


    if twse_symbols:

        ex_ch = "|".join(

            f"tse_{symbol}.tw"

            for symbol
            in twse_symbols

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
                        "0"

                },

                headers={

                    "User-Agent":
                        "Mozilla/5.0"

                },

                timeout=20

            )


            response.raise_for_status()


            data =
                response.json()


            for item in data.get(
                "msgArray",
                []
            ):

                symbol = str(
                    item.get("c", "")
                )


                if not symbol:

                    continue


                price = None


                # 最新成交價

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


                # 沒有最新成交價時
                # 嘗試最佳賣價

                if price is None:

                    ask = item.get("a")


                    if ask:

                        try:

                            first =
                                ask.split(
                                    "_"
                                )[0]


                            if first not in (
                                "",
                                "-"
                            ):

                                price =
                                    float(
                                        first
                                    )

                        except:

                            pass


                # 再嘗試最佳買價

                if price is None:

                    bid = item.get("b")


                    if bid:

                        try:

                            first =
                                bid.split(
                                    "_"
                                )[0]


                            if first not in (
                                "",
                                "-"
                            ):

                                price =
                                    float(
                                        first
                                    )

                        except:

                            pass


                if price is not None:

                    quotes[symbol] = {

                        "price":
                            price,

                        "market":
                            "TWSE",

                        "time":
                            item.get(
                                "t",
                                ""
                            )

                    }


        except Exception as e:

            print(
                "TWSE 行情取得失敗：",
                e
            )


    # --------------------------------------------------------
    # TPEx
    # --------------------------------------------------------

    tpex_symbols = [

        str(
            x.get("symbol")
        )

        for x in stocks

        if str(
            x.get("market", "")
        ).upper() in (
            "TPEX",
            "TPEx"
        )

    ]


    if tpex_symbols:

        try:

            response = requests.get(

                "https://www.tpex.org.tw/"
                "openapi/v1.1/"
                "tpex_mainboard_quotes",

                headers={

                    "User-Agent":
                        "Mozilla/5.0"

                },

                timeout=20

            )


            response.raise_for_status()


            data =
                response.json()


            wanted =
                set(
                    tpex_symbols
                )


            for item in data:

                symbol = str(

                    item.get(
                        "SecuritiesCompanyCode",
                        ""
                    )

                )


                if symbol not in wanted:

                    continue


                price = (

                    item.get("Close")

                    or

                    item.get(
                        "ClosingPrice"
                    )

                )


                try:

                    price =
                        float(price)

                except:

                    continue


                quotes[symbol] = {

                    "price":
                        price,

                    "market":
                        "TPEX",

                    "time":
                        ""

                }


        except Exception as e:

            print(
                "TPEx 行情取得失敗：",
                e
            )


    return quotes


# ============================================================
# 第一次買入
#
# 核心規則：
#
# AI 選股日收盤價 = reference_close
#
# 下一交易日盤中：
#
# current_price <= reference_close
#
# → 第一筆買入
# ============================================================

def process_first_buy(
    portfolio,
    realtime_quotes
):

    today =
        today_string()


    # --------------------------------------------------------
    # 判斷今天是不是 AI 選股日之後
    # --------------------------------------------------------

    for signal in portfolio.get(
        "signal_queue",
        []
    ):

        if signal.get(
            "status"
        ) != "waiting":

            continue


        signal_date =
            signal.get(
                "signal_date"
            )


        if not signal_date:

            continue


        # ----------------------------------------------------
        # 同一天不能買
        # ----------------------------------------------------

        if str(signal_date) >= str(today):

            continue


        symbol =
            str(
                signal.get(
                    "symbol"
                )
            )


        quote =
            realtime_quotes.get(
                symbol
            )


        if not quote:

            continue


        current_price =
            num(
                quote.get(
                    "price"
                )
            )


        if current_price <= 0:

            continue


        reference_close =
            num(
                signal.get(
                    "reference_close"
                )
            )


        if reference_close <= 0:

            continue


        # ====================================================
        # ★ 核心買入條件
        # ====================================================

        if current_price > reference_close:

            continue


        # ----------------------------------------------------
        # 每檔最多 20% 初始資金
        # ----------------------------------------------------

        target_budget =
            INITIAL_CAPITAL * \
            MAX_ALLOCATION_PER_STOCK


        # 第一筆 = 30%

        buy_budget =
            target_budget * \
            FIRST_BUY_ALLOCATION


        cash =
            num(
                portfolio.get(
                    "cash"
                )
            )


        if cash <= 0:

            print(
                "現金不足"
            )

            continue


        buy_budget =
            min(
                buy_budget,
                cash
            )


        quantity = int(

            buy_budget //
            current_price

        )


        if quantity <= 0:

            print(
                f"{symbol} 資金不足以買入 1 股"
            )

            continue


        actual_amount =
            quantity * current_price


        # ----------------------------------------------------
        # 扣現金
        # ----------------------------------------------------

        portfolio["cash"] =
            cash - actual_amount


        # ----------------------------------------------------
        # 建立持股
        # ----------------------------------------------------

        portfolio.setdefault(
            "holdings",
            []
        ).append({

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
                signal_date,

            "reference_close":
                reference_close,

            "buy_stage":
                1,

            "allocation_used":
                FIRST_BUY_ALLOCATION

        })


        # ----------------------------------------------------
        # 更新訊號
        # ----------------------------------------------------

        signal["status"] =
            "holding"


        signal["first_buy_date"] =
            today


        signal["first_buy_price"] =
            current_price


        # ----------------------------------------------------
        # 保存交易紀錄
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
                "盤中價格 ≤ AI 選股日收盤價",

            "signal_date":
                signal_date,

            "reference_close":
                reference_close

        })


        print(
            "★ 第一筆買入：",
            symbol,
            quantity,
            "股 @",
            current_price
        )


# ============================================================
# 更新目前持股價格
# ============================================================

def update_holdings(
    portfolio,
    realtime_quotes
):

    for holding in portfolio.get(
        "holdings",
        []
    ):

        symbol =
            str(
                holding.get(
                    "symbol"
                )
            )


        quote =
            realtime_quotes.get(
                symbol
            )


        if not quote:

            continue


        current_price =
            num(
                quote.get(
                    "price"
                )
            )


        if current_price <= 0:

            continue


        quantity =
            num(
                holding.get(
                    "quantity"
                )
            )


        average_cost =
            num(
                holding.get(
                    "average_cost"
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
# 更新等待進場
# ============================================================

def update_waiting(
    portfolio
):

    waiting = []


    holdings_symbols = {

        str(
            x.get("symbol")
        )

        for x in portfolio.get(
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


        symbol =
            str(
                signal.get(
                    "symbol"
                )
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
                    "reference_close"
                ),

            "status":
                "等待價格 ≤ 選股日收盤"

        })


    portfolio["waiting"] =
        waiting


# ============================================================
# 更新總資產
# ============================================================

def update_total_assets(
    portfolio
):

    cash =
        num(
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


    total_assets =
        cash + market_value


    initial_capital =
        num(
            portfolio.get(
                "initial_capital"
            ),
            INITIAL_CAPITAL
        )


    total_profit =
        total_assets - initial_capital


    total_return = 0


    if initial_capital > 0:

        total_return =
            total_profit /
            initial_capital *
            100


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

    today =
        today_string()


    total_assets =
        num(
            portfolio.get(
                "total_assets"
            )
        )


    initial_capital =
        num(
            portfolio.get(
                "initial_capital"
            ),
            INITIAL_CAPITAL
        )


    return_percent = 0


    if initial_capital > 0:

        return_percent = (

            total_assets -
            initial_capital

        ) / initial_capital * 100


    performance =
        portfolio.setdefault(
            "performance",
            []
        )


    existing = None


    for row in performance:

        if row.get(
            "date"
        ) == today:

            existing = row

            break


    new_row = {

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

        existing.update(
            new_row
        )

    else:

        performance.append(
            new_row
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
        datetime.now().isoformat(
            timespec="seconds"
        )
    )
    print("=" * 65)
    print()


    # ========================================================
    # 1. 讀取 / 建立 Portfolio
    # ========================================================

    portfolio =
        load_json(
            PORTFOLIO_FILE,
            create_default_portfolio()
        )


    # 如果舊 JSON 缺少必要欄位
    # 補回來

    defaults =
        create_default_portfolio()


    for key, value in defaults.items():

        if key not in portfolio:

            portfolio[key] = value


    # ========================================================
    # 2. 從 Top100 + 基本面 + 技術面
    #    找出真正最終 0～5 檔
    # ========================================================

    (
        top100_data,
        final_stocks
    ) = select_final_stocks()


    # ========================================================
    # 3. 加入 AI 訊號
    # ========================================================

    add_new_signals(

        portfolio,

        top100_data,

        final_stocks

    )


    # ========================================================
    # 4. 建立需要監控的股票
    # ========================================================

    monitor = {}


    for signal in portfolio.get(
        "signal_queue",
        []
    ):

        if signal.get(
            "status"
        ) == "waiting":

            symbol =
                str(
                    signal.get(
                        "symbol"
                    )
                )


            monitor[symbol] = {

                "symbol":
                    symbol,

                "market":
                    signal.get(
                        "market"
                    )

            }


    for holding in portfolio.get(
        "holdings",
        []
    ):

        symbol =
            str(
                holding.get(
                    "symbol"
                )
            )


        monitor[symbol] = {

            "symbol":
                symbol,

            "market":
                holding.get(
                    "market"
                )

        }


    monitor_stocks =
        list(
            monitor.values()
        )


    print()
    print(
        "目前監控：",
        [
            x["symbol"]
            for x in monitor_stocks
        ]
    )


    # ========================================================
    # 5. 取得即時行情
    # ========================================================

    quotes =
        get_realtime_quotes(
            monitor_stocks
        )


    print(
        f"取得行情：{len(quotes)} 檔"
    )


    # ========================================================
    # 6. 判斷是否觸發第一次買入
    # ========================================================

    process_first_buy(

        portfolio,

        quotes

    )


    # ========================================================
    # 7. 更新目前持股
    # ========================================================

    update_holdings(

        portfolio,

        quotes

    )


    # ========================================================
    # 8. 更新等待名單
    # ========================================================

    update_waiting(
        portfolio
    )


    # ========================================================
    # 9. 更新總資產
    # ========================================================

    update_total_assets(
        portfolio
    )


    # ========================================================
    # 10. 更新每日績效
    # ========================================================

    update_daily_performance(
        portfolio
    )


    # ========================================================
    # 11. 更新時間
    # ========================================================

    portfolio["date"] =
        today_string()


    portfolio["updated_at"] =
        datetime.now().isoformat(
            timespec="seconds"
        )


    # ========================================================
    # 12. 儲存
    # ========================================================

    save_json(
        PORTFOLIO_FILE,
        portfolio
    )


    # ========================================================
    # 13. 顯示結果
    # ========================================================

    print()
    print("=" * 65)

    print(
        "現金：",
        round(
            portfolio.get(
                "cash",
                0
            ),
            2
        )
    )

    print(
        "總資產：",
        round(
            portfolio.get(
                "total_assets",
                0
            ),
            2
        )
    )

    print(
        "累積損益：",
        round(
            portfolio.get(
                "total_profit",
                0
            ),
            2
        )
    )

    print(
        "累積報酬率：",
        round(
            portfolio.get(
                "total_return_percent",
                0
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
