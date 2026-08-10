from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="土洋合買+技術面選股", layout="centered")

st.title("📈 台股「土洋合買 + 均線/布林中軌轉上」選股")
st.caption("自動抓取最新籌碼資料，結合布林中軌（20MA）與短均線向上訊號")


# 使用 快取 機制，避免每次重新整理或切換頁面都重複發送 Requests 被阻擋
@st.cache_data(ttl=3600)
def get_latest_twse_data():
    """自動往回搜尋最近一個有交易資料的營業日，並加入 User-Agent 避免被阻擋"""
    current_date = datetime.now()

    # 偽裝成真實瀏覽器標頭
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
    }

    for i in range(10):
        target_date = current_date - timedelta(days=i)
        date_str = target_date.strftime("%Y%m%d")
        url_fund = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALL"

        try:
            res_fund = requests.get(url_fund, headers=headers, timeout=8)
            if res_fund.status_code == 200:
                data_fund = res_fund.json()

                if data_fund.get("stat") == "OK" and "data" in data_fund:
                    cols_fund = [
                        str(c).strip() for c in data_fund["fields"]
                    ]
                    df_fund = pd.DataFrame(
                        data_fund["data"], columns=cols_fund
                    )
                    display_date = target_date.strftime("%Y/%m/%d")
                    return df_fund, display_date
        except Exception:
            continue

    return pd.DataFrame(), None


@st.cache_data(ttl=3600)
def check_technical_signals(stock_code):
    """
    計算技術指標：
    1. 布林中軌 (20 MA) 均線即將向上/拐頭向上
    2. 均線趨勢：5 MA 向上 且 10 MA 向上，20 MA 即將向上
    """
    try:
        ticker_str = f"{stock_code}.TW"
        ticker = yf.Ticker(ticker_str)
        hist = ticker.history(period="50d")

        if len(hist) < 30:
            return False, False, 0.0

        # 計算均線 (布林中軌即為 20MA)
        hist["MA5"] = hist["Close"].rolling(window=5).mean()
        hist["MA10"] = hist["Close"].rolling(window=10).mean()
        hist["MA20"] = hist["Close"].rolling(window=20).mean()  # 布林中軌

        latest_close = hist["Close"].iloc[-1]

        # --- 判斷 1：布林中軌 (20MA) 均線即將向上/已向上 ---
        ma20_today = hist["MA20"].iloc[-1]
        ma20_prev = hist["MA20"].iloc[-2]
        ma20_prev2 = hist["MA20"].iloc[-3]

        slope_today = ma20_today - ma20_prev
        slope_prev = ma20_prev - ma20_prev2

        bb_middle_turning_up = (slope_today > 0) or (
            slope_today > slope_prev and slope_today >= -0.15
        )

        # --- 判斷 2：5MA 與 10MA 明確向上，且 20MA 即將向上 ---
        ma5_up = hist["MA5"].iloc[-1] > hist["MA5"].iloc[-2]
        ma10_up = hist["MA10"].iloc[-1] > hist["MA10"].iloc[-2]

        ma_signal = ma5_up and ma10_up and bb_middle_turning_up

        return bb_middle_turning_up, ma_signal, round(latest_close, 2)

    except Exception:
        return False, False, 0.0


def process_and_filter(df_fund, filter_bollinger=False, filter_ma=False):
    """籌碼過濾 + 技術面二階段交叉篩選"""
    if df_fund.empty:
        return pd.DataFrame()

    code_col = next(
        (c for c in df_fund.columns if "代號" in c), df_fund.columns[0]
    )
    name_col = next(
        (c for c in df_fund.columns if "名稱" in c), df_fund.columns[1]
    )
    vol_col = next(
        (c for c in df_fund.columns if "成交" in c or "股數" in c), None
    )

    foreign_col = next(
        (c for c in df_fund.columns if "外資" in c or "外陸資" in c), None
    )
    sitca_col = next((c for c in df_fund.columns if "投信" in c), None)

    if not (foreign_col and sitca_col):
        st.error("籌碼欄位解析失敗，請稍後再試。")
        return pd.DataFrame()

    temp_df = pd.DataFrame()
    temp_df["Code"] = df_fund[code_col].astype(str).str.strip()
    temp_df["Name"] = df_fund[name_col].astype(str).str.strip()

    for col_name, target in [
        (foreign_col, "Foreign_Buy"),
        (sitca_col, "Sitca_Buy"),
    ]:
        temp_df[target] = (
            df_fund[col_name]
            .astype(str)
            .str.replace(",", "")
            .str.replace(" ", "")
        )
        temp_df[target] = pd.to_numeric(
            temp_df[target], errors="coerce"
        ).fillna(0)

    if vol_col:
        temp_df["Volume"] = (
            df_fund[vol_col]
            .astype(str)
            .str.replace(",", "")
            .str.replace(" ", "")
        )
        temp_df["Volume"] = pd.to_numeric(
            temp_df["Volume"], errors="coerce"
        ).fillna(0)
    else:
        temp_df["Volume"] = (
            temp_df["Foreign_Buy"].abs() + temp_df["Sitca_Buy"].abs()
        )

    temp_df["Volume_K"] = (temp_df["Volume"] / 1000).astype(int)
    temp_df["Foreign_Buy_K"] = (temp_df["Foreign_Buy"] / 1000).astype(int)
    temp_df["Sitca_Buy_K"] = (temp_df["Sitca_Buy"] / 1000).astype(int)

    # 1. 基礎條件：土洋合買 且 成交量 >= 1000張
    condition = (
        (temp_df["Foreign_Buy_K"] > 0)
        & (temp_df["Sitca_Buy_K"] > 0)
        & (temp_df["Volume_K"] >= 1000)
    )
    base_result = temp_df[condition].copy()

    # 2. 技術面計算與過濾
    if filter_bollinger or filter_ma:
        bb_signals = []
        ma_signals = []
        prices = []

        progress_bar = st.progress(0)
        total = len(base_result)

        for idx, row in enumerate(base_result.iterrows()):
            code = row[1]["Code"]
            bb_sig, ma_sig, price = check_technical_signals(code)
            bb_signals.append(bb_sig)
            ma_signals.append(ma_sig)
            prices.append(price)

            if total > 0:
                progress_bar.progress((idx + 1) / total)

        progress_bar.empty()
        base_result["BB_Signal"] = bb_signals
        base_result["MA_Signal"] = ma_signals
        base_result["Price"] = prices

        if filter_bollinger:
            base_result = base_result[base_result["BB_Signal"] == True]
        if filter_ma:
            base_result = base_result[base_result["MA_Signal"] == True]
    else:
        base_result["Price"] = 0.0

    result = base_result[
        [
            "Code",
            "Name",
            "Price",
            "Volume_K",
            "Foreign_Buy_K",
            "Sitca_Buy_K",
        ]
    ].copy()
    result.columns = [
        "股票代號",
        "股票名稱",
        "收盤價",
        "成交量(張)",
        "外資買超(張)",
        "投信買超(張)",
    ]
    return result


# 介面配置
st.subheader("⚙️ 篩選與排序設定")
col1, col2 = st.columns(2)

with col1:
    sort_option = st.selectbox(
        "📊 結果排序依據：",
        [
            "依股價/規模（高到低）",
            "依投信買超張數（高到低）",
            "依外資買超張數（高到低）",
        ],
    )

with col2:
    enable_bb = st.checkbox("🔍 勾選：布林中軌（20MA）即將向上", value=False)
    enable_ma = st.checkbox(
        "📈 勾選：5MA與10MA向上，20MA即將向上", value=False
    )

# 執行按鈕
if st.button("🚀 一鍵查詢符合條件股票", use_container_width=True):
    with st.spinner("正在自動尋找最新資料日並分析技術指標..."):
        raw_fund, trade_date = get_latest_twse_data()

        if not raw_fund.empty:
            result_df = process_and_filter(
                raw_fund, filter_bollinger=enable_bb, filter_ma=enable_ma
            )
            if not result_df.empty:
                if "股價" in sort_option:
                    result_df = result_df.sort_values(
                        by=["收盤價", "成交量(張)"], ascending=False
                    )
                elif "投信" in sort_option:
                    result_df = result_df.sort_values(
                        by=["投信買超(張)", "外資買超(張)"], ascending=False
                    )
                elif "外資" in sort_option:
                    result_df = result_df.sort_values(
                        by=["外資買超(張)", "投信買超(張)"], ascending=False
                    )

                st.success(
                    f"📅 **數據日期：{trade_date}**｜成功篩選出 {len(result_df)} 支標的"
                )
                st.dataframe(result_df, hide_index=True, use_container_width=True)
            else:
                st.info(f"📅 **數據日期：{trade_date}**｜目前條件下無符合標的。")
        else:
            st.error(
                "❌ 無法連線至證交所或連線逾時，請稍後再試，或檢查網路環境。"
            )
