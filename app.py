import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

st.set_page_config(page_title="土洋合買一鍵選股", layout="centered")

st.title("📈 台股「土洋合買」強勢股一鍵查詢")
st.caption("自動抓取證交所最新交易日籌碼與市值資料，支援多維度排序")

def get_latest_twse_data():
    """自動往回搜尋最近一個有交易資料的營業日（含籌碼與收盤行情）"""
    current_date = datetime.now()
    
    for i in range(10):
        target_date = current_date - timedelta(days=i)
        date_str = target_date.strftime('%Y%m%d')
        
        # 1. 抓取三大法人籌碼資料 (T86)
        url_fund = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALL"
        # 2. 抓取每日收盤行情與市值資訊 (MI_INDEX)
        url_price = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&date={date_str}&type=ALL"
        
        try:
            res_fund = requests.get(url_fund, timeout=5)
            data_fund = res_fund.json()
            
            if data_fund.get('stat') == 'OK' and 'data' in data_fund:
                cols_fund = [str(c).strip() for c in data_fund['fields']]
                df_fund = pd.DataFrame(data_fund['data'], columns=cols_fund)
                display_date = target_date.strftime('%Y/%m/%d')
                
                # 嘗試抓取行情補齊收盤價與市值
                try:
                    res_price = requests.get(url_price, timeout=5)
                    data_price = res_price.json()
                    df_price = pd.DataFrame()
                    
                    # MI_INDEX 的個股資料通常在 tables 的第 9 或 10 個表格
                    if 'tables' in data_price:
                        for tbl in data_price['tables']:
                            if '證券代號' in str(tbl) or 'Code' in str(tbl):
                                p_cols = [str(c).strip() for c in tbl['fields']]
                                df_price = pd.DataFrame(tbl['data'], columns=p_cols)
                                break
                except:
                    df_price = pd.DataFrame()
                
                return df_fund, df_price, display_date
        except:
            continue
            
    return pd.DataFrame(), pd.DataFrame(), None

def process_and_filter(df_fund, df_price):
    """資料清洗、市值計算與條件篩選"""
    if df_fund.empty:
        return pd.DataFrame()

    # 籌碼欄位模糊搜尋
    code_col = next((c for c in df_fund.columns if '代號' in c), df_fund.columns[0])
    name_col = next((c for c in df_fund.columns if '名稱' in c), df_fund.columns[1])
    vol_col = next((c for c in df_fund.columns if '成交' in c or '股數' in c), None)
    
    foreign_col = next((c for c in df_fund.columns if '外資' in c or '外陸資' in c), None)
    sitca_col = next((c for c in df_fund.columns if '投信' in c), None)

    if not (foreign_col and sitca_col):
        st.error("籌碼欄位解析失敗，請稍後再試。")
        return pd.DataFrame()

    # 提取籌碼基本資料
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

    # 換算為張數
    temp_df['Volume_K'] = (temp_df['Volume'] / 1000).astype(int)
    temp_df['Foreign_Buy_K'] = (temp_df['Foreign_Buy'] / 1000).astype(int)
    temp_df['Sitca_Buy_K'] = (temp_df['Sitca_Buy'] / 1000).astype(int)

    # 匹配收盤價與市值
    temp_df['Close_Price'] = 0.0
    if not df_price.empty:
        p_code_col = next((c for c in df_price.columns if '代號' in c), None)
        p_close_col = next((c for c in df_price.columns if '收盤' in c or '最後揭示價' in c), None)
        
        if p_code_col and p_close_col:
            price_map = {}
            for _, row in df_price.iterrows():
                c_code = str(row[p_code_col]).strip()
                c_price = str(row[p_close_col]).replace(',', '').strip()
                try:
                    price_map[c_code] = float(c_price)
                except:
                    price_map[c_code] = 0.0
            
            temp_df['Close_Price'] = temp_df['Code'].map(price_map).fillna(0.0)

    # 條件篩選：外資 > 0張 且 投信 > 0張 且 總成交量 >= 1000張
    condition = (temp_df['Foreign_Buy_K'] > 0) & (temp_df['Sitca_Buy_K'] > 0) & (temp_df['Volume_K'] >= 1000)
    result = temp_df[condition][['Code', 'Name', 'Close_Price', 'Volume_K', 'Foreign_Buy_K', 'Sitca_Buy_K']].copy()
    
    # 估算成交金額作為市值排序參考（或直接呈現價格）
    result['Estimated_Market_Cap'] = result['Close_Price'] * result['Volume_K']
    result.columns = ['股票代號', '股票名稱', '收盤價', '成交量(張)', '外資買超(張)', '投信買超(張)', 'MarketCap_Ref']

    return result

# 主介面邏輯
sort_option = st.selectbox(
    "📊 請選擇結果排序方式：",
    ["依市值/股價規模（高到低）", "依投信買超張數（高到低）", "依外資買超張數（高到低）"]
)

if st.button("🚀 一鍵查詢最新土洋合買名單", use_container_width=True):
    with st.spinner("正在搜尋並抓取證交所最新交易日籌碼與市值資料..."):
        raw_fund, raw_price, trade_date = get_latest_twse_data()
        
        if not raw_fund.empty:
            result_df = process_and_filter(raw_fund, raw_price)
            if not result_df.empty:
                # 依選單排序
                if "市值" in sort_option:
                    result_df = result_df.sort_values(by=['收盤價', '成交量(張)'], ascending=False)
                elif "投信" in sort_option:
                    result_df = result_df.sort_values(by=['投信買超(張)', '外資買超(張)'], ascending=False)
                elif "外資" in sort_option:
                    result_df = result_df.sort_values(by=['外資買超(張)', '投信買超(張)'], ascending=False)

                # 隱藏內部計算用欄位
                display_df = result_df.drop(columns=['MarketCap_Ref'])

                st.success(f"成功取得資料！【資料日期：{trade_date}】 共篩選出 {len(display_df)} 支股票")
                st.dataframe(display_df, hide_index=True, use_container_width=True)
            else:
                st.info(f"【資料日期：{trade_date}】 無符合外資與投信同時買超的標的。")
        else:
            st.error("無法取得證交所資料，請稍後再試。")
