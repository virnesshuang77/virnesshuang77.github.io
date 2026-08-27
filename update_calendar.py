import requests
import json
from datetime import datetime
from pathlib import Path


# =========================================================
# 基本設定
# =========================================================

OUTPUT_FILE = Path("calendar-data.json")

API_URL = (
    "https://openapi.twse.com.tw/v1/"
    "opendata/t187ap05_L"
)


# =========================================================
# 追蹤公司
# =========================================================

COMPANIES = {

    "2330": {
        "name": "台積電",
        "flag": "🇹🇼"
    },

    "2408": {
        "name": "南亞科",
        "flag": "🇹🇼"
    },

    "6770": {
        "name": "力積電",
        "flag": "🇹🇼"
    },

    "2344": {
        "name": "華邦電",
        "flag": "🇹🇼"
    },

    "2454": {
        "name": "聯發科",
        "flag": "🇹🇼"
    },

    "3711": {
        "name": "日月光投控",
        "flag": "🇹🇼"
    }

}


# =========================================================
# 民國日期 → 西元日期
# =========================================================

def convert_roc_date(value):

    if value is None:
        return ""

    value = str(value).strip()

    if value == "":
        return ""

    # 民國年月日
    # 例如：
    # 1150817 → 2026-08-17

    if len(value) == 7 and value.isdigit():

        year = int(value[0:3]) + 1911
        month = int(value[3:5])
        day = int(value[5:7])

        return (
            f"{year:04d}-"
            f"{month:02d}-"
            f"{day:02d}"
        )


    # 民國年月
    # 例如：
    # 11507 → 2026-07

    if len(value) == 5 and value.isdigit():

        year = int(value[0:3]) + 1911
        month = int(value[3:5])

        return (
            f"{year:04d}-"
            f"{month:02d}"
        )


    return value


# =========================================================
# 數字轉換
# =========================================================

def convert_number(value):

    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    try:

        number = float(value)

        if number.is_integer():
            return int(number)

        return number

    except ValueError:

        return value


# =========================================================
# 取得 TWSE 月營收
# =========================================================

def get_twse_data():

    print()
    print("正在取得 TWSE 月營收資料...")

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        API_URL,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    print(
        f"取得 {len(data)} 筆資料"
    )

    return data


# =========================================================
# 找出 6 家公司
# =========================================================

def find_companies(data):

    result = {}

    for item in data:

        stock_id = str(
            item.get(
                "公司代號",
                ""
            )
        ).strip()


        if stock_id not in COMPANIES:
            continue


        company = COMPANIES[stock_id]


        data_date = convert_roc_date(
            item.get(
                "出表日期",
                ""
            )
        )


        month = convert_roc_date(
            item.get(
                "資料年月",
                ""
            )
        )


        result[stock_id] = {

            "stock_id": stock_id,

            "name": company["name"],

            "flag": company["flag"],

            "data_date": data_date,

            "month": month,

            "revenue": convert_number(
                item.get(
                    "營業收入-當月營收",
                    ""
                )
            ),

            "previous_revenue": convert_number(
                item.get(
                    "營業收入-上月營收",
                    ""
                )
            ),

            "last_year_revenue": convert_number(
                item.get(
                    "營業收入-去年當月營收",
                    ""
                )
            ),

            "mom": convert_number(
                item.get(
                    "營業收入-上月比較增減(%)",
                    ""
                )
            ),

            "yoy": convert_number(
                item.get(
                    "營業收入-去年同月增減(%)",
                    ""
                )
            )

        }


    return result


# =========================================================
# 產生 Calendar 的營收事件
# =========================================================

def build_revenue_events(companies):

    events = []


    for stock_id, company in companies.items():

        date = company["data_date"]

        month = company["month"]


        if date == "":
            continue


        # -------------------------------------------------
        # 取得月份文字
        # 例如：
        # 2026-07 → 7月
        # -------------------------------------------------

        month_text = ""

        if len(month) == 7:

            month_number = int(
                month[5:7]
            )

            month_text = (
                f"{month_number}月"
            )


        # -------------------------------------------------
        # 標題
        # -------------------------------------------------

        title = (
            f'{company["flag"]} '
            f'{company["name"]} '
            f'{month_text}營收'
        )


        # -------------------------------------------------
        # 說明文字
        # -------------------------------------------------

        description_parts = []


        if company["revenue"] is not None:

            description_parts.append(
                f'營收：{company["revenue"]}'
            )


        if company["mom"] is not None:

            description_parts.append(
                f'月增：{company["mom"]}%'
            )


        if company["yoy"] is not None:

            description_parts.append(
                f'年增：{company["yoy"]}%'
            )


        description = "　".join(
            description_parts
        )


        # -------------------------------------------------
        # Calendar event
        # -------------------------------------------------

        event = {

            "date": date,

            "time": "依公告",

            "country": "TW",

            "type": "revenue",

            "stock_id": stock_id,

            "title": title,

            "importance": "high",

            "month": month,

            "revenue": company["revenue"],

            "mom": company["mom"],

            "yoy": company["yoy"],

            "description": description

        }


        events.append(event)


    # 日期排序
    events.sort(
        key=lambda event: (
            event["date"],
            event["stock_id"]
        )
    )


    return events


# =========================================================
# 建立 JSON
# =========================================================

def build_json(companies, events):

    return {

        "updated_at":
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

        "source":
            "TWSE OpenAPI / t187ap05_L",

        "tracked_companies":
            list(COMPANIES.keys()),

        "companies":
            companies,

        "revenue_events":
            events

    }


# =========================================================
# 儲存 JSON
# =========================================================

def save_json(data):

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=4
        )


    print()
    print(
        f"已產生：{OUTPUT_FILE}"
    )


# =========================================================
# 顯示結果
# =========================================================

def show_result(data):

    print()
    print("=" * 70)
    print("最新月營收")
    print("=" * 70)


    for stock_id in COMPANIES:

        company = data["companies"].get(
            stock_id
        )


        if company is None:

            print()
            print(
                f'{stock_id} '
                f'{COMPANIES[stock_id]["name"]}：'
                f'找不到資料'
            )

            continue


        print()
        print(
            f'{company["flag"]} '
            f'{stock_id} '
            f'{company["name"]}'
        )

        print(
            f'資料月份：'
            f'{company["month"]}'
        )

        print(
            f'出表日期：'
            f'{company["data_date"]}'
        )

        print(
            f'當月營收：'
            f'{company["revenue"]}'
        )

        print(
            f'月增率：'
            f'{company["mom"]}%'
        )

        print(
            f'年增率：'
            f'{company["yoy"]}%'
        )


    print()
    print("=" * 70)
    print("Calendar 營收事件")
    print("=" * 70)


    for event in data["revenue_events"]:

        print(
            f'{event["date"]}  '
            f'{event["title"]}'
        )


    print()
    print("=" * 70)


# =========================================================
# 主程式
# =========================================================

def main():

    try:

        # 1. 取得 TWSE
        raw_data = get_twse_data()


        # 2. 找 6 家公司
        companies = find_companies(
            raw_data
        )


        if not companies:

            print()
            print(
                "找不到指定公司的資料。"
            )

            return


        # 3. 產生營收事件
        events = build_revenue_events(
            companies
        )


        # 4. 建立 JSON
        output = build_json(
            companies,
            events
        )


        # 5. 儲存 JSON
        save_json(
            output
        )


        # 6. 顯示結果
        show_result(
            output
        )


    except requests.RequestException as error:

        print()
        print(
            "TWSE API 連線失敗："
        )

        print(error)


    except Exception as error:

        print()
        print(
            "程式執行錯誤："
        )

        print(error)


# =========================================================
# 執行
# =========================================================

if __name__ == "__main__":

    main()
