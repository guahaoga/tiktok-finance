import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import os
import sys
import subprocess
import io
import numpy as np 

# ---------------------------------------------------------
# 1. 基础配置
# ---------------------------------------------------------
st.set_page_config(page_title="TikTok 跨境财务系统", layout="wide", page_icon="🌏")

# --- 🔐 安全登录锁 (云端版必备) ---
if "auth" not in st.session_state:
    st.session_state.auth = False

def check_password():
    st.markdown("""<style>.stTextInput input {text-align: center;}</style>""", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.title("🔒 内部系统请登录")
        pwd = st.text_input("请输入访问密码", type="password")
        if st.button("登录", use_container_width=True, type="primary"):
            if pwd == "qwe123":  # 🔥🔥🔥 在这里修改你的密码 (默认888888) 🔥🔥🔥
                st.session_state.auth = True
                st.rerun()
            else:
                st.error("密码错误")

if not st.session_state.auth:
    check_password()
    st.stop() 
# ------------------------------------

# 自动修复环境
try:
    import openpyxl
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
    import openpyxl
try:
    import xlsxwriter
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "xlsxwriter"])
    import xlsxwriter

SITES = {
    "🇹🇭 泰国": {"symbol": "฿", "code": "THB", "sku_col": "SKU-泰国", "sheet_name": "泰国"},
    "🇻🇳 越南": {"symbol": "₫", "code": "VND", "sku_col": "SKU-越南", "sheet_name": "越南"},
    "🇵🇭 菲律宾": {"symbol": "₱", "code": "PHP", "sku_col": "SKU-菲律宾", "sheet_name": "菲律宾"},
    "🇲🇾 马来西亚": {"symbol": "RM", "code": "MYR", "sku_col": "SKU-马来", "sheet_name": "马来西亚"},
    "🇸🇬 新加坡": {"symbol": "S$", "code": "SGD", "sku_col": "SKU-新加坡", "sheet_name": "新加坡"},
}

# 云端版不依赖本地持久化，依靠 Session 和 上传
if 'product_df' not in st.session_state:
    # 初始化空表
    cols = ["商品名称", "采购成本(CNY)", "SKU-泰国", "SKU-越南", "SKU-菲律宾", "SKU-马来", "SKU-新加坡"]
    st.session_state['product_df'] = pd.DataFrame(columns=cols)

# CSS 美化
st.markdown("""
<style> 
    .block-container {padding-top: 2rem !important; padding-bottom: 5rem;}
    div[data-testid="stSidebarNav"] {display: none;}
    .stButton button {font-weight: bold !important; border-radius: 8px !important;}
    div[data-testid="stMetric"] {background: #fff; border: 1px solid #f0f0f0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.03);}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 核心函数
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def get_exchange_rate(local_code):
    try:
        url = f"https://api.exchangerate-api.com/v4/latest/{local_code}"
        res = requests.get(url, timeout=3).json()
        return res['rates']['CNY']
    except:
        return 1.0

def clean_df_types(df):
    columns = ["商品名称", "采购成本(CNY)", "SKU-泰国", "SKU-越南", "SKU-菲律宾", "SKU-马来", "SKU-新加坡"]
    for col in columns:
        if col not in df.columns: df[col] = ""
    text_cols = ["商品名称", "SKU-泰国", "SKU-越南", "SKU-菲律宾", "SKU-马来", "SKU-新加坡"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).replace('nan', '')
    if "采购成本(CNY)" in df.columns:
        df["采购成本(CNY)"] = pd.to_numeric(df["采购成本(CNY)"], errors='coerce').fillna(0.0)
    return df

def generate_excel_template():
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for site_info in SITES.values():
            sheet_name = site_info['sheet_name']
            df_template = pd.DataFrame({
                "商品名称 (必填)": ["示例A", "示例B"],
                "采购成本(CNY)": [10.5, 20.0],
                "SKU ID": ["SKU-1001", "SKU-1002"]
            })
            df_template.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()

def parse_multisheet_excel(file):
    xls = pd.read_excel(file, sheet_name=None, dtype=str) 
    master_df = pd.DataFrame(columns=["商品名称", "采购成本(CNY)"])
    for site_key, site_info in SITES.items():
        sheet_name = site_info['sheet_name']
        target_col = site_info['sku_col']
        if sheet_name in xls:
            df_sheet = xls[sheet_name]
            df_sheet.columns = df_sheet.columns.str.strip()
            col_name = next((c for c in df_sheet.columns if "商品" in c or "Name" in c), None)
            col_cost = next((c for c in df_sheet.columns if "成本" in c or "Cost" in c), None)
            col_sku = next((c for c in df_sheet.columns if "SKU" in c or "ID" in c), None)
            if col_name and col_sku:
                temp_df = df_sheet[[col_name, col_sku]].copy()
                temp_df.columns = ["商品名称", target_col]
                if col_cost:
                    temp_df["采购成本(CNY)"] = pd.to_numeric(df_sheet[col_cost], errors='coerce').fillna(0)
                if master_df.empty:
                    master_df = temp_df
                else:
                    master_df = pd.merge(master_df, temp_df, on="商品名称", how="outer")
                    if "采购成本(CNY)_y" in master_df.columns:
                        master_df["采购成本(CNY)"] = master_df["采购成本(CNY)_y"].fillna(master_df["采购成本(CNY)_x"])
                        master_df = master_df.drop(columns=["采购成本(CNY)_x", "采购成本(CNY)_y"])
    return clean_df_types(master_df)

if 'current_site' not in st.session_state:
    st.session_state['current_site'] = None
if 'filter_status' not in st.session_state:
    st.session_state['filter_status'] = 'All'

# ---------------------------------------------------------
# 界面逻辑
# ---------------------------------------------------------

if st.session_state['current_site'] is None:
    st.markdown("<style>div[data-testid='stSidebar'] {display: none;}</style>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>🌏 TikTok 财务中台</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #888; margin-bottom: 50px;'>点击下方卡片进入对应站点</p>", unsafe_allow_html=True)
    
    cols = st.columns(5)
    for i, site in enumerate(SITES.keys()):
        if cols[i].button(site, use_container_width=True):
            st.session_state['current_site'] = site
            st.rerun()
    
    st.markdown("---")
    _, c, _ = st.columns([2, 2, 2])
    if c.button("📝 管理全球商品成本库", type="secondary", use_container_width=True):
        st.session_state['current_site'] = "Global_Config"
        st.rerun()

else:
    with st.sidebar:
        st.title("功能菜单")
        st.markdown("---")
        if st.session_state['current_site'] == "Global_Config":
            app_mode = "📝 商品成本库"
        else:
            app_mode = st.radio("📍 导航", ["📊 财务看板", "📝 商品成本库"], index=0)
        st.markdown("---")
        if st.session_state['current_site'] != "Global_Config":
            site_code = SITES[st.session_state['current_site']]['code']
            rate = get_exchange_rate(site_code)
            st.metric(f"当前汇率 ({site_code})", f"1 : {rate:.4f}", "CNY")
            st.divider()
        if st.button("🔙 返回首页", use_container_width=True):
            st.session_state['current_site'] = None
            st.rerun()

    if app_mode == "📝 商品成本库":
        st.title("📝 全球商品成本数据库")
        st.info("⚠️ 注意：云端版请务必点击【下载表格】备份数据，下次使用时重新导入。")
        
        with st.expander("📥 **下载 Excel 模板**", expanded=True):
            st.download_button("👉 点击下载标准模板.xlsx", generate_excel_template(), "TikTok_Template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        with st.expander("📂 **导入本地 Excel (自动合并)**", expanded=True):
            uploaded_cost_file = st.file_uploader("上传 Excel 文件", type=['xlsx'])
            if uploaded_cost_file and st.button("⚠️ 确认导入"):
                try:
                    new_df = parse_multisheet_excel(uploaded_cost_file)
                    st.session_state['product_df'] = new_df
                    st.success("✅ 导入成功！")
                    st.rerun()
                except Exception as e:
                    st.error(f"导入失败: {e}")

        st.markdown("---")
        # 下载当前数据 (云端版核心功能)
        if not st.session_state['product_df'].empty:
            current_csv = st.session_state['product_df'].to_csv(index=False).encode('utf-8-sig')
            st.download_button("💾 备份/下载当前数据 (CSV)", data=current_csv, file_name="my_costs_backup.csv", mime="text/csv", type="primary")

        st.markdown("### 在线编辑")
        edited_df = st.data_editor(
            st.session_state['product_df'],
            num_rows="dynamic",
            use_container_width=True,
            height=600,
            hide_index=True,
            column_config={
                "商品名称": st.column_config.TextColumn(width="medium", required=True),
                "采购成本(CNY)": st.column_config.NumberColumn(label="采购成本(¥)", min_value=0.0, format="%.2f", required=True),
                "SKU-泰国": st.column_config.TextColumn(width="small"),
                "SKU-越南": st.column_config.TextColumn(width="small"),
                "SKU-菲律宾": st.column_config.TextColumn(width="small"),
                "SKU-马来": st.column_config.TextColumn(width="small"),
                "SKU-新加坡": st.column_config.TextColumn(width="small"),
            }
        )
        if not edited_df.equals(st.session_state['product_df']):
            st.session_state['product_df'] = edited_df

    elif app_mode == "📊 财务看板":
        current_site = st.session_state['current_site']
        site_conf = SITES[current_site]
        symbol = site_conf['symbol']
        code = site_conf['code']
        target_sku_col = site_conf['sku_col']
        rate_to_cny = get_exchange_rate(code)

        with st.sidebar:
            st.subheader("📂 上传数据")
            uploaded_settlement = st.file_uploader(f"{current_site} Order details", type=['xlsx', 'csv'], key="settle")

        st.title(f"📊 {current_site} 经营看板")
        st.caption(f"核算货币: {code} | 汇率: 1 {code} ≈ {rate_to_cny:.4f} CNY")
        st.markdown("---")

        tot_rev, tot_sales, tot_pro, margin_sales, margin_settle = 0,0,0,0,0
        df_merged = None
        
        if uploaded_settlement:
            try:
                if uploaded_settlement.name.lower().endswith('.csv'):
                    try: df_s = pd.read_csv(uploaded_settlement)
                    except: uploaded_settlement.seek(0); df_s = pd.read_csv(uploaded_settlement, encoding='gbk')
                else:
                    df_s = pd.read_excel(uploaded_settlement, engine='openpyxl')

                cols_s = df_s.columns.tolist()
                def find(keys):
                    for c in cols_s: 
                        if any(k in c for k in keys): return c
                    return None

                col_sku = find(['SKU ID', 'SKU', 'Seller SKU'])
                col_amt = find(['Total settlement amount', 'Settlement amount', 'Amount'])
                col_rev = find(['Total Revenue', 'Revenue', 'Product Revenue', 'Total revenue', 'Sales'])
                col_date = find(['Statement Date', 'Time', 'Date'])
                col_order = find(['Order/adjustment ID', 'Order ID', '订单号'])
                col_qty = find(['Quantity', 'Qty', '数量', 'Items'])

                if col_sku and col_amt:
                    df_c = pd.DataFrame()
                    df_c['Order ID'] = df_s[col_order].astype(str).replace('nan', '') if col_order else "Unknown"
                    df_c['SKU'] = df_s[col_sku].astype(str).str.strip()
                    df_c['Settlement Amount'] = pd.to_numeric(df_s[col_amt], errors='coerce').fillna(0)
                    df_c['Quantity'] = pd.to_numeric(df_s[col_qty], errors='coerce').fillna(0) if col_qty else 1
                    df_c['Revenue'] = pd.to_numeric(df_s[col_rev], errors='coerce').fillna(0) if col_rev else 0
                    
                    if col_date:
                        df_c['Date'] = pd.to_datetime(df_s[col_date], errors='coerce')
                        df_c['Month'] = df_c['Date'].dt.strftime('%Y-%m')
                    else:
                        df_c['Month'] = "Unknown"

                    pdb = st.session_state['product_df']
                    if target_sku_col in pdb.columns:
                        valid = pdb[pdb[target_sku_col].notna()].copy()
                        valid['SKU'] = valid[target_sku_col].astype(str).str.strip()
                        valid['Cost_CNY'] = valid["采购成本(CNY)"]
                        
                        df_merged = pd.merge(df_c, valid[['SKU', 'Cost_CNY']], on='SKU', how='left')
                        df_merged['Is_Missing_Cost'] = df_merged['Cost_CNY'].isna()
                        df_merged['Cost_CNY'] = df_merged['Cost_CNY'].fillna(0)
                        
                        df_merged['Cost_Local_Unit'] = df_merged['Cost_CNY'] / rate_to_cny if rate_to_cny else 0
                        df_merged['Total_Cost'] = df_merged['Cost_Local_Unit'] * df_merged['Quantity']
                        
                        cancel_mask = (df_merged['Revenue'] == 0) & (df_merged['Settlement Amount'] == 0)
                        df_merged.loc[cancel_mask, 'Total_Cost'] = 0
                        df_merged['Is_Canceled'] = cancel_mask
                        
                        df_merged['Net_Profit'] = df_merged['Settlement Amount'] - df_merged['Total_Cost']
                        
                        conditions = [
                            df_merged['Is_Missing_Cost'],
                            df_merged['Is_Canceled'],
                            (df_merged['Net_Profit'] < 0) & (~df_merged['Is_Missing_Cost']) & (~df_merged['Is_Canceled']),
                            (df_merged['Net_Profit']*rate_to_cny > 0) & (df_merged['Net_Profit']*rate_to_cny < 2) & (~df_merged['Is_Missing_Cost'])
                        ]
                        choices = ['Missing', 'Canceled', 'Loss', 'Low']
                        df_merged['Row_Status'] = np.select(conditions, choices, default='Normal')

                        df_valid_for_calc = df_merged[~df_merged['Is_Missing_Cost']]
                        tot_sales = df_valid_for_calc['Revenue'].sum()
                        tot_rev = df_valid_for_calc['Settlement Amount'].sum()
                        tot_pro = df_valid_for_calc['Net_Profit'].sum()
                        
                        margin_sales = (tot_pro / tot_sales * 100) if tot_sales else 0
                        margin_settle = (tot_pro / tot_rev * 100) if tot_rev else 0

            except Exception as e:
                st.error(f"Error: {e}")

        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("💰 总销售额", f"{symbol} {tot_sales:,.0f}", f"≈ ¥ {tot_sales*rate_to_cny:,.0f}")
        k2.metric("💵 总回款", f"{symbol} {tot_rev:,.0f}", f"≈ ¥ {tot_rev*rate_to_cny:,.0f}")
        k3.metric("🧧 净利润", f"{symbol} {tot_pro:,.0f}", f"≈ ¥ {tot_pro*rate_to_cny:,.0f}")
        k4.metric("📉 总销售额利润率", f"{margin_sales:.1f}%", "基于总销售额")
        k5.metric("💰 总回款利润率", f"{margin_settle:.1f}%", "基于总回款")
        k6.metric("📊 订单量", f"{len(df_merged) if df_merged is not None else 0}")

        st.markdown("---")
        st.subheader("📢 推广投放效益分析")
        c_ad1, c_ad2 = st.columns([1, 4])
        with c_ad1: ad_spend = st.number_input("👉 推广花费 (¥)", 0.0, step=100.0)
        with c_ad2:
            pro_cny = tot_pro * rate_to_cny
            sales_cny = tot_sales * rate_to_cny
            roi = (sales_cny / pro_cny) if pro_cny > 0 else 0
            real_pro = pro_cny - ad_spend
            real_m = (real_pro / sales_cny * 100) if sales_cny else 0
            actual_roi = (sales_cny / ad_spend) if ad_spend > 0 else 0
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("🛡️ 投流保本 ROI", f"{roi:.2f}", help="及格线")
            m2.metric("🚀 实际投放 ROI", f"{actual_roi:.2f}", help="成绩单")
            m3.metric("💰 实际到手利润", f"¥ {real_pro:,.2f}", delta=f"-{ad_spend}", delta_color="normal")
            m4.metric("📉 实际净利率", f"{real_m:.1f}%")

        if df_merged is not None:
            st.markdown("###")
            tab1, tab2 = st.tabs(["📊 利润趋势", "📋 订单明细"])
            with tab1:
                df_chart = df_merged[~df_merged['Is_Missing_Cost']]
                if 'Month' in df_chart and df_chart['Month'].notna().any():
                    g = df_chart.groupby('Month')[['Settlement Amount', 'Net_Profit']].sum().reset_index()
                    plot_data = []
                    for idx, row in g.iterrows():
                        plot_data.append({'月份': row['Month'], '类型': '结算回款', '金额': row['Settlement Amount'], '文本': f"<b>{symbol}{row['Settlement Amount']:,.0f}</b>"})
                        plot_data.append({'月份': row['Month'], '类型': '净利润', '金额': row['Net_Profit'], '文本': f"<b>{symbol}{row['Net_Profit']:,.0f}</b>"})
                    fig = px.bar(pd.DataFrame(plot_data), x='月份', y='金额', color='类型', barmode='group', text='文本', color_discrete_map={'结算回款': '#2980B9', '净利润': '#2ECC71'})
                    st.plotly_chart(fig, use_container_width=True)

            with tab2:
                st.markdown("##### 🔍 订单筛选器")
                f1, f2, f3, f4, f5 = st.columns(5)
                filter_choice = st.session_state['filter_status']
                def set_filter(val): st.session_state['filter_status'] = val
                
                bt_all = f1.button(f"📋 全部订单 ({len(df_merged)})", type="primary" if filter_choice=='All' else "secondary", use_container_width=True, on_click=set_filter, args=('All',))
                bt_loss = f2.button(f"🟥 亏损 ({len(df_merged[df_merged['Row_Status']=='Loss'])})", type="primary" if filter_choice=='Loss' else "secondary", use_container_width=True, on_click=set_filter, args=('Loss',))
                bt_low = f3.button(f"🟨 低利 ({len(df_merged[df_merged['Row_Status']=='Low'])})", type="primary" if filter_choice=='Low' else "secondary", use_container_width=True, on_click=set_filter, args=('Low',))
                bt_cancel = f4.button(f"🟪 取消 ({len(df_merged[df_merged['Row_Status']=='Canceled'])})", type="primary" if filter_choice=='Canceled' else "secondary", use_container_width=True, on_click=set_filter, args=('Canceled',))
                bt_miss = f5.button(f"🟩 缺成本 ({len(df_merged[df_merged['Row_Status']=='Missing'])})", type="primary" if filter_choice=='Missing' else "secondary", use_container_width=True, on_click=set_filter, args=('Missing',))

                if filter_choice == 'All': filtered_df = df_merged
                else: filtered_df = df_merged[df_merged['Row_Status'] == filter_choice]

                disp = filtered_df.copy().sort_values('Date', ascending=False)
                disp['Profit_CNY_Check'] = disp['Net_Profit'] * rate_to_cny

                def fmt_dual(local, cny): 
                    if pd.isna(cny): return "未录入"
                    return f"{symbol} {local:,.2f} (¥ {cny:,.2f})"
                
                disp['Revenue_Dual'] = disp.apply(lambda x: fmt_dual(x['Revenue'], x['Revenue']*rate_to_cny), axis=1)
                disp['Settlement_Dual'] = disp.apply(lambda x: fmt_dual(x['Settlement Amount'], x['Settlement Amount']*rate_to_cny), axis=1)
                
                def fmt_cost(row):
                    if row['Is_Missing_Cost']: return "❌ 未录入"
                    return fmt_dual(row['Total_Cost'], row['Total_Cost']*rate_to_cny)
                def fmt_pro(row):
                    if row['Is_Missing_Cost']: return "❌ 待计算"
                    return fmt_dual(row['Net_Profit'], row['Net_Profit']*rate_to_cny)

                disp['Cost_Dual'] = disp.apply(fmt_cost, axis=1)
                disp['Profit_Dual'] = disp.apply(fmt_pro, axis=1)
                
                final_view = disp[['Date', 'Order ID', 'SKU', 'Quantity', 'Revenue_Dual', 'Settlement_Dual', 'Cost_Dual', 'Profit_Dual', 'Row_Status']]
                final_view.columns = ['日期', '订单号', 'SKU', '数量', f'销售额', f'回款', f'总成本', f'净利', 'Row_Status']
                
                def highlight_rows(row):
                    status = row['Row_Status']
                    style = ''
                    if status == 'Missing': style = 'background-color: #E8F5E9; color: #1B5E20' 
                    elif status == 'Canceled': style = 'background-color: #F3E5F5; color: #4A148C' 
                    elif status == 'Loss': style = 'background-color: #FFEBEE; color: #B71C1C' 
                    elif status == 'Low': style = 'background-color: #FFFDE7; color: #F57F17' 
                    return [style] * len(row)

                styled_df = final_view.style.apply(highlight_rows, axis=1)
                try: styled_df.hide(subset=['Row_Status'], axis=1)
                except: pass 
                st.dataframe(styled_df, use_container_width=True)
                
        elif uploaded_settlement:
            st.info("💡 暂无数据。")