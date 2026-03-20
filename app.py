import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.express as px
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# --- 網頁基本設定 ---
st.set_page_config(page_title="個人財富管理儀表板", page_icon="💰", layout="centered")

# --- 1. 連線至 Google Sheets 資料庫 ---
# 使用 st.cache_resource 避免每次操作都重新建立連線
@st.cache_resource
def get_connection():
    return st.connection("gsheets", type=GSheetsConnection)

conn = get_connection()

# 讀取資料 (ttl=0 代表不快取，確保抓到最新資料)
try:
    df_banks = conn.read(worksheet="Banks", ttl=0)
    df_stocks = conn.read(worksheet="Stocks", ttl=0)
    df_expenses = conn.read(worksheet="Expenses", ttl=0)
except Exception as e:
    st.error(f"讀取資料庫失敗，請確認 Google Sheets 設定與 Secrets 是否正確。錯誤訊息: {e}")
    st.stop()

# 確保空表單時擁有正確的欄位 (包含備註)
if df_banks.empty: 
    df_banks = pd.DataFrame(columns=['銀行名稱', '餘額', '更新日期', '備註'])
elif '備註' not in df_banks.columns:
    df_banks['備註'] = ""

if df_stocks.empty: 
    df_stocks = pd.DataFrame(columns=['市場', '代號', '股數', '平均成本', '備註'])
elif '備註' not in df_stocks.columns:
    df_stocks['備註'] = ""

if df_expenses.empty: 
    df_expenses = pd.DataFrame(columns=['日期', '類別', '項目', '金額'])

# --- 2. 預先計算總資產與獲取即時股價 ---
total_bank = df_banks['餘額'].sum() if not df_banks.empty else 0
total_stock_value = 0
stock_details = []

if not df_stocks.empty:
    for index, row in df_stocks.iterrows():
        market = row['市場']
        
        # 1. 讀取代號並清理格式 (處理 Pandas 將數字加上 .0 的問題)
        raw_ticker = str(row['代號']).strip()
        if raw_ticker.endswith(".0"):
            ticker = raw_ticker[:-2] # 把最後的 .0 刪掉
        else:
            ticker = raw_ticker
            
        shares = float(row['股數'])
        cost = float(row['平均成本'])
        note = row.get('備註', '') 
        current_price = 0
        
        # --- 2. 抓取即時報價 (雙重防護機制：偽裝瀏覽器 + FinMind 備用) ---
        try:
            fetch_success = False
            
            # 策略 A：偽裝成正常瀏覽器，避免被 Yahoo Finance 擋下 (解決 403 錯誤)
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
            
            yf_tickers_to_try = [ticker]
            if market == "台灣股市" and not (ticker.endswith(".TW") or ticker.endswith(".TWO")):
                yf_tickers_to_try = [f"{ticker}.TW", f"{ticker}.TWO"]

            for yf_t in yf_tickers_to_try:
                # 把 session 傳進去給 yfinance
                stock_info = yf.Ticker(yf_t, session=session)
                hist = stock_info.history(period="7d") # 拉長到 7 天防連假無開盤
                
                if not hist.empty:
                    current_price = float(hist['Close'].iloc[-1])
                    fetch_success = True
                    break 
            
            # 策略 B：如果 Yahoo Finance 還是失敗，且是台股，自動啟動 FinMind 備用 API
            if not fetch_success and market == "台灣股市":
                url = "https://api.finmindtrade.com/api/v4/data"
                params = {
                    "dataset": "TaiwanStockPrice", 
                    "data_id": ticker, 
                    "start_date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                }
                res = requests.get(url, params=params, timeout=5).json()
                if res.get('msg') == 'success' and len(res['data']) > 0:
                    current_price = float(res['data'][-1]['close'])
                    fetch_success = True
            
            # 如果 A 跟 B 都失敗了，才會退回成本價
            if not fetch_success:
                current_price = cost 
                st.toast(f"⚠️ {ticker} 報價抓取失敗，請確認代號是否正確。")
                
        except Exception as e:
            current_price = cost
            print(f"抓取 {ticker} 發生異常: {e}")
            st.toast(f"⚠️ 讀取 {ticker} 發生連線異常。")
                
        # --- 3. 計算成本、手續費、稅金與損益 ---
        if market == "台灣股市":
            fee_rate = 0.001425 * 0.28 # 台股手續費 2.8 折
            tax_rate = 0.003           # 台股交易稅千分之三
        else:
            fee_rate = 0.0             # 預設美股免手續費與交易稅
            tax_rate = 0.0
            
        buy_fee = cost * shares * fee_rate
        total_cost = cost * shares + buy_fee
        
        sell_fee = current_price * shares * fee_rate
        sell_tax = current_price * shares * tax_rate
        
        current_value = (current_price * shares) - sell_fee - sell_tax
        total_stock_value += current_value 
        
        profit = current_value - total_cost
        profit_pct = (profit / total_cost) * 100 if total_cost > 0 else 0
        
        net_sell_ratio = 1 - fee_rate - tax_rate
        break_even_price = total_cost / (shares * net_sell_ratio) if shares > 0 and net_sell_ratio > 0 else cost
        
        stock_details.append({
            'ticker': ticker, 'market': market, 'shares': shares, 
            'current_price': current_price, 'current_value': current_value, 
            'profit': profit, 'profit_pct': profit_pct,
            'break_even': break_even_price,
            'note': note
        })

# --- 3. 介面與分頁設計 ---
st.title("📊 財富管理儀表板")
tab_home, tab_bank, tab_stock, tab_expense = st.tabs(["🏠 首頁", "🏦 銀行存款", "📈 股票投資", "💸 支出追蹤"])

# --- 首頁：總資產概況 ---
with tab_home:
    st.subheader("資產分布概況")
    total_assets = total_bank + total_stock_value
    
    st.metric(label="預估總資產 (TWD)", value=f"NT$ {total_assets:,.0f}")
    
    if total_assets > 0:
        fig = px.pie(
            values=[total_bank, total_stock_value], 
            names=['銀行存款', '股票投資'],
            hole=0.4,
            color_discrete_sequence=px.colors.sequential.Teal
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("目前尚無資產資料，請至其他分頁新增。")

# --- 銀行存款 ---
with tab_bank:
    st.subheader("帳戶餘額管理")
    if not df_banks.empty:
        for index, row in df_banks.iterrows():
            st.metric(label=f"🏦 {row['銀行名稱']}", value=f"NT$ {row['餘額']:,.0f}", delta=f"更新於: {row['更新日期']}", delta_color="off")
            
            note = row.get('備註', '')
            if pd.notna(note) and str(note).strip() != "":
                st.caption(f"📝 備註：{note}")
                
    else:
        st.write("尚無帳戶資料。")
        
    st.divider()
    with st.expander("➕ 新增/更新銀行帳戶"):
        new_bank = st.text_input("銀行名稱 (如：玉山銀行)")
        new_amount = st.number_input("目前餘額", min_value=0, step=1000)
        new_note = st.text_input("備註 (選填，例如：薪資戶、旅遊基金)")
        
        if st.button("確認更新"):
            if new_bank in df_banks['銀行名稱'].values:
                df_banks.loc[df_banks['銀行名稱'] == new_bank, '餘額'] = new_amount
                df_banks.loc[df_banks['銀行名稱'] == new_bank, '更新日期'] = datetime.now().strftime("%Y-%m-%d")
                df_banks.loc[df_banks['銀行名稱'] == new_bank, '備註'] = new_note 
            else:
                new_row = pd.DataFrame([{
                    '銀行名稱': new_bank, 
                    '餘額': new_amount, 
                    '更新日期': datetime.now().strftime("%Y-%m-%d"),
                    '備註': new_note 
                }])
                df_banks = pd.concat([df_banks, new_row], ignore_index=True)
            
            conn.update(worksheet="Banks", data=df_banks)
            st.success("更新成功！")
            st.rerun()

# --- 股票投資 ---
with tab_stock:
    st.subheader("庫存持股狀況")
    if stock_details:
        for s in stock_details:
            st.markdown(f"#### 🏷️ **{s['ticker']}** ({s['market']})")
            if pd.notna(s['note']) and str(s['note']).strip() != "":
                st.caption(f"📝 備註：{s['note']}")
                
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric(label="持有股數", value=f"{s['shares']:.0f} 股")
            with col2:
                st.metric(label="及時股價", value=f"${s['current_price']:,.2f}")
            with col3:
                st.metric(label="損益平衡價", value=f"${s['break_even']:,.2f}")
            with col4:
                st.metric(
                    label="目前淨損益", 
                    value=f"${s['profit']:,.0f}", 
                    delta=f"{s['profit_pct']:.2f}%"
                )
            st.divider() 
    else:
        st.write("目前尚無持股紀錄。")
        
    st.divider()
    with st.expander("➕ 新增買進紀錄"):
        col1, col2 = st.columns(2)
        with col1:
            s_market = st.selectbox("市場", ["台灣股市", "美國股市"])
            s_ticker = st.text_input("股票代號 (台股如 2330，美股如 AAPL)")
            s_note = st.text_input("備註 (選填，例如：長期存股、短線)") 
        with col2:
            s_shares = st.number_input("買進股數", min_value=1, step=1)
            s_cost = st.number_input("平均買進成本", min_value=0.0, step=1.0)
            
        if st.button("新增持股"):
            new_stock = pd.DataFrame([{
                '市場': s_market, 
                '代號': s_ticker, 
                '股數': s_shares, 
                '平均成本': s_cost, 
                '備註': s_note
            }])
            df_stocks = pd.concat([df_stocks, new_stock], ignore_index=True)
            conn.update(worksheet="Stocks", data=df_stocks)
            st.success("已寫入 Google Sheets！")
            st.rerun()

# --- 支出追蹤 ---
with tab_expense:
    st.subheader("支出紀錄與趨勢")
    
    with st.form("expense_form"):
        col1, col2 = st.columns(2)
        with col1:
            e_date = st.date_input("日期")
            e_cat = st.selectbox("類別", ["膳食", "交通", "進修/書籍", "醫療/保健", "娛樂", "其他"])
        with col2:
            e_name = st.text_input("項目說明")
            e_amount = st.number_input("金額", min_value=0, step=10)
            
        if st.form_submit_button("新增一筆支出"):
            new_record = pd.DataFrame([{'日期': e_date.strftime("%Y-%m-%d"), '類別': e_cat, '項目': e_name, '金額': e_amount}])
            df_expenses = pd.concat([df_expenses, new_record], ignore_index=True)
            conn.update(worksheet="Expenses", data=df_expenses)
            st.success("支出已記錄！")
            st.rerun()
            
    if not df_expenses.empty:
        df_expenses['金額'] = pd.to_numeric(df_expenses['金額'])
        expense_trend = df_expenses.groupby('日期')['金額'].sum().reset_index()
        fig_exp = px.line(expense_trend, x='日期', y='金額', title="每日支出趨勢", markers=True)
        st.plotly_chart(fig_exp, use_container_width=True)
        
        with st.expander("查看原始數據"):
            st.dataframe(df_expenses, use_container_width=True)
