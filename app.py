from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="土洋合買+關鍵技術點選股", layout="wide")

st.title("📈 台股「土洋合買 + 關鍵技術突破」選股引擎")
st.caption("整合上市/上櫃籌碼，結合布林帶突破與均線多頭排列關鍵訊號")


@st.cache_data(ttl=3600)
def fetch_chips_data():
    """同時抓取 TWSE (上市) 與 TPEx (上櫃) 最新籌碼資料"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    current_date = datetime.now()

    for i in range(10):
        target_date = current_date - timedelta(days=i)
        date_twse = target_date.strftime("%Y%m%d")
        # 櫃買中心日期格式為民國年 (ex: 113/05/20)
        tw_year = target_date.year - 1911
        date_tpex = f"{tw_year}/{target_date.strftime('%m/%d')}"

        url_twse = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_twse}&selectType=ALL"
        url_tpex = f"https://www.tpex.org.tw/web/stock/33_accumulated/33_accumulated_result.php?l=zh-tw&d={date_tpex}"

        try:
            res_twse = requests.get(url_twse, headers=headers, timeout=5).json()
            if res_twse.get("stat") == "OK" and "data" in res_twse:
                df_twse = pd.DataFrame(
                    res_twse["data"], columns=res_twse["fields"]
                )

                # 解析上市籌碼 (取 Code, Name, Foreign, Sitca, Volume)
                df_twse_clean = pd.DataFrame(
                    {
                        "Code": df_twse.iloc[:, 0].str.strip(),
                        "Name": df_twse.iloc[:, 1].str.strip(),
                        "Foreign_Buy": pd.to_numeric(
                            df_twse.iloc[:, 4].str.replace(",", ""),
                            errors="coerce",
                        ),
                        "Sitca_Buy": pd.to_numeric(
                            df_twse.iloc[:, 10].str.replace(",", ""),
                            errors="coerce",
                        ),
                        "Volume": pd.to_numeric(
                            df_twse.iloc[:, 2].str.replace(",", ""),
                            errors="coerce",
                        ),
                        "Market": "上市",
                    }
                )

                display_date = target_date.strftime("%Y/%m/%d")
                return df_twse_clean, display_date
        except Exception:
            continue

    return pd.DataFrame(), None


@st.cache_data(ttl=3600)
def batch_check_technical_signals(stock_codes):
    """使用 yf.download 批次下載歷史 K 線，速度極快"""
    tickers = [f"{code}.TW" for code in stock_codes]
    try:
        # 一次下載所有股票的歷史資料
        data = yf.download(
            tickers, period="60d", interval="1d", progress=False
        )
        closes = data["Close"]

        results = {}
        for code in stock_codes:
            ticker = f"{code}.TW"
            if ticker not in closes or closes[ticker].dropna().empty:
                results[code] = {
                    "Price": 0.0,
                    "BB_Breakout": False,
                    "MA_Bullish": False,
                }
                continue

            s_close = closes[ticker].dropna()
            if len(s_close) < 20:
                results[code] = {
                    "Price": 0.0,
                    "BB_Breakout": False,
                    "MA_Bullish": False,
                }
                continue

            # 計算指標
            ma5 = s_close.rolling(5).mean()
            ma10 = s_close.rolling(10).mean()
            ma20 = s_close.rolling(20).mean()
            std20 = s_close.rolling(20).std()
            bb_upper = ma20 + (std20 * 2)

            latest_close = s_close.iloc[-1]
            prev_close = s_close.iloc[-2]
            latest_bb_upper = bb_upper.iloc[-1]

            # 關鍵點 1：強勢突破布林上軌 (當日收盤價 > 上軌，且前一日在軌內)
            bb_breakout = (
                latest_close > latest_bb_upper
            ) and (prev_close <= bb_upper.iloc[-2])

            # 關鍵點 2：短中均線多頭排列 (5MA > 10MA > 20MA) 且 5MA 向上
            ma_bullish = (
                (ma5.iloc[-1] > ma10.iloc[-1] > ma20.iloc[-1])
                and (ma5.iloc[-1] > ma5.iloc[-2])
            )

            results[code] = {
                "Price": round(float(latest_close), 2),
                "BB_Breakout": bb_breakout,
                "MA_Bullish": ma_bullish,
            }
        return results
    except Exception:
        return {}


# UI 選單與主程式
st.sidebar.header("🎯 技術關鍵點過濾選項")
filter_bb = st.sidebar.checkbox(
    "🔥 關鍵點 1：強勢突破布林上軌 (開牌訊號)", value=False
)
filter_ma = st.sidebar.checkbox(
    "📈 關鍵點 2：均線多頭排列 (5MA > 10MA > 20MA)", value=True
)

sort_by = st.sidebar.selectbox(
    "📊 排序方式",
    ["投信買超張數", "外資買超張數", "成交量"],
)

if st.button("🚀 開始選股分析", use_container_width=True):
    with st.spinner("正在取得籌碼與價格資料..."):
        df_chips, trade_date = fetch_chips_data()

        if not df_chips.empty:
            # 初步篩選：土洋合買 且 成交量 >= 1000 張
            df_filtered = df_chips[
                (df_chips["Foreign_Buy"] > 0)
                & (df_chips["Sitca_Buy"] > 0)
                & (df_chips["Volume"] >= 1000000)  # 1000張 = 1,000,000股
            ].copy()

            # 轉張數
            df_filtered["Foreign_Buy_K"] = (
                df_filtered["Foreign_Buy"] / 1000
            ).astype(int)
            df_filtered["Sitca_Buy_K"] = (
                df_filtered["Sitca_Buy"] / 1000
            ).astype(int)
            df_filtered["Volume_K"] = (
                df_filtered["Volume"] / 1000
            ).astype(int)

            # 批次取得技術指標
            codes = df_filtered["Code"].tolist()
            tech_data = batch_check_technical_signals(codes)

            # 填入技術指標欄位
            df_filtered["Price"] = df_filtered["Code"].apply(
                lambda c: tech_data.get(c, {}).get("Price", 0.0)
            )
            df_filtered["BB_Breakout"] = df_filtered["Code"].apply(
                lambda c: tech_data.get(c, {}).get("BB_Breakout", False)
            )
            df_filtered["MA_Bullish"] = df_filtered["Code"].apply(
                lambda c: tech_data.get(c, {}).get("MA_Bullish", False)
            )

            # 套用條件過濾
            if filter_bb:
                df_filtered = df_filtered[df_filtered["BB_Breakout"] == True]
            if filter_ma:
                df_filtered = df_filtered[df_filtered["MA_Bullish"] == True]

            # 排序與整理輸出
            sort_key_map = {
                "投信買超張數": "Sitca_Buy_K",
                "外資買超張數": "Foreign_Buy_K",
                "成交量": "Volume_K",
            }
            df_filtered = df_filtered.sort_values(
                by=sort_key_map[sort_by], ascending=False
            )

            final_df = df_filtered[
                [
                    "Code",
                    "Name",
                    "Price",
                    "Volume_K",
                    "Foreign_Buy_K",
                    "Sitca_Buy_K",
                    "BB_Breakout",
                    "MA_Bullish",
                ]
            ]
            final_df.columns = [
                "股票代號",
                "股票名稱",
                "收盤價",
                "成交量(張)",
                "外資買超(張)",
                "投信買超(張)",
                "突破布林上軌",
                "均線多頭排列",
            ]

            st.success(
                f"📅 **數據日期：{trade_date}**｜成功篩選出 {len(final_df)} 支符合條件標的"
            )
            st.dataframe(final_df, hide_index=True, use_container_width=True)
        else:
            st.error("無法取得籌碼資料，請稍後再試。")
