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
    
    # 最多往回找 10 天（覆蓋週末與長假）
    for i in range(10):
        target_date = current_date - timedelta(days=i)
        date_str = target_date.strftime('%Y%m%d')
        url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALL"
        
        try:
            res = requests.get(url, timeout=5)
            data = res.json()
            
            if data.get('stat') == 'OK' and 'data' in data:
                cols = [str(c).strip() for c in data['fields']]
                df = pd.DataFrame(data['data'], columns=cols)
                display_date = target_date.strftime('%Y/%m/%d')
                return df, display_date
        except:
            continue
            
    return pd.DataFrame(), None

def process_and_filter(df):
    """防錯處理：使用模糊關鍵字尋找欄位，避免 KeyError"""
    if df.empty:
        return pd.DataFrame()

    # 尋找關鍵欄位
    code_col = next((c for c in df.columns if '代號' in c), df.columns[0])
    name_col = next((c for c in df.columns if '名稱' in c), df.columns[1])
    vol_col = next((c for c in df.columns if '成交' in c or '股數' in c), None)
    
    # 尋找外資與投信買賣超欄位
    foreign_col = next((c for c in df.columns if '外資' in c or '外陸資' in c and '買賣超' in c), None)
    sitca_col = next((c for c in df.columns if '投信' in c and '買賣超' in c), None)

    # 若找不到欄位則改用位置備案
    if not foreign_col:
        foreign_col = next((c for c in df.columns if '外資' in c or '外陸資' in c), None)
    if not sitca_col:
        sitca_col = next((c for c in df.columns if '投信' in c), None)

    if not (foreign_col and sitca_col):
        st.error("欄位解析失敗，請稍後再試。")
        return pd.DataFrame()

    # 提取數據
    temp_df = pd.DataFrame()
    temp_df['Code'] = df[code_col].astype(str).str.strip()
    temp_df['Name'] = df[name_col].astype(str).str.strip()
    
    # 數值轉化與清理
    for col_name, target in [(foreign_col, 'Foreign_Buy'), (sitca_col, 'Sitca_Buy')]:
        temp_df[target] = df[col_name].astype(str).str.replace(',', '').str.replace(' ', '')
        temp_df[target] = pd.to_numeric(temp_df[target], errors='coerce').fillna(0)

    if vol_col:
        temp_df['Volume'] = df[vol_col].astype(str).str.replace(',', '').str.replace(' ', '')
        temp_df['Volume'] = pd.to_numeric(temp_df['Volume'], errors='coerce').fillna(0)
    else:
        temp_df['Volume'] = temp_df['Foreign_Buy'].abs() + temp_df['Sitca_Buy'].abs()

    # 換算為張數 (1張 = 1000股)
    temp_df['Volume_K'] = (temp_df['Volume'] / 1000).astype(int)
    temp_df['Foreign_Buy_K'] = (temp_df['Foreign_Buy'] / 1000).astype(int)
    temp_df['Sitca_Buy_K'] = (temp_df['Sitca_Buy'] / 1000).astype(int)

    # 條件篩選：外資 > 0張 且 投信 > 0張 且 總成交量 >= 1000張
    condition = (temp_df['Foreign_Buy_K'] > 0) & (temp_df['Sitca_Buy_K'] > 0) & (temp_df['Volume_K'] >= 1000)
    result = temp_df[condition][['Code', 'Name', 'Volume_K', 'Foreign_Buy_K', 'Sitca_Buy_K']]
    result.columns = ['股票代號', '股票名稱', '成交量(張)', '外資買超(張)', '投信買超(張)']

    return result.sort_values(by=['投信買超(張)', '外資買超(張)'], ascending=False)

# 主介面邏輯
if st.button("🚀 一鍵查詢最新土洋合買名單", use_container_width=True):
    with st.spinner("正在搜尋並抓取證交所最新交易日資料..."):
        raw_df, trade_date = get_latest_twse_data()
        
        if not raw_df.empty:
            result_df = process_and_filter(raw_df)
            if not result_df.empty:
                st.success(f"成功取得資料！【資料日期：{trade_date}】 共篩選出 {len(result_df)} 支股票")
                st.dataframe(result_df, hide_index=True, use_container_width=True)
            else:
                st.info(f"【資料日期：{trade_date}】 無符合外資與投信同時買超的標的。")
        else:
            st.error("無法取得證交所資料，請稍後再試。")
