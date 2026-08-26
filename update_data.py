import requests
import pandas as pd
import json
import time
from datetime import datetime


# ============================================================
# TWSE API
# ============================================================

TWSE_FUND_URL = (
    "https://www.twse.com.tw/rwd/zh/fund/T86"
)

TWSE_PRICE_URL = (
    "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    )
}


# ============================================================
# 取得今天日期
# ============================================================

def get_today():

    return datetime.now().strftime("%Y%m%d")


# ============================================================
# 取得三大法人資料
# ============================================================

def get_twse_fund_data(date):

    print()
    print("=" * 70)
    print(f"正在取得三大法人資料：{date}")
    print("=" * 70)

    params = {
        "date": date,
        "selectType": "ALLBUT0999",
        "response": "json"
    }

    response = requests.get(
        TWSE_FUND_URL,
        params=params,
        headers=HEADERS,
        timeout=30
    )

    print(
        "HTTP Status：",
        response.status_code
    )

    response.raise_for_status()

    data = response.json()

    status = data.get("stat")

    print(
        "TWSE Status：",
        status
    )

    if status != "OK":

        print(
            "目前尚未取得今天的三大法人資料。"
        )

        return None

    rows = data.get("data", [])

    fields = data.get("fields", [])

    if not rows:

        print(
            "TWSE 回傳資料為空。"
        )

        return None

    df = pd.DataFrame(
        rows,
        columns=fields
    )

    print(
        "取得資料筆數：",
        len(df)
    )

    return df


# ============================================================
# 清理三大法人資料
# ============================================================

def clean_fund_data(df):

    df = df.rename(
        columns={
            "證券代號": "stock_id",
            "證券名稱": "stock_name"
        }
    )

    # 股票代號
    df["stock_id"] = (
        df["stock_id"]
        .astype(str)
        .str.strip()
    )

    # 股票名稱
    df["stock_name"] = (
        df["stock_name"]
        .astype(str)
        .str.strip()
    )

    # 數字欄位
    for column in df.columns:

        if column in [
            "stock_id",
            "stock_name"
        ]:
            continue

        df[column] = (
            df[column]
            .astype(str)
            .str.replace(
                ",",
                "",
                regex=False
            )
            .replace(
                [
                    "--",
                    "---",
                    ""
                ],
                "0"
            )
        )

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        ).fillna(0)

    return df


# ============================================================
# 取得收盤價
# ============================================================

def get_price_data(date):

    print()
    print("=" * 70)
    print(f"正在取得收盤行情：{date}")
    print("=" * 70)

    params = {
        "date": date,
        "type": "ALL",
        "response": "json"
    }

    response = requests.get(
        TWSE_PRICE_URL,
        params=params,
        headers=HEADERS,
        timeout=30
    )

    print(
        "HTTP Status：",
        response.status_code
    )

    response.raise_for_status()

    data = response.json()

    if data.get("stat") != "OK":

        print(
            "目前尚未取得收盤行情。"
        )

        return None

    tables = data.get(
        "tables",
        []
    )

    price_table = None

    for table in tables:

        fields = table.get(
            "fields",
            []
        )

        if (
            "證券代號" in fields
            and
            "收盤價" in fields
        ):

            price_table = table

            break

    if price_table is None:

        print(
            "找不到收盤價資料表。"
        )

        return None

    price_df = pd.DataFrame(
        price_table["data"],
        columns=price_table["fields"]
    )

    price_df = price_df.rename(
        columns={
            "證券代號": "stock_id",
            "收盤價": "close_price"
        }
    )

    price_df["stock_id"] = (
        price_df["stock_id"]
        .astype(str)
        .str.strip()
    )

    price_df["close_price"] = (
        price_df["close_price"]
        .astype(str)
        .str.replace(
            ",",
            "",
            regex=False
        )
        .replace(
            [
                "--",
                "---",
                "除權息",
                "X",
                ""
            ],
            "0"
        )
    )

    price_df["close_price"] = pd.to_numeric(
        price_df["close_price"],
        errors="coerce"
    ).fillna(0)

    print(
        "取得收盤價股票數量：",
        len(price_df)
    )

    return price_df


# ============================================================
# 建立 data.json
# ============================================================

def save_data_json(df, data_date):

    result = {
        "data_date": data_date,
        "source": "TWSE",
        "data": df.to_dict(
            orient="records"
        )
    }

    with open(
        "data.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("✅ data.json 已建立")


# ============================================================
# 建立 money_rank.json
# ============================================================

def create_money_rank(
    fund_df,
    price_df,
    data_date
):

    print()
    print("=" * 70)
    print("正在建立法人資金排行榜")
    print("=" * 70)

    df = fund_df.merge(
        price_df[
            [
                "stock_id",
                "close_price"
            ]
        ],
        on="stock_id",
        how="left"
    )

    df["close_price"] = (
        df["close_price"]
        .fillna(0)
    )

    # --------------------------------------------------------
    # 計算資金
    # --------------------------------------------------------

    df["foreign_money"] = (
        df[
            "外陸資買賣超股數(不含外資自營商)"
        ]
        *
        df["close_price"]
    )

    df["investment_trust_money"] = (
        df[
            "投信買賣超股數"
        ]
        *
        df["close_price"]
    )

    df["dealer_money"] = (
        df[
            "自營商買賣超股數"
        ]
        *
        df["close_price"]
    )

    df["total_money"] = (
        df[
            "三大法人買賣超股數"
        ]
        *
        df["close_price"]
    )

    # --------------------------------------------------------
    # 排名函數
    # --------------------------------------------------------

    def make_rank(column):

        result = (
            df[
                [
                    "stock_id",
                    "stock_name",
                    "close_price",
                    column
                ]
            ]
            .sort_values(
                column,
                ascending=False
            )
            .reset_index(drop=True)
        )

        result["rank"] = (
            result.index + 1
        )

        return result.head(100)

    # --------------------------------------------------------
    # 四種排行
    # --------------------------------------------------------

    foreign = make_rank(
        "foreign_money"
    )

    investment_trust = make_rank(
        "investment_trust_money"
    )

    dealer = make_rank(
        "dealer_money"
    )

    total = make_rank(
        "total_money"
    )

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    result = {

        "data_date": data_date,

        "currency": "TWD",

        "unit": "TWD",

        "top_n": 100,

        "foreign":
            foreign.to_dict(
                orient="records"
            ),

        "investment_trust":
            investment_trust.to_dict(
                orient="records"
            ),

        "dealer":
            dealer.to_dict(
                orient="records"
            ),

        "total":
            total.to_dict(
                orient="records"
            )

    }

    with open(
        "money_rank.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(
        "✅ money_rank.json 已建立"
    )


# ============================================================
# 主程式
# ============================================================

def main():

    print()
    print("=" * 70)
    print("TWSE 每日法人資料自動更新")
    print("=" * 70)

    today = get_today()

    data_date = datetime.strptime(
        today,
        "%Y%m%d"
    ).strftime(
        "%Y-%m-%d"
    )

    print(
        "今天日期：",
        data_date
    )

    # ========================================================
    # 等待 TWSE 資料
    #
    # GitHub Actions 16:00 開始
    # 每 10 分鐘重新嘗試
    # 最多 18 次
    # ========================================================

    fund_df = None

    max_retry = 18

    for attempt in range(
        1,
        max_retry + 1
    ):

        print()
        print(
            "=" * 70
        )

        print(
            f"資料取得嘗試 "
            f"{attempt}/{max_retry}"
        )

        print(
            "=" * 70
        )

        try:

            fund_df = get_twse_fund_data(
                today
            )

        except Exception as error:

            print(
                "取得資料發生錯誤：",
                error
            )

            fund_df = None

        if fund_df is not None:

            print()
            print(
                "🎉 成功取得今天的三大法人資料！"
            )

            break

        if attempt < max_retry:

            print()
            print(
                "目前沒有資料。"
            )

            print(
                "10 分鐘後再次嘗試..."
            )

            time.sleep(600)

    # ========================================================
    # 18 次都失敗
    # ========================================================

    if fund_df is None:

        raise Exception(
            "今天未能取得 TWSE 三大法人資料。"
        )

    # ========================================================
    # 清理
    # ========================================================

    fund_df = clean_fund_data(
        fund_df
    )

    print()
    print(
        "清理完成。"
    )

    print(
        "股票數量：",
        len(fund_df)
    )

    # ========================================================
    # 儲存 data.json
    # ========================================================

    save_data_json(
        fund_df,
        data_date
    )

    # ========================================================
    # 取得收盤價
    # ========================================================

    price_df = None

    max_price_retry = 6

    for attempt in range(
        1,
        max_price_retry + 1
    ):

        print()
        print(
            f"收盤價取得 "
            f"{attempt}/{max_price_retry}"
        )

        try:

            price_df = get_price_data(
                today
            )

        except Exception as error:

            print(
                "取得收盤價發生錯誤：",
                error
            )

            price_df = None

        if price_df is not None:

            break

        if attempt < max_price_retry:

            print(
                "5 分鐘後重新嘗試..."
            )

            time.sleep(300)

    if price_df is None:

        raise Exception(
            "今天未能取得 TWSE 收盤價資料。"
        )

    # ========================================================
    # 建立 money_rank.json
    # ========================================================

    create_money_rank(
        fund_df,
        price_df,
        data_date
    )

    # ========================================================
    # 完成
    # ========================================================

    print()
    print("=" * 70)
    print("🎉 今日資料更新完成")
    print("=" * 70)

    print(
        "資料日期：",
        data_date
    )

    print(
        "股票數量：",
        len(fund_df)
    )

    print()
    print(
        "已更新："
    )

    print(
        "  data.json"
    )

    print(
        "  money_rank.json"
    )

    print("=" * 70)


# ============================================================
# 執行
# ============================================================

if __name__ == "__main__":

    main()