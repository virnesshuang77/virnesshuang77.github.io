import json
import time
from datetime import datetime
from pathlib import Path

import requests


# ============================================================
# AI Trading - Taiwan Fundamentals
# ============================================================
#
# 讀取：
#
#     tw_top100.json
#
# 取得：
#
#     TaiwanStockFinancialStatements
#     TaiwanStockBalanceSheet
#
# 最後產生：
#
#     tw_fundamentals.json
#
#
# 目前只處理 Top 100。
#
# ETF / 無財報資料商品：
#
#     保留在結果中
#     fundamental_available = false
#
#
# ============================================================


TOP100_FILE = Path(
    "tw_top100.json"
)

OUTPUT_FILE = Path(
    "tw_fundamentals.json"
)


API_URL = (
    "https://api.finmindtrade.com/"
    "api/v4/data"
)


TIMEOUT = 30


HEADERS = {

    "User-Agent":
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0 Safari/537.36"

}


SESSION = requests.Session()

SESSION.headers.update(
    HEADERS
)


# ============================================================
# 基本工具
# ============================================================

def clean_number(value):

    if value is None:
        return None

    if isinstance(
        value,
        (int, float)
    ):

        return value

    try:

        text = str(
            value
        ).strip()

        if text in (
            "",
            "-",
            "--",
            "None",
            "null"
        ):

            return None

        return float(
            text.replace(",", "")
        )

    except Exception:

        return None


def safe_divide(
    numerator,
    denominator
):

    if (
        numerator is None
        or denominator is None
        or denominator == 0
    ):

        return None

    return (
        numerator
        / denominator
    )


def percentage(
    numerator,
    denominator
):

    value = safe_divide(
        numerator,
        denominator
    )

    if value is None:

        return None

    return round(
        value * 100,
        4
    )


# ============================================================
# FinMind API
# ============================================================

def fetch_finmind(
    dataset,
    symbol
):

    params = {

        "dataset":
            dataset,

        "data_id":
            symbol,

        # ----------------------------------------------------
        # 我們只需要最近幾季
        # ----------------------------------------------------

        "start_date":
            "2024-01-01"

    }

    try:

        response = SESSION.get(

            API_URL,

            params=params,

            timeout=TIMEOUT

        )

        response.raise_for_status()

        result = response.json()

    except Exception as exc:

        print(

            f"[API ERROR] "
            f"{dataset} "
            f"{symbol}: "
            f"{exc}"

        )

        return []

    if not isinstance(
        result,
        dict
    ):

        return []

    data = result.get(
        "data",
        []
    )

    if not isinstance(
        data,
        list
    ):

        return []

    return data


# ============================================================
# 將 FinMind 資料整理成：
#
# date -> type -> value
# ============================================================

def organize_financial_data(
    rows
):

    result = {}

    for row in rows:

        if not isinstance(
            row,
            dict
        ):

            continue

        date = row.get(
            "date"
        )

        item_type = row.get(
            "type"
        )

        value = clean_number(
            row.get(
                "value"
            )
        )

        if not date:

            continue

        if not item_type:

            continue

        if value is None:

            continue

        if date not in result:

            result[date] = {}

        result[
            date
        ][
            item_type
        ] = value

    return result


# ============================================================
# 找欄位
# ============================================================

def find_value(
    quarter,
    possible_names
):

    for name in possible_names:

        if name in quarter:

            return quarter[
                name
            ]

    return None


# ============================================================
# 找最近四季
# ============================================================

def get_latest_quarters(
    financial
):

    dates = sorted(
        financial.keys()
    )

    return dates[
        -4:
    ]


# ============================================================
# 找去年同期
# ============================================================

def get_same_quarter_last_year(
    financial,
    latest_date
):

    try:

        year = int(
            latest_date[:4]
        )

        month = int(
            latest_date[5:7]
        )

        target = (
            f"{year - 1:04d}-"
            f"{month:02d}-"
            f"{latest_date[8:10]}"
        )

        if target in financial:

            return target

    except Exception:

        pass

    # --------------------------------------------------------
    # 如果日期格式不同
    # 就用季度位置推估
    # --------------------------------------------------------

    dates = sorted(
        financial.keys()
    )

    if latest_date not in dates:

        return None

    index = dates.index(
        latest_date
    )

    target_index = (
        index - 4
    )

    if target_index >= 0:

        return dates[
            target_index
        ]

    return None


# ============================================================
# 計算單季資料
# ============================================================

def calculate_quarter_metrics(
    financial,
    latest_date
):

    latest = financial.get(
        latest_date,
        {}
    )

    previous_year_date = (
        get_same_quarter_last_year(
            financial,
            latest_date
        )
    )

    previous_year = {}

    if previous_year_date:

        previous_year = financial.get(
            previous_year_date,
            {}
        )

    # --------------------------------------------------------
    # 收入
    # --------------------------------------------------------

    revenue = find_value(

        latest,

        [
            "Revenue",
            "Income",
            "OperatingRevenue"
        ]

    )

    revenue_last_year = find_value(

        previous_year,

        [
            "Revenue",
            "Income",
            "OperatingRevenue"
        ]

    )

    # --------------------------------------------------------
    # 毛利
    # --------------------------------------------------------

    gross_profit = find_value(

        latest,

        [
            "GrossProfit"
        ]

    )

    # --------------------------------------------------------
    # 營業利益
    # --------------------------------------------------------

    operating_income = find_value(

        latest,

        [
            "OperatingIncome",
            "OperatingIncomeLoss"
        ]

    )

    # --------------------------------------------------------
    # 稅後淨利
    # --------------------------------------------------------

    net_income = find_value(

        latest,

        [
            "IncomeAfterTaxes",
            "ProfitLoss",
            "NetIncome"
        ]

    )

    net_income_last_year = find_value(

        previous_year,

        [
            "IncomeAfterTaxes",
            "ProfitLoss",
            "NetIncome"
        ]

    )

    # --------------------------------------------------------
    # EPS
    # --------------------------------------------------------

    eps = find_value(

        latest,

        [
            "EPS"
        ]

    )

    eps_last_year = find_value(

        previous_year,

        [
            "EPS"
        ]

    )

    # --------------------------------------------------------
    # 毛利率
    # --------------------------------------------------------

    gross_margin = percentage(

        gross_profit,

        revenue

    )

    # --------------------------------------------------------
    # 營益率
    # --------------------------------------------------------

    operating_margin = percentage(

        operating_income,

        revenue

    )

    # --------------------------------------------------------
    # 稅後淨利率
    # --------------------------------------------------------

    net_margin = percentage(

        net_income,

        revenue

    )

    # --------------------------------------------------------
    # 營收年增率
    # --------------------------------------------------------

    revenue_yoy = None

    if (
        revenue is not None
        and revenue_last_year is not None
        and revenue_last_year != 0
    ):

        revenue_yoy = round(

            (
                revenue
                / revenue_last_year
                - 1
            )
            * 100,

            4

        )

    # --------------------------------------------------------
    # 淨利年增率
    # --------------------------------------------------------

    net_income_yoy = None

    if (
        net_income is not None
        and net_income_last_year is not None
        and net_income_last_year != 0
    ):

        net_income_yoy = round(

            (
                net_income
                / net_income_last_year
                - 1
            )
            * 100,

            4

        )

    # --------------------------------------------------------
    # EPS 年增率
    # --------------------------------------------------------

    eps_yoy = None

    if (
        eps is not None
        and eps_last_year is not None
        and eps_last_year != 0
    ):

        eps_yoy = round(

            (
                eps
                / eps_last_year
                - 1
            )
            * 100,

            4

        )

    return {

        "latest_quarter":
            latest_date,

        "previous_year_quarter":
            previous_year_date,

        "revenue":
            revenue,

        "revenue_yoy":
            revenue_yoy,

        "gross_profit":
            gross_profit,

        "gross_margin":
            gross_margin,

        "operating_income":
            operating_income,

        "operating_margin":
            operating_margin,

        "net_income":
            net_income,

        "net_income_yoy":
            net_income_yoy,

        "net_margin":
            net_margin,

        "eps":
            eps,

        "eps_yoy":
            eps_yoy

    }


# ============================================================
# 計算 TTM
# ============================================================

def calculate_ttm(
    financial,
    item_names
):

    dates = get_latest_quarters(
        financial
    )

    values = []

    for date in dates:

        quarter = financial.get(
            date,
            {}
        )

        value = find_value(
            quarter,
            item_names
        )

        if value is None:

            continue

        values.append(
            value
        )

    if not values:

        return None

    return sum(
        values
    )


# ============================================================
# 資產負債表資料
# ============================================================

def calculate_balance_metrics(
    balance,
    financial
):

    dates = sorted(
        balance.keys()
    )

    if not dates:

        return {

            "balance_sheet_date":
                None,

            "assets":
                None,

            "liabilities":
                None,

            "equity":
                None,

            "debt_ratio":
                None,

            "current_assets":
                None,

            "current_liabilities":
                None,

            "current_ratio":
                None,

            "roe_ttm":
                None

        }

    latest_date = dates[-1]

    latest = balance[
        latest_date
    ]

    # --------------------------------------------------------
    # 資產
    # --------------------------------------------------------

    assets = find_value(

        latest,

        [
            "Assets",
            "TotalAssets"
        ]

    )

    # --------------------------------------------------------
    # 負債
    # --------------------------------------------------------

    liabilities = find_value(

        latest,

        [
            "Liabilities",
            "TotalLiabilities"
        ]

    )

    # --------------------------------------------------------
    # 權益
    # --------------------------------------------------------

    equity = find_value(

        latest,

        [
            "Equity",
            "EquityAttributableToOwnersOfParent",
            "TotalEquity"
        ]

    )

    # --------------------------------------------------------
    # 流動資產
    # --------------------------------------------------------

    current_assets = find_value(

        latest,

        [
            "CurrentAssets"
        ]

    )

    # --------------------------------------------------------
    # 流動負債
    # --------------------------------------------------------

    current_liabilities = find_value(

        latest,

        [
            "CurrentLiabilities"
        ]

    )

    # --------------------------------------------------------
    # 負債比
    # --------------------------------------------------------

    debt_ratio = percentage(

        liabilities,

        assets

    )

    # --------------------------------------------------------
    # 流動比
    # --------------------------------------------------------

    current_ratio = None

    if (
        current_assets is not None
        and current_liabilities is not None
        and current_liabilities != 0
    ):

        current_ratio = round(

            current_assets
            / current_liabilities,

            4

        )

    # --------------------------------------------------------
    # ROE
    #
    # 使用 TTM 稅後淨利 /
    # 平均期初期末權益
    #
    # 這是一個模型用的估算值。
    # --------------------------------------------------------

    roe_ttm = None

    ttm_net_income = calculate_ttm(

        financial,

        [
            "IncomeAfterTaxes",
            "ProfitLoss",
            "NetIncome"
        ]

    )

    if (
        ttm_net_income is not None
        and equity is not None
        and equity != 0
    ):

        # 找約一年前的權益
        old_equity = None

        if len(dates) >= 5:

            old_date = dates[-5]

            old_row = balance.get(
                old_date,
                {}
            )

            old_equity = find_value(

                old_row,

                [
                    "Equity",
                    "EquityAttributableToOwnersOfParent",
                    "TotalEquity"
                ]

            )

        if (
            old_equity is not None
            and old_equity != 0
        ):

            average_equity = (
                equity
                + old_equity
            ) / 2

        else:

            average_equity = equity

        roe_ttm = percentage(

            ttm_net_income,

            average_equity

        )

    return {

        "balance_sheet_date":
            latest_date,

        "assets":
            assets,

        "liabilities":
            liabilities,

        "equity":
            equity,

        "debt_ratio":
            debt_ratio,

        "current_assets":
            current_assets,

        "current_liabilities":
            current_liabilities,

        "current_ratio":
            current_ratio,

        "roe_ttm":
            roe_ttm

    }


# ============================================================
# 單一股票
# ============================================================

def process_stock(
    stock
):

    market = stock.get(
        "market"
    )

    symbol = str(
        stock.get(
            "symbol",
            ""
        )
    ).strip()

    name = stock.get(
        "name"
    )

    result = {

        "market":
            market,

        "symbol":
            symbol,

        "name":
            name,

        "fundamental_available":
            False,

        "source":
            "FinMind",

        "data_as_of":
            None

    }

    print()

    print(
        f"[FUNDAMENTAL] "
        f"{symbol} "
        f"{name}"
    )

    # --------------------------------------------------------
    # ETF 等商品可能沒有財報
    # --------------------------------------------------------

    financial_rows = fetch_finmind(

        "TaiwanStockFinancialStatements",

        symbol

    )

    time.sleep(0.25)

    balance_rows = fetch_finmind(

        "TaiwanStockBalanceSheet",

        symbol

    )

    time.sleep(0.25)

    if not financial_rows:

        print(
            "    無財報資料，可能為 ETF 或非公司型商品"
        )

        return result

    financial = organize_financial_data(
        financial_rows
    )

    balance = organize_financial_data(
        balance_rows
    )

    if not financial:

        return result

    dates = sorted(
        financial.keys()
    )

    latest_date = dates[-1]

    quarter_metrics = (
        calculate_quarter_metrics(

            financial,

            latest_date

        )
    )

    balance_metrics = (
        calculate_balance_metrics(

            balance,

            financial

        )
    )

    # --------------------------------------------------------
    # TTM EPS
    # --------------------------------------------------------

    eps_ttm = calculate_ttm(

        financial,

        [
            "EPS"
        ]

    )

    # --------------------------------------------------------
    # TTM Revenue
    # --------------------------------------------------------

    revenue_ttm = calculate_ttm(

        financial,

        [
            "Revenue",
            "Income",
            "OperatingRevenue"
        ]

    )

    # --------------------------------------------------------
    # TTM Net Income
    # --------------------------------------------------------

    net_income_ttm = calculate_ttm(

        financial,

        [
            "IncomeAfterTaxes",
            "ProfitLoss",
            "NetIncome"
        ]

    )

    # --------------------------------------------------------
    # TTM Operating Income
    # --------------------------------------------------------

    operating_income_ttm = calculate_ttm(

        financial,

        [
            "OperatingIncome",
            "OperatingIncomeLoss"
        ]

    )

    # --------------------------------------------------------
    # TTM Gross Profit
    # --------------------------------------------------------

    gross_profit_ttm = calculate_ttm(

        financial,

        [
            "GrossProfit"
        ]

    )

    # --------------------------------------------------------
    # TTM Margin
    # --------------------------------------------------------

    gross_margin_ttm = percentage(

        gross_profit_ttm,

        revenue_ttm

    )

    operating_margin_ttm = percentage(

        operating_income_ttm,

        revenue_ttm

    )

    net_margin_ttm = percentage(

        net_income_ttm,

        revenue_ttm

    )

    result.update({

        "fundamental_available":
            True,

        "latest_quarter":
            quarter_metrics[
                "latest_quarter"
            ],

        "previous_year_quarter":
            quarter_metrics[
                "previous_year_quarter"
            ],

        # ----------------------------------------------------
        # 最新單季
        # ----------------------------------------------------

        "quarter_revenue":
            quarter_metrics[
                "revenue"
            ],

        "quarter_revenue_yoy":
            quarter_metrics[
                "revenue_yoy"
            ],

        "quarter_gross_profit":
            quarter_metrics[
                "gross_profit"
            ],

        "quarter_gross_margin":
            quarter_metrics[
                "gross_margin"
            ],

        "quarter_operating_income":
            quarter_metrics[
                "operating_income"
            ],

        "quarter_operating_margin":
            quarter_metrics[
                "operating_margin"
            ],

        "quarter_net_income":
            quarter_metrics[
                "net_income"
            ],

        "quarter_net_income_yoy":
            quarter_metrics[
                "net_income_yoy"
            ],

        "quarter_net_margin":
            quarter_metrics[
                "net_margin"
            ],

        "quarter_eps":
            quarter_metrics[
                "eps"
            ],

        "quarter_eps_yoy":
            quarter_metrics[
                "eps_yoy"
            ],

        # ----------------------------------------------------
        # TTM
        # ----------------------------------------------------

        "ttm_revenue":
            revenue_ttm,

        "ttm_gross_profit":
            gross_profit_ttm,

        "ttm_gross_margin":
            gross_margin_ttm,

        "ttm_operating_income":
            operating_income_ttm,

        "ttm_operating_margin":
            operating_margin_ttm,

        "ttm_net_income":
            net_income_ttm,

        "ttm_net_margin":
            net_margin_ttm,

        "ttm_eps":
            eps_ttm,

        # ----------------------------------------------------
        # 資產負債
        # ----------------------------------------------------

        "balance_sheet_date":
            balance_metrics[
                "balance_sheet_date"
            ],

        "assets":
            balance_metrics[
                "assets"
            ],

        "liabilities":
            balance_metrics[
                "liabilities"
            ],

        "equity":
            balance_metrics[
                "equity"
            ],

        "debt_ratio":
            balance_metrics[
                "debt_ratio"
            ],

        "current_assets":
            balance_metrics[
                "current_assets"
            ],

        "current_liabilities":
            balance_metrics[
                "current_liabilities"
            ],

        "current_ratio":
            balance_metrics[
                "current_ratio"
            ],

        "roe_ttm":
            balance_metrics[
                "roe_ttm"
            ],

        "data_as_of":
            latest_date

    })

    print(

        f"    季度："
        f"{latest_date}"

    )

    print(

        f"    EPS："
        f"{result.get('quarter_eps')}"

    )

    print(

        f"    營收 YoY："
        f"{result.get('quarter_revenue_yoy')}%"

    )

    print(

        f"    毛利率："
        f"{result.get('quarter_gross_margin')}%"

    )

    print(

        f"    營益率："
        f"{result.get('quarter_operating_margin')}%"

    )

    print(

        f"    ROE TTM："
        f"{result.get('roe_ttm')}%"

    )

    print(

        f"    負債比："
        f"{result.get('debt_ratio')}%"

    )

    return result


# ============================================================
# 主程式
# ============================================================

def main():

    print()

    print(
        "=" * 60
    )

    print(
        "AI Trading - Taiwan Fundamentals"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # 讀取 Top 100
    # --------------------------------------------------------

    if not TOP100_FILE.exists():

        raise RuntimeError(

            "找不到 tw_top100.json"

        )

    with TOP100_FILE.open(

        "r",

        encoding="utf-8"

    ) as file:

        top100_data = json.load(
            file
        )

    stocks = top100_data.get(
        "stocks",
        []
    )

    if len(stocks) != 100:

        raise RuntimeError(

            f"Top 100 數量異常："
            f"{len(stocks)}"

        )

    # --------------------------------------------------------
    # 開始抓取
    # --------------------------------------------------------

    fundamentals = []

    success = 0

    no_data = 0

    for index, stock in enumerate(

        stocks,

        start=1

    ):

        print()

        print(
            "=" * 60
        )

        print(
            f"處理進度："
            f"{index}/100"
        )

        print(
            "=" * 60
        )

        result = process_stock(
            stock
        )

        fundamentals.append(
            result
        )

        if result.get(
            "fundamental_available"
        ):

            success += 1

        else:

            no_data += 1

        # ----------------------------------------------------
        # 避免 API 請求過快
        # ----------------------------------------------------

        time.sleep(0.5)

    # --------------------------------------------------------
    # 建立輸出
    # --------------------------------------------------------

    output = {

        "generated_at":
            datetime.now().isoformat(
                timespec="seconds"
            ),

        "market":
            "TW",

        "source":
            "FinMind",

        "source_datasets": [

            "TaiwanStockFinancialStatements",

            "TaiwanStockBalanceSheet"

        ],

        "top100_date":
            top100_data.get(
                "date"
            ),

        "stock_count":
            len(
                fundamentals
            ),

        "fundamental_count":
            success,

        "no_fundamental_count":
            no_data,

        "stocks":
            fundamentals

    }

    # --------------------------------------------------------
    # 儲存
    # --------------------------------------------------------

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

    print()

    print(
        "=" * 60
    )

    print(
        "基本面資料完成"
    )

    print(
        "=" * 60
    )

    print(
        "Top 100：",
        len(stocks)
    )

    print(
        "有財報：",
        success
    )

    print(
        "無財報：",
        no_data
    )

    print(
        "輸出：",
        OUTPUT_FILE
    )

    print()

    print(
        "完成。"
    )


if __name__ == "__main__":

    main()
