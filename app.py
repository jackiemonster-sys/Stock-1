import streamlit as st
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime, timedelta

st.set_page_config(page_title="土洋合買+多重技術面選股", layout="centered")

st.title("📈 台股「土洋合買 + 均線/布林」進階選股")
st.caption("自動抓取最新籌碼資料，結合布林下軌轉上與均線扣抵轉強訊號")

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

def check_technical_signals(stock_code):
    """
    計算技術指標：
    1. 布林通道 (20 MA, 2倍標準差) 下軌轉上
    2. 均線趨勢：5 MA 向上、10 MA 向上，且 20 MA 即將向上（斜率轉平或陡度上升）
    """
    try:
        ticker_str = f"{stock_code}.TW"
        ticker = yf.Ticker(ticker_str)
        hist = ticker.history(period="50d")
        
        if len(hist) < 30:
            return False, False, 0.0
            
        # 計算均線
        hist['MA5'] = hist['Close'].rolling(window=5).mean()
        hist['MA10'] = hist['Close'].rolling(window=10).mean()
        hist['MA20'] = hist['Close'].rolling(window=20).mean()
        
        # 計算布林通道
        hist['STD20'] = hist['Close'].rolling(window=20).std()
        hist['Lower'] = hist['MA20'] - (hist['STD20'] * 2)
        
        latest_close = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2]
        
        # --- 判斷 1：布林通道下軌轉上 ---
        near_or_below_lower = any(hist['Close'].iloc[-3:] <= hist['Lower'].iloc[-3:] * 1.015)
        bb_turning_up = near_or_below_lower and ((latest_close > prev_close) or (hist['Lower'].iloc[-1] >= hist['Lower'].iloc[-2]))
        
        # --- 判斷 2：5MA, 10MA 向上，20MA 即將向上 ---
        ma5_up = hist['MA5'].iloc[-1] > hist['MA5'].iloc[-2]
        ma10_up = hist['MA10'].iloc[-1] > hist['MA10'].iloc[-2]
        
        # 20MA 即將向上：今日 20MA 高於前日，或今日斜率止跌平緩（扣抵將過低價區）
        ma20_slope_today = hist['MA20'].iloc[-1] - hist['MA20'].iloc[-2]
        ma20_slope_prev = hist['MA20'].iloc[-2] - hist['MA20'].iloc[-3]
        ma20_turning_up = (ma20_slope_today > 0) or (ma20_slope_today > ma20_slope_prev and ma20_slope_today >= -0.1)
        
        ma_signal = ma5_up and ma10_up and ma20_turning_up
        
        return bb_turning_up, ma_signal, round(latest_close, 2)
        
    except:
        return False, False, 0.0

def process_and_filter(df_fund, filter_bollinger=False, filter_ma=False):
    """籌碼過濾 + 技術面二階段交叉篩選"""
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

    # 1. 基礎條件：土洋合買 且 成交量 >= 1000張
    condition = (temp_df['Foreign_Buy_K'] > 0) & (temp_df['Sitca_Buy_K'] > 0) & (temp_df['Volume_K'] >= 1000)
    base_result = temp_df[condition].copy()

    # 2. 技術面計算與過濾
    if filter_bollinger or filter_ma:
        bb_signals = []
        ma_signals = []
        prices = []
        
        progress_bar = st.progress(0)
        total = len(base_result)
        
        for idx, row in enumerate(base_result.iterrows()):
            code = row[1]['Code']
            bb_sig, ma_sig, price = check_technical_signals(code)
            bb_signals.append(bb_sig)
            ma_signals.append(ma_sig)
            prices.append(price)
            
            if total > 0:
                progress_bar.progress((idx + 1) / total)
                
        progress_bar.empty()
        base_result['BB_Signal'] = bb_signals
        base_result['MA_Signal'] = ma_signals
        base_result['Price'] = prices
        
        if filter_bollinger:
            base_result = base_result[base_result['BB_Signal'] == True]
        if filter_ma:
            base_result = base_result[base_result['MA_Signal'] == True]
    else:
        base_result['Price'] = 0.0

    result = base_result[['Code', 'Name', 'Price', 'Volume_K', 'Foreign_Buy_K', 'Sitca_Buy_K']].copy()
    result.columns = ['股票代號', '股票名稱', '收盤價', '成交量(張)', '外資買超(張)', '投信買超(張)']
    return result

# 介面配置
st.subheader("⚙️ 篩選與排序設定")
col1, col2 = st.columns(2)

with col1:
    sort_option = st.selectbox(
        "📊 結果排序依據：",
        ["依股價/規模（高到低）", "依投信買超張數（高到低）", "依外資買超張數（高到低）"]
    )

with col2:
    enable_bb = st.checkbox("🔍 勾選：布林下軌觸底轉上", value=False)
    enable_ma = st.checkbox("📈 勾選：5MA與10MA向上，20MA即將向上", value=False)

if st.button("🚀 一鍵查詢符合條件股票", use_container_width=True):
    with st.spinner("正在分析籌碼與均線/布林指標..."):
        raw_fund, trade_date = get_latest_twse_data()
        
        if not raw_fund.empty:
            result_df = process_and_filter(raw_fund, filter_bollinger=enable_bb, filter_ma=enable_ma)
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
                st.info(f"【資料日期：{trade_date}】 無符合目前勾選條件的標的。")
        else:
            st.error("無法取得證交所資料，請稍後再試。")
