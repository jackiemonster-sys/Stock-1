import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

st.set_page_config(page_title="土洋合買一鍵選股", layout="centered")

st.title("📈 台股「土洋合買」強勢股一鍵查詢")
st.caption("自動抓取證交所最新交易日籌碼資料，篩選外資與投信同步加碼標的")

def get_latest_twse_data():
    """自動往回搜尋最近一個有交易資料的營業日"""
    current_date = datetime.now()
    
    # 最多往回找 10 天（覆蓋長假）
    for i in range(10):
        target_date = current_date - timedelta(days=i)
        date_str = target_date.strftime('%Y%m%d')
        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALL"
        
        try:
            res = requests.get(url, timeout=5)
            data = res.json()
            
            # 若取得成功且 stat 為 OK，代表找到了最新的交易日資料
            if data.get('stat') == 'OK' and 'data' in data:
                cols = data['fields']
                df = pd.DataFrame(data['data'], columns=cols)
                display_date = target_date.strftime('%Y/%m/%d')
                return df, display_date
        except:
            continue
            
    return pd.DataFrame(), None

def process_and_filter(df):
    """資料清洗與條件篩選"""
    if df.empty:
        return pd.DataFrame()
        
    df = df[['證券代號', '證券名稱', '成交股數', '外陸資買賣超股數(不含外資自營商)', '投信買賣超股數']]
    df.columns = ['Code', 'Name', 'Volume', 'Foreign_Buy', 'Sitca_Buy']
    
    for col in ['Volume', 'Foreign_Buy', 'Sitca_Buy']:
        df[col] = df[col].astype(str).str.replace(',', '').astype(float)
        
    df['Volume_K'] = (df['Volume'] / 1000).astype(int)
    df['Foreign_Buy_K'] = (df['Foreign_Buy'] / 1000).astype(int)
    df['Sitca_Buy_K'] = (df['Sitca_Buy'] / 1000).astype(int)
    
    # 篩選條件：外資 > 0張 且 投信 > 0張 且 總成交量 >= 1000張
    condition = (df['Foreign_Buy_K'] > 0) & (df['Sitca_Buy_K'] > 0) & (df['Volume_K'] >= 1000)
    result = df[condition][['Code', 'Name', 'Volume_K', 'Foreign_Buy_K', 'Sitca_Buy_K']]
    result.columns = ['股票代號', '股票名稱', '成交量(張)', '外資買超(張)', '投信買超(張)']
    
    return result.sort_values(by=['投信買超(張)', '外資買超(張)'], ascending=False)

# 主介面邏輯
if st.button("🚀 一鍵查詢最新土洋合買名單", use_container_width=True):
    with st.spinner("正在搜尋並抓取證交所最新交易日資料..."):
        raw_df, trade_date = get_latest_twse_data()
        
        if not raw_df.empty:
            result_df = process_and_filter(raw_df)
            st.success(f"成功取得資料！【資料日期：{trade_date}】 共篩選出 {len(result_df)} 支股票")
            st.dataframe(result_df, hide_index=True, use_container_width=True)
        else:
            st.error("無法取得證交所資料，請稍後再試。")
