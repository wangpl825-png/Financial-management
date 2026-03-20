import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.express as px
from datetime import datetime, timedelta

# --- 網頁基本設定 ---
st.set_page_config(page_title="個人財富管理儀表板", page_icon="💰", layout="centered")

# --- 初始化暫存資料 (代替資料庫) ---
if 'expenses' not in st.session_state:
    st.session_state.expenses = pd.DataFrame(columns=['日期', '類別', '項目', '金額'])
if 'banks' not in st.session_state:
    st.session_state.banks = {'玉山銀行': 50000, '元大銀行': 30000}

# --- 標題與分頁設計 ---
st.title("📊 財富管理儀表板")
tab_home, tab_bank, tab_stock, tab_expense = st.tabs(["🏠 首頁", "🏦 銀行存款", "📈 股票投資", "💸 支出追蹤"])

# --- 1. 首頁：總資產概況 ---
with tab_home:
    st.subheader("資產分布概況")
    # 簡單加總銀行存款作為範例
    total_bank = sum(st.session_state.banks.values())
    
    # 繪製圓餅圖
    fig = px.pie(
        values=[total_bank, 150000, 20000], # 假設股票15萬，現金2萬
        names=['銀行存款', '股票投資', '手邊現金'],
        title="目前資產分布",
        hole=0.4
    )
    st.plotly_chart(fig, use_container_width=True)
    
    st.metric(label="預估總資產", value=f"NT$ {total_bank + 150000 + 20000:,}")

# --- 2. 銀行存款 ---
with tab_bank:
    st.subheader("銀行帳戶管理")
    for bank, amount in st.session_state.banks.items():
        st.metric(label=bank, value=f"NT$ {amount:,}")
    
    st.divider()
    with st.expander("➕ 新增/更新銀行帳戶"):
        new_bank = st.text_input("銀行名稱 (如：國泰世華)")
        new_amount = st.number_input("目前餘額", min_value=0, step=1000)
        if st.button("更新帳戶"):
            st.session_state.banks[new_bank] = new_amount
            st.success(f"已更新 {new_bank} 餘額為 {new_amount}")
            st.rerun()

# --- 3. 股票投資 (API 串接) ---
with tab_stock:
    st.subheader("即時股價追蹤")
    stock_type = st.radio("選擇市場", ["台灣股市", "美國股市"], horizontal=True)
    
    if stock_type == "台灣股市":
        tw_ticker = st.text_input("輸入台股代號", value="2330")
        if st.button("查詢台股"):
            try:
                # 透過 FinMind API 抓取台股資料
                url = "https://api.finmindtrade.com/api/v4/data"
                parameter = {
                    "dataset": "TaiwanStockPrice",
                    "data_id": tw_ticker,
                    "start_date": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                }
                res = requests.get(url, params=parameter)
                data = res.json()
                if data['msg'] == 'success' and len(data['data']) > 0:
                    df_tw = pd.DataFrame(data['data'])
                    fig_tw = px.line(df_tw, x='date', y='close', title=f"{tw_ticker} 近一個月收盤價趨勢")
                    st.plotly_chart(fig_tw, use_container_width=True)
                    st.metric(label="最新收盤價", value=df_tw['close'].iloc[-1])
                else:
                    st.warning("查無資料或達到 API 限制。")
            except Exception as e:
                st.error(f"獲取資料失敗: {e}")
                
    else:
        us_ticker = st.text_input("輸入美股代號", value="AAPL")
        if st.button("查詢美股"):
            try:
                # 透過 yfinance 抓取美股資料
                stock = yf.Ticker(us_ticker)
                hist = stock.history(period="1mo")
                fig_us = px.line(hist, x=hist.index, y='Close', title=f"{us_ticker} 近一個月收盤價趨勢")
                st.plotly_chart(fig_us, use_container_width=True)
                st.metric(label="最新收盤價 (USD)", value=round(hist['Close'].iloc[-1], 2))
            except Exception as e:
                st.error("查無此代號或網路錯誤")

# --- 4. 支出追蹤 ---
with tab_expense:
    st.subheader("本月支出紀錄")
    
    with st.form("expense_form"):
        col1, col2 = st.columns(2)
        with col1:
            e_date = st.date_input("日期")
            e_cat = st.selectbox("類別", ["膳食", "交通", "進修/書籍", "醫療/保健", "娛樂", "其他"])
        with col2:
            e_name = st.text_input("項目說明")
            e_amount = st.number_input("金額", min_value=0, step=10)
            
        submitted = st.form_submit_button("新增一筆支出")
        if submitted:
            new_record = pd.DataFrame([{'日期': e_date, '類別': e_cat, '項目': e_name, '金額': e_amount}])
            st.session_state.expenses = pd.concat([st.session_state.expenses, new_record], ignore_index=True)
            st.success("新增成功！")
            
    if not st.session_state.expenses.empty:
        st.dataframe(st.session_state.expenses, use_container_width=True)
        # 支出趨勢圖
        expense_trend = st.session_state.expenses.groupby('日期')['金額'].sum().reset_index()
        fig_exp = px.line(expense_trend, x='日期', y='金額', title="每日支出趨勢", markers=True)
        st.plotly_chart(fig_exp, use_container_width=True)
