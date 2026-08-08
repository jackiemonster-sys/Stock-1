import streamlit as st
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime, timedelta

st.set_page_config(page_title="土洋合買+布林轉上選股", layout="centered")

st.title("📈 台股「土洋合買 + 布林轉上」一鍵選股")
st.caption("自動抓取最新籌碼資料，結合布林通道（Bollinger Bands）下軌轉上訊號")

def get_latest_twse_data():
    """自動往回搜尋最近一個有交易資料的營業日"""
    current_date = datetime.now()
    
    for i in range(10):
        target_date = current_date - timedelta(days=i)
        date_str = target_date.strftime('%Y%m%d')
        url_fund = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALL"
        
        try:
            res_fund = requests.get(url_fund, timeout=5)
            data_fund = res_fund.json()
            
            if data_fund.get('stat') == 'OK' and 'data' in data_fund:
                cols_fund = [str(c).strip() for c in data_fund['fields']]
                df_fund = pd.DataFrame(data_fund['data'], columns=cols_fund)
                display_date = target_date.strftime('%Y/%m/%d')
                return df_fund, display_date
        except:
            continue
            
    return pd.DataFrame(), None

def check_bollinger_signal(stock_code):
    """
    計算布林通道 (20 MA, 2倍標準差)
    判斷條件：
    1. 過去 3 天內曾觸及或跌破下軌 (Lower Band)
    2. 近 1~2 天收盤價開始拉回向上，且紅 K 或止跌（下軌拐頭或股價離開下軌向上）
    """
    try:
        # 台股上市代號格式為 XXXX.TW
        ticker_str = f"{stock_code}.TW"
        ticker = yf.Ticker(ticker_str)
        
        # 抓取近 40 天 K 線資料
        hist = ticker.history(period="40d")
        if len(hist) < 25:
            return False, 0.0, "資料不足"
            
        # 計算 20 MA 與布林上下軌
        hist['MA20'] = hist['Close'].rolling(window=20).mean()
        hist['STD20'] = hist['Close'].rolling(window=20).std()
        hist['Upper'] = hist['MA20'] + (hist['STD20'] * 2)
        hist['Lower'] = hist['MA20'] - (hist['STD20'] * 2)
        
        latest_close = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2]
        latest_lower = hist['Lower'].iloc[-1]
        prev_lower = hist['Lower'].iloc[-2]
        
        # 判斷條件：
        # A. 今日收盤價低於下軌的 1.02 倍（代表貼近下軌或剛從下軌彈起）
        # B. 今日收盤價高於昨日收盤價（股價轉強向上），或者下軌斜率開始止跌轉平/轉上
        near_or_below_lower = any(hist['Close'].iloc[-3:] <= hist['Lower'].iloc[-3:] * 1.015)
        turning_up = (latest_close > prev_close) or (latest_lower >= prev_lower)
        
        is_signal = near_or_below_lower and turning_up
        return is_signal, round(latest_close, 2), "下軌止跌轉上" if is_signal else "未符合"
        
    except:
        return False, 0.0, "計算失敗"

def process_and_filter(df_fund, filter_bollinger=False):
    """資料清洗、籌碼篩選與布林通道交叉檢驗"""
    if df_fund.empty:
        return pd.DataFrame()

    code_col = next((c for c in df_fund.columns if '代號' in c), df_fund.columns[0])
    name_col = next((c for c in df_fund.columns if '名稱' in c), df_fund.columns[1])
    vol_col = next((c for c in df_fund.columns if '成交' in c or '股數' in c), None)
    
    foreign_col = next((c for c in df_fund.columns if '外資' in c or '外陸資' in c), None)
    sitca_col = next((c for c in df_fund.columns if '投信' in c), None)

    if not (foreign_col and sitca_col):
        st.error("籌碼欄位解析失敗，請稍後再試。")
        return pd.DataFrame()

    temp_df = pd.DataFrame()
    temp_df['Code'] = df_fund[code_col].astype(str).str.strip()
    temp_df['Name'] = df_fund[name_col].astype(str).str.strip()
    
    for col_name, target in [(foreign_col, 'Foreign_Buy'), (sitca_col, 'Sitca_Buy')]:
        temp_df[target] = df_fund[col_name].astype(str).str.replace(',', '').str.replace(' ', '')
        temp_df[target] = pd.to_numeric(temp_df[target], errors='coerce').fillna(0)

    if vol_col:
        temp_df['Volume'] = df_fund[vol_col].astype(str).str.replace(',', '').str.replace(' ', '')
        temp_df['Volume'] = pd.to_numeric(temp_df['Volume'], errors='coerce').fillna(0)
    else:
        temp_df['Volume'] = temp_df['Foreign_Buy'].abs() + temp_df['Sitca_Buy'].abs()

    temp_df['Volume_K'] = (temp_df['Volume'] / 1000).astype(int)
    temp_df['Foreign_Buy_K'] = (temp_df['Foreign_Buy'] / 1000).astype(int)
    temp_df['Sitca_Buy_K'] = (temp_df['Sitca_Buy'] / 1000).astype(int)

    # 1. 先篩選土洋合買標的
    condition = (temp_df['Foreign_Buy_K'] > 0) & (temp_df['Sitca_Buy_K'] > 0) & (temp_df['Volume_K'] >= 1000)
    base_result = temp_df[condition].copy()

    # 2. 若開啟布林通道過濾，逐一計算技術面訊號
    prices = []
    bollinger_signals = []
    
    if filter_bollinger:
        progress_bar = st.progress(0)
        total = len(base_result)
        
        for idx, row in enumerate(base_result.iterrows()):
            code = row[1]['Code']
            is_sig, price, status = check_bollinger_signal(code)
            bollinger_signals.append(is_sig)
            prices.append(price)
            if total > 0:
                progress_bar.progress((idx + 1) / total)
                
        progress_bar.empty()
        base_result['BB_Signal'] = bollinger_signals
        base_result['Price'] = prices
        base_result = base_result[base_result['BB_Signal'] == True]
    else:
        base_result['Price'] = 0.0

    result = base_result[['Code', 'Name', 'Price', 'Volume_K', 'Foreign_Buy_K', 'Sitca_Buy_K']].copy()
    result.columns = ['股票代號', '股票名稱', '收盤價', '成交量(張)', '外資買超(張)', '投信買超(張)']
    return result

# 控制面板介面
col1, col2 = st.columns(2)

with col1:
    sort_option = st.selectbox(
        "📊 排序方式：",
        ["依股價/規模（高到低）", "依投信買超張數（高到低）", "依外資買超張數（高到低）"]
    )

with col2:
    enable_bb = st.checkbox("🔍 僅顯示布林通道「下軌觸底轉上」標的", value=False)

if st.button("🚀 一鍵查詢最新名單", use_container_width=True):
    with st.spinner("正在分析籌碼與布林通道指標..."):
        raw_fund, trade_date = get_latest_twse_data()
        
        if not raw_fund.empty:
            result_df = process_and_filter(raw_fund, filter_bollinger=enable_bb)
            if not result_df.empty:
                if "股價" in sort_option:
                    result_df = result_df.sort_values(by=['收盤價', '成交量(張)'], ascending=False)
                elif "投信" in sort_option:
                    result_df = result_df.sort_values(by=['投信買超(張)', '外資買超(張)'], ascending=False)
                elif "外資" in sort_option:
                    result_df = result_df.sort_values(by=['外資買超(張)', '投信買超(張)'], ascending=False)

                st.success(f"成功取得資料！【資料日期：{trade_date}】 共篩選出 {len(result_df)} 支股票")
                st.dataframe(result_df, hide_index=True, use_container_width=True)
            else:
                st.info(f"【資料日期：{trade_date}】 無符合設定條件的標的。")
        else:
            st.error("無法取得證交所資料，請稍後再試。")
