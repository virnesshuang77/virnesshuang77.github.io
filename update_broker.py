import pandas as pd
import json
import os
from datetime import datetime


# ============================================================
# 設定
# ============================================================

INPUT_FILE = "broker_daily.csv"

OUTPUT_FILE = "broker_data.json"

TOP_N = 30


# ============================================================
# 開始
# ============================================================

print("=" * 70)
print("券商分點 TOP 30 資料處理")
print("=" * 70)


# ============================================================
# 1. 確認輸入檔案
# ============================================================

if not os.path.exists(INPUT_FILE):

    print()
    print("❌ 找不到：")
    print(INPUT_FILE)

    print()
    print("目前這個程式需要真正的券商分點交易資料。")

    print()
    print("預期 CSV 欄位：")

    print(
        "日期 / 股票代號 / 股票名稱 / "
        "券商代號 / 券商名稱 / 買進股數 / 賣出股數"
    )

    raise SystemExit(1)


# ============================================================
# 2. 讀取 CSV
# ============================================================

print()
print("正在讀取券商分點資料...")

df = pd.read_csv(
    INPUT_FILE,
    encoding="utf-8-sig"
)


print(
    f"資料筆數：{len(df):,}"
)


print()
print("原始欄位：")

print(
    df.columns.tolist()
)


# ============================================================
# 3. 欄位名稱自動辨識
# ============================================================

def find_column(
    candidates,
    columns
):

    for candidate in candidates:

        if candidate in columns:

            return candidate

    return None


date_column = find_column(

    [
        "日期",
        "date",
        "交易日期"
    ],

    df.columns

)


stock_id_column = find_column(

    [
        "股票代號",
        "證券代號",
        "stock_id",
        "stock"
    ],

    df.columns

)


stock_name_column = find_column(

    [
        "股票名稱",
        "證券名稱",
        "stock_name"
    ],

    df.columns

)


broker_id_column = find_column(

    [
        "券商代號",
        "證券商代號",
        "broker_id",
        "securities_trader_id"
    ],

    df.columns

)


broker_name_column = find_column(

    [
        "券商名稱",
        "證券商",
        "broker_name",
        "securities_trader"
    ],

    df.columns

)


buy_column = find_column(

    [
        "買進股數",
        "買進",
        "buy",
        "buy_volume"
    ],

    df.columns

)


sell_column = find_column(

    [
        "賣出股數",
        "賣出",
        "sell",
        "sell_volume"
    ],

    df.columns

)


# ============================================================
# 4. 檢查欄位
# ============================================================

required = {

    "日期": date_column,

    "股票代號": stock_id_column,

    "券商代號": broker_id_column,

    "券商名稱": broker_name_column,

    "買進": buy_column,

    "賣出": sell_column

}


print()
print("=" * 70)
print("欄位辨識")
print("=" * 70)


for name, column in required.items():

    print(
        f"{name:<10}",
        "→",
        column
        if column
        else "❌ 找不到"
    )


missing = [

    name

    for name, column
    in required.items()

    if column is None

]


if missing:

    print()

    print(
        "❌ 缺少必要欄位：",
        ", ".join(missing)
    )

    raise SystemExit(1)


# ============================================================
# 5. 標準化
# ============================================================

df["broker_id"] = (

    df[broker_id_column]

    .astype(str)

    .str.strip()

)


df["broker_name"] = (

    df[broker_name_column]

    .astype(str)

    .str.strip()

)


df["stock_id"] = (

    df[stock_id_column]

    .astype(str)

    .str.strip()

)


if stock_name_column:

    df["stock_name"] = (

        df[stock_name_column]

        .astype(str)

        .str.strip()

    )

else:

    df["stock_name"] = ""


df["buy"] = pd.to_numeric(

    df[buy_column],

    errors="coerce"

).fillna(0)


df["sell"] = pd.to_numeric(

    df[sell_column],

    errors="coerce"

).fillna(0)


# ============================================================
# 6. 日期
# ============================================================

if date_column:

    df["date"] = (

        df[date_column]

        .astype(str)

        .str.strip()

    )

else:

    df["date"] = datetime.now().strftime(
        "%Y-%m-%d"
    )


data_date = df["date"].iloc[0]


# ============================================================
# 7. 股票買賣資料 → 券商據點
# ============================================================

print()
print("=" * 70)
print("正在計算券商分點買賣超")
print("=" * 70)


broker_summary = (

    df

    .groupby(

        [
            "broker_id",
            "broker_name"
        ],

        as_index=False

    )

    .agg(

        buy_shares=(
            "buy",
            "sum"
        ),

        sell_shares=(
            "sell",
            "sum"
        )

    )

)


# ============================================================
# 8. 計算淨買超
# ============================================================

broker_summary["net_shares"] = (

    broker_summary["buy_shares"]

    -

    broker_summary["sell_shares"]

)


# ============================================================
# 9. 買超 TOP 30
# ============================================================

buy_top = (

    broker_summary

    .sort_values(

        "net_shares",

        ascending=False

    )

    .head(TOP_N)

    .reset_index(drop=True)

)


buy_top["rank"] = (
    buy_top.index + 1
)


# ============================================================
# 10. 賣超 TOP 30
# ============================================================

sell_top = (

    broker_summary

    .sort_values(

        "net_shares",

        ascending=True

    )

    .head(TOP_N)

    .reset_index(drop=True)

)


sell_top["rank"] = (
    sell_top.index + 1
)


# ============================================================
# 11. 轉成 JSON
# ============================================================

def make_records(data):

    records = []


    for _, row in data.iterrows():

        records.append({

            "rank":
                int(row["rank"]),

            "broker_id":
                row["broker_id"],

            "broker_name":
                row["broker_name"],

            "buy_shares":
                int(row["buy_shares"]),

            "sell_shares":
                int(row["sell_shares"]),

            "net_shares":
                int(row["net_shares"])

        })


    return records


buy_records = make_records(
    buy_top
)


sell_records = make_records(
    sell_top
)


# ============================================================
# 12. 建立 JSON
# ============================================================

output = {

    "data_date":
        data_date,

    "unit":
        "張",

    "description":
        "券商分點每日買賣超 TOP 30",

    "top_n":
        TOP_N,

    "buy_top30":
        buy_records,

    "sell_top30":
        sell_records

}


# ============================================================
# 13. 寫入
# ============================================================

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


# ============================================================
# 14. 顯示
# ============================================================

print()
print("=" * 70)

print(
    "【淨買超 TOP 30】"
)

print("=" * 70)


for row in buy_records[:10]:

    print(

        f'{row["rank"]:>2}. '

        f'{row["broker_name"]:<20} '

        f'{row["net_shares"]:>12,} 張'

    )


print()
print("=" * 70)

print(
    "【淨賣超 TOP 30】"
)

print("=" * 70)


for row in sell_records[:10]:

    print(

        f'{row["rank"]:>2}. '

        f'{row["broker_name"]:<20} '

        f'{row["net_shares"]:>12,} 張'

    )


print()
print("=" * 70)

print(
    "✅ broker_data.json 建立完成"
)

print("=" * 70)

print()
print(
    f"資料日期：{data_date}"
)

print(
    f"買超排行：{len(buy_records)} 個據點"
)

print(
    f"賣超排行：{len(sell_records)} 個據點"
)
