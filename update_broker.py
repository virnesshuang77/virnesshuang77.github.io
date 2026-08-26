import os
import zipfile
import json
import glob
import pandas as pd
from datetime import datetime


# ============================================================
# 設定
# ============================================================

TOP_N = 30

OUTPUT_FILE = "broker_data.json"

# 可以放 ZIP / CSV / TXT
INPUT_PATTERNS = [
    "*.zip",
    "*.csv",
    "*.txt"
]


# ============================================================
# 工具：找檔案
# ============================================================

def find_input_file():

    files = []

    for pattern in INPUT_PATTERNS:

        files.extend(
            glob.glob(pattern)
        )

    # 排除輸出檔
    files = [
        f
        for f in files
        if os.path.basename(f)
        != OUTPUT_FILE
    ]

    if not files:
        return None

    # 優先 ZIP
    zip_files = [
        f
        for f in files
        if f.lower().endswith(".zip")
    ]

    if zip_files:
        return zip_files[0]

    return files[0]


# ============================================================
# 讀取 ZIP
# ============================================================

def read_zip_file(path):

    print()
    print("=" * 70)
    print("讀取 ZIP")
    print("=" * 70)

    print(
        "檔案：",
        path
    )

    with zipfile.ZipFile(
        path,
        "r"
    ) as z:

        names = z.namelist()

        print()
        print("ZIP 內容：")

        for name in names:

            print(
                " ",
                name
            )

        # 找第一個 CSV / TXT
        target = None

        for name in names:

            lower = name.lower()

            if (
                lower.endswith(".csv")
                or
                lower.endswith(".txt")
            ):

                target = name

                break

        if target is None:

            raise Exception(
                "ZIP 裡找不到 CSV 或 TXT"
            )

        print()
        print(
            "使用檔案：",
            target
        )

        raw = z.read(target)

        # 嘗試常見編碼
        for encoding in [
            "utf-8-sig",
            "big5",
            "cp950",
            "utf-8"
        ]:

            try:

                text = raw.decode(
                    encoding
                )

                print(
                    "編碼：",
                    encoding
                )

                from io import StringIO

                return pd.read_csv(
                    StringIO(text)
                )

            except Exception:
                continue

    raise Exception(
        "無法解析 ZIP 裡的資料"
    )


# ============================================================
# 讀取一般檔案
# ============================================================

def read_normal_file(path):

    print()
    print("=" * 70)
    print("讀取資料檔")
    print("=" * 70)

    print(
        "檔案：",
        path
    )

    for encoding in [
        "utf-8-sig",
        "big5",
        "cp950",
        "utf-8"
    ]:

        try:

            df = pd.read_csv(
                path,
                encoding=encoding
            )

            print(
                "編碼：",
                encoding
            )

            return df

        except Exception:
            continue

    raise Exception(
        "無法讀取資料檔案"
    )


# ============================================================
# 找欄位
# ============================================================

def find_column(
    columns,
    candidates
):

    for candidate in candidates:

        if candidate in columns:

            return candidate

    return None


# ============================================================
# 開始
# ============================================================

print("=" * 70)

print(
    "券商分點每日 TOP 30 產生器"
)

print("=" * 70)


# ============================================================
# 找輸入檔
# ============================================================

input_file = find_input_file()


if input_file is None:

    print()

    print(
        "❌ 找不到每日券商分點原始資料"
    )

    print()

    print(
        "請將官方 ZIP / CSV / TXT "
        "放在這個 Python 同一個資料夾。"
    )

    print()

    print(
        "程式不會自行產生假資料。"
    )

    raise SystemExit(1)


# ============================================================
# 讀取
# ============================================================

if input_file.lower().endswith(".zip"):

    df = read_zip_file(
        input_file
    )

else:

    df = read_normal_file(
        input_file
    )


# ============================================================
# 顯示欄位
# ============================================================

print()
print("=" * 70)

print(
    "原始資料欄位"
)

print("=" * 70)

print(
    df.columns.tolist()
)


# ============================================================
# 自動尋找欄位
# ============================================================

stock_id_column = find_column(

    df.columns,

    [
        "證券代號",
        "股票代號",
        "stock_id"
    ]

)


broker_column = find_column(

    df.columns,

    [
        "證券商",
        "券商名稱",
        "證券商名稱",
        "broker_name"
    ]

)


price_column = find_column(

    df.columns,

    [
        "成交單價",
        "成交價",
        "price"
    ]

)


buy_column = find_column(

    df.columns,

    [
        "買進股數",
        "買進",
        "buy"
    ]

)


sell_column = find_column(

    df.columns,

    [
        "賣出股數",
        "賣出",
        "sell"
    ]

)


# ============================================================
# 檢查
# ============================================================

required = {

    "證券代號":
        stock_id_column,

    "證券商":
        broker_column,

    "成交單價":
        price_column,

    "買進股數":
        buy_column,

    "賣出股數":
        sell_column

}


print()
print("=" * 70)

print(
    "欄位辨識結果"
)

print("=" * 70)


for name, column in required.items():

    print(

        f"{name:<10}"
        f" → "
        f"{column if column else '❌ 找不到'}"

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
        "❌ 缺少必要欄位："
    )

    print(
        ", ".join(missing)
    )

    print()

    print(
        "請把原始資料欄位名稱貼給我，"
        "我可以再對應。"
    )

    raise SystemExit(1)


# ============================================================
# 清理
# ============================================================

df["broker_name"] = (

    df[broker_column]

    .astype(str)

    .str.strip()

)


df["stock_id"] = (

    df[stock_id_column]

    .astype(str)

    .str.strip()

)


df["price"] = pd.to_numeric(

    df[price_column],

    errors="coerce"

).fillna(0)


df["buy_shares"] = pd.to_numeric(

    df[buy_column],

    errors="coerce"

).fillna(0)


df["sell_shares"] = pd.to_numeric(

    df[sell_column],

    errors="coerce"

).fillna(0)


# ============================================================
# 刪除無效資料
# ============================================================

df = df[
    df["broker_name"].notna()
]


df = df[
    df["broker_name"]
    != ""
]


# ============================================================
# 計算交易金額
# ============================================================

df["buy_value"] = (

    df["price"]

    *

    df["buy_shares"]

)


df["sell_value"] = (

    df["price"]

    *

    df["sell_shares"]

)


# ============================================================
# 券商據點彙總
# ============================================================

print()
print("=" * 70)

print(
    "正在計算券商據點..."
)

print("=" * 70)


broker_summary = (

    df

    .groupby(
        "broker_name",
        as_index=False
    )

    .agg(

        buy_shares=(
            "buy_shares",
            "sum"
        ),

        sell_shares=(
            "sell_shares",
            "sum"
        ),

        buy_value=(
            "buy_value",
            "sum"
        ),

        sell_value=(
            "sell_value",
            "sum"
        )

    )

)


# ============================================================
# 淨買賣
# ============================================================

broker_summary["net_shares"] = (

    broker_summary["buy_shares"]

    -

    broker_summary["sell_shares"]

)


broker_summary["net_value"] = (

    broker_summary["buy_value"]

    -

    broker_summary["sell_value"]

)


# ============================================================
# 買超 TOP 30
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

    buy_top.index

    +

    1

)


# ============================================================
# 賣超 TOP 30
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

    sell_top.index

    +

    1

)


# ============================================================
# 轉 JSON
# ============================================================

def convert_records(data):

    records = []

    for _, row in data.iterrows():

        records.append({

            "rank":
                int(row["rank"]),

            "broker_name":
                row["broker_name"],

            "buy_shares":
                int(
                    row["buy_shares"]
                ),

            "sell_shares":
                int(
                    row["sell_shares"]
                ),

            "net_shares":
                int(
                    row["net_shares"]
                ),

            "buy_value":
                float(
                    row["buy_value"]
                ),

            "sell_value":
                float(
                    row["sell_value"]
                ),

            "net_value":
                float(
                    row["net_value"]
                )

        })

    return records


buy_records = convert_records(
    buy_top
)


sell_records = convert_records(
    sell_top
)


# ============================================================
# 日期
# ============================================================

data_date = (
    datetime.now()
    .strftime("%Y-%m-%d")
)


# ============================================================
# 建立 JSON
# ============================================================

result = {

    "data_date":
        data_date,

    "unit":
        "張",

    "source":
        "TWSE broker transaction data",

    "description":
        "每日券商分點淨買賣超 TOP 30",

    "top_n":
        TOP_N,

    "buy_top30":
        buy_records,

    "sell_top30":
        sell_records

}


# ============================================================
# 寫入
# ============================================================

with open(

    OUTPUT_FILE,

    "w",

    encoding="utf-8"

) as f:

    json.dump(

        result,

        f,

        ensure_ascii=False,

        indent=2

    )


# ============================================================
# 顯示結果
# ============================================================

print()
print("=" * 70)

print(
    "【淨買超 TOP 30】"
)

print("=" * 70)


for row in buy_records:

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


for row in sell_records:

    print(

        f'{row["rank"]:>2}. '

        f'{row["broker_name"]:<20} '

        f'{row["net_shares"]:>12,} 張'

    )


print()
print("=" * 70)

print(
    "✅ broker_data.json 已建立"
)

print("=" * 70)

print()

print(
    f"買超：{len(buy_records)} 個據點"
)

print(
    f"賣超：{len(sell_records)} 個據點"
)
