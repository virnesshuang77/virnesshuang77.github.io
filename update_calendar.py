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
# 台灣月營收追蹤公司
# =========================================================

COMPANIES = {
    "2330": {"name": "台積電", "flag": "🇹🇼"},
    "2408": {"name": "南亞科", "flag": "🇹🇼"},
    "6770": {"name": "力積電", "flag": "🇹🇼"},
    "2344": {"name": "華邦電", "flag": "🇹🇼"},
    "2454": {"name": "聯發科", "flag": "🇹🇼"},
    "3711": {"name": "日月光投控", "flag": "🇹🇼"}
}


# =========================================================
# 重要財報日期與財報資料
#
# 日期統一使用「台灣日期」。
#
# 已公布的財報可以填：
#   forecast_revenue / actual_revenue
#   forecast_eps / actual_eps
#   guidance_revenue / guidance_forecast_revenue
#
# 尚未公布的公司：
#   actual_* 保持 None
# =========================================================

EARNINGS_SCHEDULE = [

    # -----------------------------------------------------
    # 2026 / 08
    # -----------------------------------------------------

    {
        "date": "2026-08-27",
        "country": "US",
        "flag": "🇺🇸",
        "symbol": "NVDA",
        "name": "NVIDIA 輝達",
        "time": "美股盤後",

        "forecast_revenue": 92.27,
        "actual_revenue": 96.22,

        "forecast_eps": 2.09,
        "actual_eps": 2.22,

        "guidance_revenue": 108.00,
        "guidance_forecast_revenue": 104.86,

        "description": (
            "Q2 FY2027 財報公布，營收與 Non-GAAP EPS "
            "均高於市場預期；公司 Q3 營收指引為 "
            "$108B ±2%。"
        )
    },


    # -----------------------------------------------------
    # 2026 / 09
    # -----------------------------------------------------

    {
        "date": "2026-09-30",
        "country": "US",
        "flag": "🇺🇸",
        "symbol": "MU",
        "name": "Micron 美光",
        "time": "美股盤後",

        "forecast_revenue": None,
        "actual_revenue": None,

        "forecast_eps": None,
        "actual_eps": None,

        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "Micron 財報預定公布。"
    },


    # -----------------------------------------------------
    # 2026 / 10
    # -----------------------------------------------------

    {
        "date": "2026-10-14",
        "country": "TW",
        "flag": "🇹🇼",
        "symbol": "2408",
        "name": "南亞科",
        "time": "依公司公告",

        "forecast_revenue": None,
        "actual_revenue": None,
        "forecast_eps": None,
        "actual_eps": None,
        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "南亞科財報預定公布。"
    },

    {
        "date": "2026-10-15",
        "country": "TW",
        "flag": "🇹🇼",
        "symbol": "6770",
        "name": "力積電",
        "time": "依公司公告",

        "forecast_revenue": None,
        "actual_revenue": None,
        "forecast_eps": None,
        "actual_eps": None,
        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "力積電財報預定公布。"
    },

    {
        "date": "2026-10-15",
        "country": "TW",
        "flag": "🇹🇼",
        "symbol": "2330",
        "name": "台積電",
        "time": "依公司公告",

        "forecast_revenue": None,
        "actual_revenue": None,
        "forecast_eps": None,
        "actual_eps": None,
        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "台積電財報預定公布。"
    },

    {
        "date": "2026-10-21",
        "country": "US",
        "flag": "🇺🇸",
        "symbol": "TSLA",
        "name": "Tesla 特斯拉",
        "time": "美股盤後",

        "forecast_revenue": None,
        "actual_revenue": None,
        "forecast_eps": None,
        "actual_eps": None,
        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "Tesla 財報預定公布。"
    },

    {
        "date": "2026-10-22",
        "country": "TW",
        "flag": "🇹🇼",
        "symbol": "3711",
        "name": "日月光投控",
        "time": "依公司公告",

        "forecast_revenue": None,
        "actual_revenue": None,
        "forecast_eps": None,
        "actual_eps": None,
        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "日月光投控財報預定公布。"
    },

    {
        "date": "2026-10-27",
        "country": "KR",
        "flag": "🇰🇷",
        "symbol": "000660",
        "name": "SK 海力士",
        "time": "依公司公告",

        "forecast_revenue": None,
        "actual_revenue": None,
        "forecast_eps": None,
        "actual_eps": None,
        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "SK 海力士財報預定公布。"
    },

    {
        "date": "2026-10-28",
        "country": "US",
        "flag": "🇺🇸",
        "symbol": "META",
        "name": "Meta",
        "time": "美股盤後",

        "forecast_revenue": None,
        "actual_revenue": None,
        "forecast_eps": None,
        "actual_eps": None,
        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "Meta 財報預定公布。"
    },

    {
        "date": "2026-10-28",
        "country": "US",
        "flag": "🇺🇸",
        "symbol": "MSFT",
        "name": "Microsoft 微軟",
        "time": "美股盤後",

        "forecast_revenue": None,
        "actual_revenue": None,
        "forecast_eps": None,
        "actual_eps": None,
        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "Microsoft 財報預定公布。"
    },

    {
        "date": "2026-10-29",
        "country": "KR",
        "flag": "🇰🇷",
        "symbol": "005930",
        "name": "三星電子",
        "time": "依公司公告",

        "forecast_revenue": None,
        "actual_revenue": None,
        "forecast_eps": None,
        "actual_eps": None,
        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "三星電子財報預定公布。"
    },

    {
        "date": "2026-10-29",
        "country": "TW",
        "flag": "🇹🇼",
        "symbol": "2344",
        "name": "華邦電",
        "time": "依公司公告",

        "forecast_revenue": None,
        "actual_revenue": None,
        "forecast_eps": None,
        "actual_eps": None,
        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "華邦電財報預定公布。"
    },

    {
        "date": "2026-10-29",
        "country": "US",
        "flag": "🇺🇸",
        "symbol": "AAPL",
        "name": "Apple 蘋果",
        "time": "美股盤後",

        "forecast_revenue": None,
        "actual_revenue": None,
        "forecast_eps": None,
        "actual_eps": None,
        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "Apple 財報預定公布。"
    },

    {
        "date": "2026-10-29",
        "country": "US",
        "flag": "🇺🇸",
        "symbol": "AMZN",
        "name": "Amazon 亞馬遜",
        "time": "美股盤後",

        "forecast_revenue": None,
        "actual_revenue": None,
        "forecast_eps": None,
        "actual_eps": None,
        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "Amazon 財報預定公布。"
    },


    # -----------------------------------------------------
    # 2026 / 11
    # -----------------------------------------------------

    {
        "date": "2026-11-03",
        "country": "US",
        "flag": "🇺🇸",
        "symbol": "AMD",
        "name": "AMD 超微",
        "time": "美股盤後",

        "forecast_revenue": None,
        "actual_revenue": None,
        "forecast_eps": None,
        "actual_eps": None,
        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "AMD 財報預定公布。"
    },

    {
        "date": "2026-11-04",
        "country": "US",
        "flag": "🇺🇸",
        "symbol": "SNDK",
        "name": "SanDisk 閃迪",
        "time": "美股盤後",

        "forecast_revenue": None,
        "actual_revenue": None,
        "forecast_eps": None,
        "actual_eps": None,
        "guidance_revenue": None,
        "guidance_forecast_revenue": None,

        "description": "SanDisk 財報預定公布。"
    }

]


# =========================================================
# 日期轉換
# =========================================================

def convert_roc_date(value):

    if value is None:
        return ""

    value = str(value).strip()

    if not value:
        return ""

    if len(value) == 7 and value.isdigit():

        year = int(value[0:3]) + 1911
        month = int(value[3:5])
        day = int(value[5:7])

        return f"{year:04d}-{month:02d}-{day:02d}"

    if len(value) == 5 and value.isdigit():

        year = int(value[0:3]) + 1911
        month = int(value[3:5])

        return f"{year:04d}-{month:02d}"

    return value


# =========================================================
# 數字轉換
# =========================================================

def convert_number(value):

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    try:

        number = float(value)

        if number.is_integer():
            return int(number)

        return number

    except ValueError:

        return value


# =========================================================
# TWSE 月營收
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

    print(f"取得 {len(data)} 筆資料")

    return data


# =========================================================
# 找出指定公司
# =========================================================

def find_companies(data):

    result = {}

    for item in data:

        stock_id = str(
            item.get("公司代號", "")
        ).strip()

        if stock_id not in COMPANIES:
            continue

        company = COMPANIES[stock_id]

        result[stock_id] = {

            "stock_id": stock_id,
            "name": company["name"],
            "flag": company["flag"],

            "data_date":
                convert_roc_date(
                    item.get("出表日期", "")
                ),

            "month":
                convert_roc_date(
                    item.get("資料年月", "")
                ),

            "revenue":
                convert_number(
                    item.get(
                        "營業收入-當月營收",
                        ""
                    )
                ),

            "mom":
                convert_number(
                    item.get(
                        "營業收入-上月比較增減(%)",
                        ""
                    )
                ),

            "yoy":
                convert_number(
                    item.get(
                        "營業收入-去年同月增減(%)",
                        ""
                    )
                )
        }

    return result


# =========================================================
# 建立營收事件
# =========================================================

def build_revenue_events(companies):

    events = []

    for stock_id, company in companies.items():

        date = company["data_date"]

        if not date:
            continue

        month = company["month"]

        month_text = ""

        if len(month) == 7:

            month_number = int(
                month[5:7]
            )

            month_text = f"{month_number}月"

        title = (
            f'{company["flag"]} '
            f'{company["name"]} '
            f'{month_text}營收'
        )

        parts = []

        if company["revenue"] is not None:
            parts.append(
                f'營收：{company["revenue"]}'
            )

        if company["mom"] is not None:
            parts.append(
                f'月增：{company["mom"]}%'
            )

        if company["yoy"] is not None:
            parts.append(
                f'年增：{company["yoy"]}%'
            )

        events.append({

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

            "description":
                "　".join(parts)
        })

    events.sort(
        key=lambda event: (
            event["date"],
            event["stock_id"]
        )
    )

    return events


# =========================================================
# 計算財報 Beat / Miss
# =========================================================

def calculate_earnings_result(item):

    forecast_revenue = item.get(
        "forecast_revenue"
    )

    actual_revenue = item.get(
        "actual_revenue"
    )

    forecast_eps = item.get(
        "forecast_eps"
    )

    actual_eps = item.get(
        "actual_eps"
    )

    revenue_status = None
    revenue_difference = None

    eps_status = None
    eps_difference = None


    if (
        forecast_revenue is not None
        and actual_revenue is not None
    ):

        revenue_difference = round(
            actual_revenue - forecast_revenue,
            2
        )

        revenue_status = (
            "beat"
            if revenue_difference > 0
            else
            "miss"
            if revenue_difference < 0
            else
            "inline"
        )


    if (
        forecast_eps is not None
        and actual_eps is not None
    ):

        eps_difference = round(
            actual_eps - forecast_eps,
            2
        )

        eps_status = (
            "beat"
            if eps_difference > 0
            else
            "miss"
            if eps_difference < 0
            else
            "inline"
        )


    return {

        "revenue_status":
            revenue_status,

        "revenue_difference":
            revenue_difference,

        "eps_status":
            eps_status,

        "eps_difference":
            eps_difference
    }


# =========================================================
# 建立財報事件
# =========================================================

def build_earnings_events():

    events = []

    for item in EARNINGS_SCHEDULE:

        result = calculate_earnings_result(
            item
        )

        events.append({

            "date": item["date"],

            "time": item["time"],

            "country": item["country"],

            "type": "earnings",

            "symbol": item["symbol"],

            "title":
                f'{item["flag"]} '
                f'{item["name"]} 財報',

            "importance": "high",

            "description":
                item["description"],

            "forecast_revenue":
                item["forecast_revenue"],

            "actual_revenue":
                item["actual_revenue"],

            "forecast_eps":
                item["forecast_eps"],

            "actual_eps":
                item["actual_eps"],

            "guidance_revenue":
                item["guidance_revenue"],

            "guidance_forecast_revenue":
                item["guidance_forecast_revenue"],

            "revenue_status":
                result["revenue_status"],

            "revenue_difference":
                result["revenue_difference"],

            "eps_status":
                result["eps_status"],

            "eps_difference":
                result["eps_difference"]
        })

    events.sort(
        key=lambda event: (
            event["date"],
            event["symbol"]
        )
    )

    return events


# =========================================================
# 建立 JSON
# =========================================================

def build_json(
    companies,
    revenue_events,
    earnings_events
):

    return {

        "updated_at":
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

        "source":
            "TWSE OpenAPI + Earnings Schedule",

        "tracked_companies":
            list(COMPANIES.keys()),

        "companies":
            companies,

        "revenue_events":
            revenue_events,

        "earnings_events":
            earnings_events
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
    print(f"已產生：{OUTPUT_FILE}")


# =========================================================
# 顯示結果
# =========================================================

def show_result(data):

    print()
    print("=" * 70)
    print("台灣月營收")
    print("=" * 70)

    for stock_id in COMPANIES:

        company = data[
            "companies"
        ].get(stock_id)

        if company is None:

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
            f'資料月份：{company["month"]}'
        )

        print(
            f'出表日期：{company["data_date"]}'
        )

        print(
            f'當月營收：{company["revenue"]}'
        )

        print(
            f'月增率：{company["mom"]}%'
        )

        print(
            f'年增率：{company["yoy"]}%'
        )


    print()
    print("=" * 70)
    print("Calendar 營收事件")
    print("=" * 70)

    for event in data[
        "revenue_events"
    ]:

        print(
            f'{event["date"]}  '
            f'{event["title"]}'
        )


    print()
    print("=" * 70)
    print("Calendar 財報事件")
    print("=" * 70)

    for event in data[
        "earnings_events"
    ]:

        print(
            f'{event["date"]}  '
            f'{event["title"]}  '
            f'{event["time"]}'
        )

        if event["actual_revenue"] is not None:

            print(
                f'  營收：預期 '
                f'${event["forecast_revenue"]:.2f}B'
                f' → 公布 '
                f'${event["actual_revenue"]:.2f}B'
            )

        if event["actual_eps"] is not None:

            print(
                f'  EPS：預期 '
                f'${event["forecast_eps"]:.2f}'
                f' → 公布 '
                f'${event["actual_eps"]:.2f}'
            )

        if event["guidance_revenue"] is not None:

            print(
                f'  Q3 指引：'
                f'${event["guidance_revenue"]:.2f}B'
                f' / 市場預期 '
                f'${event["guidance_forecast_revenue"]:.2f}B'
            )


    print()
    print("=" * 70)


# =========================================================
# 主程式
# =========================================================

def main():

    try:

        raw_data = get_twse_data()

        companies = find_companies(
            raw_data
        )

        if not companies:

            print(
                "找不到指定公司的資料。"
            )

            return

        revenue_events = (
            build_revenue_events(
                companies
            )
        )

        earnings_events = (
            build_earnings_events()
        )

        output = build_json(
            companies,
            revenue_events,
            earnings_events
        )

        save_json(output)

        show_result(output)


    except requests.RequestException as error:

        print()
        print("TWSE API 連線失敗：")
        print(error)


    except Exception as error:

        print()
        print("程式執行錯誤：")
        print(error)


if __name__ == "__main__":
    main()
