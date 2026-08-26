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

    # --------------------------------------------------------
    # 合併法人資料與收盤價
    # --------------------------------------------------------

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
    # 計算外資資金
    # --------------------------------------------------------

    df["foreign_money"] = (
        df[
            "外陸資買賣超股數(不含外資自營商)"
        ]
        *
        df["close_price"]
    )

    # --------------------------------------------------------
    # 計算投信資金
    # --------------------------------------------------------

    df["investment_trust_money"] = (
        df[
            "投信買賣超股數"
        ]
        *
        df["close_price"]
    )

    # --------------------------------------------------------
    # 計算自營商資金
    # --------------------------------------------------------

    df["dealer_money"] = (
        df[
            "自營商買賣超股數"
        ]
        *
        df["close_price"]
    )

    # --------------------------------------------------------
    # 計算三大法人資金
    # --------------------------------------------------------

    df["total_money"] = (
        df[
            "三大法人買賣超股數"
        ]
        *
        df["close_price"]
    )

    # ========================================================
    # 排名函數
    #
    # 每一種法人：
    #
    # 買超 TOP 100
    # +
    # 賣超 TOP 100
    #
    # 最多 200 筆
    # ========================================================

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
        .reset_index(
            drop=True
        )
    )

    result["rank"] = (
        result.index + 1
    )

    return result.head(100)

        # ----------------------------------------------------
        # 賣超 TOP 100
        # 負數由小到大
        #
        # 例如：
        # -100億
        # -80億
        # -50億
        #
        # -100億會排第一名
        # ----------------------------------------------------

        sell_result = (
            df[
                [
                    "stock_id",
                    "stock_name",
                    "close_price",
                    column
                ]
            ]
            .loc[
                lambda x:
                    x[column] < 0
            ]
            .sort_values(
                column,
                ascending=True
            )
            .reset_index(
                drop=True
            )
            .head(100)
        )

        sell_result["rank"] = (
            sell_result.index + 1
        )

        # ----------------------------------------------------
        # 合併買超 + 賣超
        # ----------------------------------------------------

        result = pd.concat(
            [
                buy_result,
                sell_result
            ],
            ignore_index=True
        )

        return result

    # ========================================================
    # 四種排行榜
    # ========================================================

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

    # ========================================================
    # 建立 JSON
    # ========================================================

    result = {

        "data_date":
            data_date,

        "currency":
            "TWD",

        "unit":
            "TWD",

        "top_n":
            100,

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

    # ========================================================
    # 儲存 money_rank.json
    # ========================================================

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

    print()
    print(
        "✅ money_rank.json 已建立"
    )

    print(
        "外資資料：",
        len(foreign)
    )

    print(
        "投信資料：",
        len(investment_trust)
    )

    print(
        "自營商資料：",
        len(dealer)
    )

    print(
        "三大法人資料：",
        len(total)
    )
