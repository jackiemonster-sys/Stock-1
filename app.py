import streamlit as st
import pandas as pd
import requests
from datetime import datetime

st.set_page_config(page_title="土洋合買一鍵選股", layout="centered")

st.title("📈 台股「土洋合買」強勢股一鍵查詢")
st.caption("自動抓取證交所最新資料，篩選外資與投信同步加碼標的")

def get_twse_data():
    today = datetime.now()
    date_str = today.strftime('%Y%m%d')
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALL"
    res = requests.get(url)
    
    try:
        data = res.json()
    except:
        return pd.DataFrame()
    
    if data.get('stat') != 'OK':
        return pd.DataFrame()
        
    cols = data['fields']
    df = pd.DataFrame(data['data'], columns=cols)
    df = df[['證券代號', '證券名稱', '成交股數', '外陸資買賣超股數(不含外資自營商)', '投信買賣超股數']]
    df.columns = ['Code', 'Name', 'Volume', 'Foreign_Buy', 'Sitca_Buy']
    
    for col in ['Volume', 'Foreign_Buy', 'Sitca_Buy']:
        df[col] = df[col].astype(str).str.replace(',', '').astype(float)
        
    df['Volume_K'] = (df['Volume'] / 1000).astype(int)
    df['Foreign_Buy_K'] = (df['Foreign_Buy'] / 1000).astype(int)
    df['Sitca_Buy_K'] = (df['Sitca_Buy'] / 1000).astype(int)
    
    condition = (df['Foreign_Buy_K'] > 0) & (df['Sitca_Buy_K'] > 0) & (df['Volume_K'] >= 1000)
    result = df[condition][['Code', 'Name', 'Volume_K', 'Foreign_Buy_K', 'Sitca_Buy_K']]
    result.columns = ['股票代號', '股票名稱', '成交量(張)', '外資買超(張)', '投信買超(張)']
    return result.sort_values(by=['投信買超(張)', '外資買超(張)'], ascending=False)

if st.button("🚀 一鍵查詢最新土洋合買名單", use_container_width=True):
    with st.spinner("正在抓取證交所最新籌碼資料..."):
        df_result = get_twse_data()
        if not df_result.empty:
            st.success(f"成功取得資料！共篩選出 {len(df_result)} 支股票")
            st.dataframe(df_result, hide_index=True, use_container_width=True)
        else:
            st.warning("今日尚無交易資料、資料更新中或非交易日。")
