import requests
import json
from datetime import datetime


# =====================================================
# 設定
# =====================================================

OUTPUT_FILE = "calendar-data.json"


TRACK_COMPANIES = {
    "2330": "台積電",
    "2408": "南亞科",
    "6770": "力積電",
    "2344": "華邦電",
    "2454": "聯發科",
    "3711": "日月光投控"
}


FLAGS = {
    "2330":"🇹🇼",
    "2408":"🇹🇼",
    "6770":"🇹🇼",
    "2344":"🇹🇼",
    "2454":"🇹🇼",
    "3711":"🇹🇼"
}



# =====================================================
# TWSE 月營收
# =====================================================

def get_revenue():

    print("正在取得 TWSE 月營收資料...")


    url = (
        "https://openapi.twse.com.tw/v1/opendata/"
        "t187ap05_L"
    )


    r = requests.get(url, timeout=20)

    data = r.json()


    print(
        f"取得 {len(data)} 筆資料"
    )


    result = {}


    for row in data:

        stock_id = row.get(
            "公司代號"
        )


        if stock_id not in TRACK_COMPANIES:
            continue



        result[stock_id] = {

            "stock_id":
                stock_id,

            "name":
                TRACK_COMPANIES[stock_id],

            "flag":
                FLAGS[stock_id],

            "data_date":
                row.get("資料日期",""),

            "month":
                row.get("資料年月",""),

            "revenue":
                int(
                    row.get(
                        "營業收入-當月營收",
                        0
                    )
                ),

            "previous_revenue":
                int(
                    row.get(
                        "營業收入-上月營收",
                        0
                    )
                ),

            "last_year_revenue":
                int(
                    row.get(
                        "營業收入-去年同月營收",
                        0
                    )
                ),

            "mom":
                float(
                    row.get(
                        "營業收入-上月比較增減(%)",
                        0
                    )
                ),

            "yoy":
                float(
                    row.get(
                        "營業收入-去年同月增減(%)",
                        0
                    )
                )
        }



    return result




# =====================================================
# 財報行事曆
# =====================================================

def earnings_schedule():


    return [

        {
            "date":"2026-08-27",
            "time":"美股盤後",
            "country":"US",
            "type":"earnings",
            "symbol":"NVDA",
            "title":"🇺🇸 NVIDIA 輝達 財報",
            "importance":"high",

            "forecast_revenue":46.5,
            "actual_revenue":None,

            "forecast_eps":1.01,
            "actual_eps":None,

            "guidance_revenue":None,
            "guidance_forecast_revenue":None,

            "description":
            "NVIDIA 輝達 財報公布"
        },


        {
            "date":"2026-09-30",
            "time":"美股盤後",
            "country":"US",
            "type":"earnings",
            "symbol":"MU",
            "title":"🇺🇸 Micron 美光 財報",
            "importance":"high",

            "forecast_revenue":None,
            "actual_revenue":None,

            "forecast_eps":None,
            "actual_eps":None,

            "description":
            "Micron 美光 財報公布"
        },


        {
            "date":"2026-10-15",
            "time":"依公司公告",
            "country":"TW",
            "type":"earnings",
            "symbol":"2330",
            "title":"🇹🇼 台積電 財報",
            "importance":"high",

            "forecast_revenue":None,
            "actual_revenue":None,

            "forecast_eps":None,
            "actual_eps":None,

            "description":
            "台積電 財報公布"
        },


        {
            "date":"2026-11-03",
            "time":"美股盤後",
            "country":"US",
            "type":"earnings",
            "symbol":"AMD",
            "title":"🇺🇸 AMD 超微 財報",
            "importance":"high",

            "forecast_revenue":None,
            "actual_revenue":None,

            "forecast_eps":None,
            "actual_eps":None,

            "description":
            "AMD 超微 財報公布"
        }

    ]




# =====================================================
# 產生營收事件
# =====================================================

def make_revenue_events(companies):


    events=[]


    for stock,data in companies.items():


        events.append({

            "date":
                data["data_date"],

            "time":
                "依公告",

            "country":
                "TW",

            "type":
                "revenue",

            "stock_id":
                stock,

            "title":
                f'{data["flag"]} {data["name"]} {data["month"][-2:]}月營收',

            "importance":
                "high",

            "month":
                data["month"],

            "revenue":
                data["revenue"],

            "mom":
                data["mom"],

            "yoy":
                data["yoy"],

            "description":
                (
                f'營收：{data["revenue"]} '
                f'月增：{data["mom"]}% '
                f'年增：{data["yoy"]}%'
                )
        })


    return events




# =====================================================
# 主程式
# =====================================================

def main():


    companies = get_revenue()


    data = {


        "updated_at":
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),


        "source":
            "TWSE OpenAPI + Earnings Schedule",


        "companies":
            companies,


        "revenue_events":
            make_revenue_events(
                companies
            ),


        "earnings_events":
            earnings_schedule()

    }



    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:


        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4
        )


    print()
    print(
        "已產生:",
        OUTPUT_FILE
    )



    print()
    print("="*60)
    print("財報事件")
    print("="*60)


    for e in data["earnings_events"]:

        print(
            e["date"],
            e["title"]
        )




if __name__=="__main__":

    main()
