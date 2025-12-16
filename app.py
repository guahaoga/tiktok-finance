import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import os
import sys
import subprocess
import io
import numpy as np
from PIL import Image

# ---------------------------------------------------------
# 0. 自动修复环境
# ---------------------------------------------------------
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

try:
    from PIL import Image
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image

# ---------------------------------------------------------
# 1. 基础配置
# ---------------------------------------------------------
st.set_page_config(page_title="TikTok 跨境财务系统", layout="wide", page_icon="🌏")

# 🔥 核心状态初始化
if "auth" not in st.session_state: st.session_state.auth = False
if 'product_df' not in st.session_state: st.session_state['product_df'] = None
if 'current_site' not in st.session_state: st.session_state['current_site'] = None
if 'filter_status' not in st.session_state: st.session_state['filter_status'] = 'All'
if 'show_qr' not in st.session_state: st.session_state['show_qr'] = False
# 共享数据区
if 'shared_df' not in st.session_state: st.session_state['shared_df'] = None

SITES = {
    "🇹🇭 泰国": {"symbol": "฿", "code": "THB", "sku_col": "SKU-泰国", "sheet_name": "泰国"},
    "🇻🇳 越南": {"symbol": "₫", "code": "VND", "sku_col": "SKU-越南", "sheet_name": "越南"},
    "🇵🇭 菲律宾": {"symbol": "₱", "code": "PHP", "sku_col": "SKU-菲律宾", "sheet_name": "菲律宾"},
    "🇲🇾 马来西亚": {"symbol": "RM", "code": "MYR", "sku_col": "SKU-马来", "sheet_name": "马来西亚"},
    "🇸🇬 新加坡": {"symbol": "S$", "code": "SGD", "sku_col": "SKU-新加坡", "sheet_name": "新加坡"},
}

DB_FILE = "my_costs_v3.csv" 
BACKUP_DIR = "backups"

# --- 🔐 安全登录锁 ---
def check_password():
    st.markdown("""<style>.stTextInput input {text-align: center;}</style>""", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.title("🔒 内部系统请登录")
        pwd = st.text_input("请输入访问密码", type="password")
        if st.button("登录", use_container_width=True, type="primary"):
            if pwd == "888888":  # 🔥 密码在这里修改
                st.session_state.auth = True
                st.rerun()
            else:
                st.error("密码错误")

if not st.session_state.auth:
    check_password()
    st.stop() 

# ---------------------------------------------------------
# 2. UI 美化
# ---------------------------------------------------------
st.markdown("""
<style> 
    .block-container {padding-top: 2rem !important; padding-bottom: 5rem;}
    div[data-testid="stSidebarNav"] {display: none;}
    
    .stButton button {
        min-height: 45px;
        font-weight: bold !important;
        border-radius: 8px !important;
        border: 1px solid #eee !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05) !important;
    }
    .stButton button:hover {
        border-color: #FF2D55 !important;
        color: #FF2D55 !important;
    }
    div[data-testid="stMetric"] {
        background: #fff; border: 1px solid #f0f0f0; border-radius: 8px;
        padding: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.03);
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 3. 核心函数
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

def load_product_db():
    if os.path.exists(DB_FILE):
        try:
            try: df = pd.read_csv(DB_FILE, dtype=str)
            except UnicodeDecodeError: df = pd.read_csv(DB_FILE, encoding='gbk', dtype=str)
            return clean_df_types(df)
        except: return clean_df_types(pd.DataFrame())
    else: return clean_df_types(pd.DataFrame([{"商品名称": "示例", "采购成本(CNY)": 10.0, "SKU-泰国": "Test-001"}]))

def create_backup():
    if not os.path.exists(BACKUP_DIR): os.makedirs(BACKUP_DIR)
    if os.path.exists(DB_FILE):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy(DB_FILE, os.path.join(BACKUP_DIR, f"cost_backup_{timestamp}.csv"))
        backups = sorted([os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR)], key=os.path.getmtime)
        if len(backups) > 20: os.remove(backups[0])

def save_product_db(df):
    try:
        create_backup()
        df.to_csv(DB_FILE, index=False)
        return True
    except Exception as e:
        st.error(f"保存失败: {e}")
        return False

def generate_excel_template():
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for site_info in SITES.values():
            sheet_name = site_info['sheet_name']
            df_template = pd.DataFrame({"商品名称 (必填)": ["示例A"], "采购成本(CNY)": [10.5], "SKU ID": ["SKU-1001"]})
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
                if master_df.empty: master_df = temp_df
                else:
                    master_df = pd.merge(master_df, temp_df, on="商品名称", how="outer")
                    if "采购成本(CNY)_y" in master_df.columns:
                        master_df["采购成本(CNY)"] = master_df["采购成本(CNY)_y"].fillna(master_df["采购成本(CNY)_x"])
                        master_df = master_df.drop(columns=["采购成本(CNY)_x", "采购成本(CNY)_y"])
    return clean_df_types(master_df)

def load_order_files(uploaded_files):
    if not uploaded_files: return None
    all_dfs = []
    try:
        for file in uploaded_files:
            if file.name.lower().endswith('.csv'):
                try: temp = pd.read_csv(file)
                except: file.seek(0); temp = pd.read_csv(file, encoding='gbk')
            else: temp = pd.read_excel(file, engine='openpyxl')
            all_dfs.append(temp)
        if all_dfs:
            return pd.concat(all_dfs, ignore_index=True)
    except Exception as e:
        st.error(f"读取文件失败: {e}")
    return None

if st.session_state['product_df'] is None: st.session_state['product_df'] = load_product_db()

# ---------------------------------------------------------
# 4. 界面逻辑
# ---------------------------------------------------------

if st.session_state['current_site'] is None:
    st.markdown("<style>div[data-testid='stSidebar'] {display: none;}</style>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; margin-top: 50px;'>🌏 TikTok 财务中台</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #888; margin-bottom: 50px;'>请选择您要查看的站点</p>", unsafe_allow_html=True)
    
    site_list = list(SITES.keys())
    c1, c2, c3 = st.columns(3)
    if c1.button(site_list[0], use_container_width=True, type="primary"): st.session_state['current_site'] = site_list[0]; st.rerun()
    if c2.button(site_list[1], use_container_width=True, type="primary"): st.session_state['current_site'] = site_list[1]; st.rerun()
    if c3.button(site_list[2], use_container_width=True, type="primary"): st.session_state['current_site'] = site_list[2]; st.rerun()
    st.write("") 
    _, c4, c5, _ = st.columns([0.5, 1, 1, 0.5])
    if c4.button(site_list[3], use_container_width=True, type="primary"): st.session_state['current_site'] = site_list[3]; st.rerun()
    if c5.button(site_list[4], use_container_width=True, type="primary"): st.session_state['current_site'] = site_list[4]; st.rerun()

    st.markdown("---")
    _, c_center, _ = st.columns([2, 2, 2])
    if c_center.button("📝 管理全球商品成本库", type="secondary", use_container_width=True):
        st.session_state['current_site'] = "Global_Config"
        st.rerun()

else:
    with st.sidebar:
        st.title("功能菜单")
        st.markdown("---")
        if st.session_state['current_site'] == "Global_Config":
            app_mode = "📝 商品成本库"
        else:
            app_mode = st.radio("📍 导航", ["📊 财务看板", "📊 按照结算单汇总", "📝 商品成本库"], index=0)
        st.markdown("---")
        if st.session_state['current_site'] != "Global_Config":
            site_code = SITES[st.session_state['current_site']]['code']
            rate = get_exchange_rate(site_code)
            st.metric(f"当前汇率 ({site_code})", f"1 : {rate:.4f}", "CNY")
            st.divider()
        if st.button("🔙 返回首页", use_container_width=True):
            st.session_state['current_site'] = None
            st.session_state['shared_df'] = None 
            st.rerun()

    # === 页面 A: 商品成本库 ===
    if app_mode == "📝 商品成本库":
        st.title("📝 全球商品成本数据库")
        with st.expander("📥 **下载 Excel 模板**", expanded=True):
            st.download_button("👉 点击下载标准模板.xlsx", generate_excel_template(), "TikTok_Template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with st.expander("📂 **导入本地 Excel (自动合并)**", expanded=True):
            uploaded_cost_file = st.file_uploader("上传 Excel 文件", type=['xlsx'])
            if uploaded_cost_file and st.button("⚠️ 确认导入"):
                try:
                    new_df = parse_multisheet_excel(uploaded_cost_file)
                    save_product_db(new_df)
                    st.session_state['product_df'] = new_df
                    st.success("✅ 导入成功！")
                    st.rerun()
                except Exception as e: st.error(f"导入失败: {e}")
        st.markdown("---")
        if not st.session_state['product_df'].empty:
            current_csv = st.session_state['product_df'].to_csv(index=False).encode('utf-8-sig')
            st.download_button("💾 备份/下载当前数据 (CSV)", data=current_csv, file_name="my_costs_backup.csv", mime="text/csv", type="primary")
        edited_df = st.data_editor(st.session_state['product_df'], num_rows="dynamic", use_container_width=True, height=600, hide_index=True)
        if not edited_df.equals(st.session_state['product_df']):
            if not edited_df.empty:
                save_product_db(edited_df)
                st.session_state['product_df'] = edited_df
                st.toast("✅ 已保存", icon="💾")

    # ==========================
    # 共享数据处理逻辑
    # ==========================
    elif app_mode in ["📊 财务看板", "📊 按照结算单汇总"]:
        current_site = st.session_state['current_site']
        site_conf = SITES[current_site]
        symbol = site_conf['symbol']
        code = site_conf['code']
        target_sku_col = site_conf['sku_col']
        rate_to_cny = get_exchange_rate(code)

        with st.sidebar:
            st.subheader("📂 数据中心")
            if st.session_state['shared_df'] is not None:
                row_count = len(st.session_state['shared_df'])
                st.success(f"✅ 已加载 {row_count} 条数据")
                if st.button("🗑️ 清空数据", type="primary"):
                    st.session_state['shared_df'] = None
                    st.rerun()
            else:
                st.info("💡 暂无数据，请上传")

            uploaded_files = st.file_uploader(
                f"上传 {current_site} 订单 (支持批量拖拽)", 
                type=['xlsx', 'csv'], 
                accept_multiple_files=True,
                key=f"uploader_{app_mode}"
            )
            
            if uploaded_files:
                new_df = load_order_files(uploaded_files)
                if new_df is not None:
                    st.session_state['shared_df'] = new_df

        df_merged = None
        df_raw = st.session_state['shared_df']

        if df_raw is not None:
            try:
                cols_s = df_raw.columns.tolist()
                def find(keys):
                    for c in cols_s: 
                        if any(k in c for k in keys): return c
                    return None

                col_sku = find(['SKU ID', 'SKU', 'Seller SKU'])
                col_amt = find(['Total settlement amount', 'Settlement amount', 'Amount'])
                col_rev = find(['Total Revenue', 'Revenue', 'Product Revenue'])
                col_date = find(['Statement Date', 'Time', 'Date'])
                col_order = find(['Order/adjustment ID', 'Order ID', '订单号'])
                col_qty = find(['Quantity', 'Qty', '数量'])
                col_stmt = find(['Statement ID', '结算单号', 'Statement'])

                if col_sku and col_amt:
                    df_c = pd.DataFrame()
                    df_c['Order ID'] = df_raw[col_order].astype(str).replace('nan', '') if col_order else "Unknown"
                    df_c['SKU'] = df_raw[col_sku].astype(str).str.strip()
                    df_c['Statement ID'] = df_raw[col_stmt].astype(str).replace('nan', '').str.replace(r'\.0$', '', regex=True) if col_stmt else "Unknown"
                    df_c['Settlement Amount'] = pd.to_numeric(df_raw[col_amt], errors='coerce').fillna(0)
                    df_c['Revenue'] = pd.to_numeric(df_raw[col_rev], errors='coerce').fillna(0) if col_rev else 0
                    df_c['Quantity'] = pd.to_numeric(df_raw[col_qty], errors='coerce').fillna(0) if col_qty else 1
                    
                    if col_date:
                        df_c['Date'] = pd.to_datetime(df_raw[col_date], errors='coerce')
                        df_c['Month'] = df_c['Date'].dt.strftime('%Y-%m')
                    else:
                        df_c['Date'] = pd.NaT
                        df_c['Month'] = "Unknown"

                    pdb = st.session_state['product_df']
                    if target_sku_col in pdb.columns:
                        valid = pdb[pdb[target_sku_col].notna()].copy()
                        valid['SKU'] = valid[target_sku_col].astype(str).str.strip()
                        valid['Cost_CNY'] = valid["采购成本(CNY)"]
                        valid['商品名称'] = valid['商品名称'].astype(str).str.strip()
                        
                        df_merged = pd.merge(df_c, valid[['SKU', 'Cost_CNY', '商品名称']], on='SKU', how='left')
                        
                        df_merged['Is_Missing_Cost'] = df_merged['Cost_CNY'].isna()
                        df_merged['Cost_CNY'] = df_merged['Cost_CNY'].fillna(0)
                        df_merged['Cost_Local_Unit'] = df_merged['Cost_CNY'] / rate_to_cny if rate_to_cny else 0
                        df_merged['Total_Cost'] = df_merged['Cost_Local_Unit'] * df_merged['Quantity']
                        
                        # 取消订单
                        cancel_mask = (df_merged['Revenue'] == 0) & (df_merged['Settlement Amount'] == 0)
                        df_merged.loc[cancel_mask, 'Total_Cost'] = 0
                        df_merged['Is_Canceled'] = cancel_mask

                        # 拒收订单
                        reject_mask = (df_merged['Revenue'] == 0) & (df_merged['Settlement Amount'] < 0)
                        df_merged['Is_Rejected'] = reject_mask
                        
                        df_merged['Net_Profit'] = df_merged['Settlement Amount'] - df_merged['Total_Cost']
                        
                        conditions = [
                            df_merged['Is_Missing_Cost'],
                            df_merged['Is_Rejected'],
                            df_merged['Is_Canceled'],
                            (df_merged['Net_Profit'] < 0) & (~df_merged['Is_Missing_Cost']) & (~df_merged['Is_Rejected']) & (~df_merged['Is_Canceled']),
                            (df_merged['Net_Profit']*rate_to_cny > 0) & (df_merged['Net_Profit']*rate_to_cny < 2) & (~df_merged['Is_Missing_Cost'])
                        ]
                        choices = ['Missing', 'Rejected', 'Canceled', 'Loss', 'Low']
                        df_merged['Row_Status'] = np.select(conditions, choices, default='Normal')

            except Exception as e:
                st.error(f"数据解析错误: {e}")

        # ==========================
        # 页面 B: 财务看板
        # ==========================
        if app_mode == "📊 财务看板":
            st.title(f"📊 {current_site} 经营看板")
            st.caption(f"核算货币: {code} | 汇率: 1 {code} ≈ {rate_to_cny:.4f} CNY")
            st.markdown("---")

            if df_merged is not None:
                df_valid = df_merged[~df_merged['Is_Missing_Cost']]
                
                tot_sales = df_valid['Revenue'].sum()
                tot_rev = df_valid['Settlement Amount'].sum()
                tot_pro = df_valid['Net_Profit'].sum()
                margin_sales = (tot_pro / tot_sales * 100) if tot_sales else 0
                margin_settle = (tot_pro / tot_rev * 100) if tot_rev else 0
                
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("💰 总销售额", f"{symbol} {tot_sales:,.0f}", f"≈ ¥ {tot_sales*rate_to_cny:,.0f}")
                k2.metric("💵 总回款", f"{symbol} {tot_rev:,.0f}", f"≈ ¥ {tot_rev*rate_to_cny:,.0f}")
                k3.metric("🧧 净利润", f"{symbol} {tot_pro:,.0f}", f"≈ ¥ {tot_pro*rate_to_cny:,.0f}")
                k4.metric("📊 总订单量", f"{len(df_merged)}")
                
                k5, k6, k7, k8 = st.columns(4)
                k5.metric("📉 销售额利润率", f"{margin_sales:.1f}%")
                k6.metric("💰 回款利润率", f"{margin_settle:.1f}%")
                
                count_rej = df_merged['Is_Rejected'].sum()
                rate_rej = (count_rej / len(df_merged) * 100) if len(df_merged) > 0 else 0
                k7.metric("⛔ 拒收单量", f"{count_rej}")
                k8.metric("📉 拒收率", f"{rate_rej:.1f}%")

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
                    m1.metric("🛡️ 投流保本 ROI", f"{roi:.2f}", help="及格线 (GMV/毛利)")
                    m2.metric("🚀 实际投放 ROI", f"{actual_roi:.2f}", help="成绩单 (GMV/广告费)")
                    m3.metric("💰 实际到手利润", f"¥ {real_pro:,.2f}", delta=f"-{ad_spend}", delta_color="normal")
                    m4.metric("📉 实际净利率", f"{real_m:.1f}%")

                st.markdown("###")
                tab1, tab2 = st.tabs(["📊 利润趋势", "📋 订单明细"])
                with tab1:
                    if 'Month' in df_merged and df_merged['Month'].notna().any():
                        g = df_merged[~df_merged['Is_Missing_Cost']].groupby('Month')[['Settlement Amount', 'Net_Profit']].sum().reset_index()
                        
                        # 🔥🔥🔥 图表优化代码 🔥🔥🔥
                        plot_data = []
                        for idx, row in g.iterrows():
                            # 回款
                            plot_data.append({
                                '月份': row['Month'],
                                '指标': '总回款',
                                '数值': row['Settlement Amount'],
                                '数值(CNY)': row['Settlement Amount'] * rate_to_cny
                            })
                            # 利润
                            plot_data.append({
                                '月份': row['Month'],
                                '指标': '净利润',
                                '数值': row['Net_Profit'],
                                '数值(CNY)': row['Net_Profit'] * rate_to_cny
                            })
                        
                        df_plot = pd.DataFrame(plot_data)
                        
                        fig = px.bar(
                            df_plot,
                            x='月份',
                            y='数值',
                            color='指标',
                            barmode='group',
                            text_auto='.2s',
                            title=f'{current_site} 经营趋势 (结算币种: {code})',
                            labels={'数值': f'金额 ({symbol})', '月份': '时间'},
                            color_discrete_map={'总回款': '#3498DB', '净利润': '#2ECC71'} # 蓝绿配色
                        )
                        # 双币种悬停显示
                        fig.update_traces(
                            hovertemplate="<b>%{x}</b><br>%{data.name}: %{y:,.2f} " + symbol + "<br>≈ ¥%{customdata[0]:,.2f}",
                            customdata=df_plot[['数值(CNY)']]
                        )
                        fig.update_layout(xaxis_title="", yaxis_title="")
                        st.plotly_chart(fig, use_container_width=True)

                with tab2:
                    st.markdown("#### 🏆 商品经营效能分析 (按商品名称聚合)")
                    df_product_analysis = df_merged[(~df_merged['Is_Missing_Cost']) & (~df_merged['Is_Canceled'])].copy()
                    if not df_product_analysis.empty:
                        df_product_analysis['商品名称'] = df_product_analysis['商品名称'].fillna(df_product_analysis['SKU'])
                        df_pro_agg = df_product_analysis.groupby('商品名称').agg({'Quantity': 'sum', 'Revenue': 'sum', 'Net_Profit': 'sum'}).reset_index()
                        df_pro_agg['保本ROI'] = df_pro_agg.apply(lambda x: (x['Revenue'] / x['Net_Profit']) if x['Net_Profit'] > 0 else 0, axis=1)
                        df_pro_agg['单均利润'] = df_pro_agg['Net_Profit'] / df_pro_agg['Quantity']
                        df_pro_agg['净利率'] = df_pro_agg.apply(lambda x: (x['Net_Profit'] / x['Revenue']) if x['Revenue'] > 0 else 0, axis=1)
                        
                        df_pro_agg = df_pro_agg.sort_values('Quantity', ascending=False)
                        def fmt_pro_dual(row, col):
                            val_local = row[col]; val_cny = val_local * rate_to_cny
                            return f"{symbol} {val_local:,.0f} (¥{val_cny:,.0f})"
                        df_pro_agg['总销售额'] = df_pro_agg.apply(lambda x: fmt_pro_dual(x, 'Revenue'), axis=1)
                        df_pro_agg['总毛利'] = df_pro_agg.apply(lambda x: fmt_pro_dual(x, 'Net_Profit'), axis=1)
                        df_pro_agg['平均订单利润'] = df_pro_agg.apply(lambda x: fmt_pro_dual(x, '单均利润'), axis=1)
                        df_pro_agg['平均净利率'] = (df_pro_agg['净利率'] * 100).map('{:.1f}%'.format)
                        df_pro_agg['平均保本ROI'] = df_pro_agg['保本ROI'].apply(lambda x: f"{x:.2f}" if x > 0 else "亏损")
                        st.dataframe(df_pro_agg[['商品名称', 'Quantity', '总销售额', '总毛利', '平均订单利润', '平均净利率', '平均保本ROI']].rename(columns={'Quantity': '总销量'}), use_container_width=True, hide_index=True)
                    
                    st.divider()
                    st.markdown("##### 🔍 订单流水明细")
                    f1, f2, f3, f4, f5, f6, f7 = st.columns(7)
                    filter_choice = st.session_state['filter_status']
                    def set_filter(val): st.session_state['filter_status'] = val
                    
                    c_all = len(df_merged)
                    c_norm = len(df_merged[df_merged['Row_Status']=='Normal'])
                    c_loss = len(df_merged[df_merged['Row_Status']=='Loss'])
                    c_low = len(df_merged[df_merged['Row_Status']=='Low'])
                    c_rej = len(df_merged[df_merged['Row_Status']=='Rejected'])
                    c_cancel = len(df_merged[df_merged['Row_Status']=='Canceled'])
                    c_miss = len(df_merged[df_merged['Row_Status']=='Missing'])

                    f1.button(f"📋 全部 ({c_all})", type="primary" if filter_choice=='All' else "secondary", on_click=set_filter, args=('All',), use_container_width=True)
                    f2.button(f"✅ 正常 ({c_norm})", type="primary" if filter_choice=='Normal' else "secondary", on_click=set_filter, args=('Normal',), use_container_width=True)
                    f3.button(f"🟥 亏损 ({c_loss})", type="primary" if filter_choice=='Loss' else "secondary", on_click=set_filter, args=('Loss',), use_container_width=True)
                    f4.button(f"🟨 低利 ({c_low})", type="primary" if filter_choice=='Low' else "secondary", on_click=set_filter, args=('Low',), use_container_width=True)
                    f5.button(f"⛔ 拒收 ({c_rej})", type="primary" if filter_choice=='Rejected' else "secondary", on_click=set_filter, args=('Rejected',), use_container_width=True)
                    f6.button(f"🟪 取消 ({c_cancel})", type="primary" if filter_choice=='Canceled' else "secondary", on_click=set_filter, args=('Canceled',), use_container_width=True)
                    f7.button(f"🟩 缺成本 ({c_miss})", type="primary" if filter_choice=='Missing' else "secondary", on_click=set_filter, args=('Missing',), use_container_width=True)
                    
                    if filter_choice == 'All': filtered_df = df_merged
                    else: filtered_df = df_merged[df_merged['Row_Status'] == filter_choice]
                    
                    disp = filtered_df.copy().sort_values('Date', ascending=False)
                    def fmt_dual(local, cny): return f"{symbol} {local:,.2f} (¥ {cny:,.2f})" if not pd.isna(cny) else "未录入"
                    disp['Revenue_Dual'] = disp.apply(lambda x: fmt_dual(x['Revenue'], x['Revenue']*rate_to_cny), axis=1)
                    disp['Settlement_Dual'] = disp.apply(lambda x: fmt_dual(x['Settlement Amount'], x['Settlement Amount']*rate_to_cny), axis=1)
                    def fmt_cost(row): return "❌ 未录入" if row['Is_Missing_Cost'] else fmt_dual(row['Total_Cost'], row['Total_Cost']*rate_to_cny)
                    def fmt_pro(row): return "❌ 待计算" if row['Is_Missing_Cost'] else fmt_dual(row['Net_Profit'], row['Net_Profit']*rate_to_cny)
                    disp['Cost_Dual'] = disp.apply(fmt_cost, axis=1)
                    disp['Profit_Dual'] = disp.apply(fmt_pro, axis=1)
                    
                    final_view = disp[['Date', 'Order ID', '商品名称', 'Quantity', 'Revenue_Dual', 'Settlement_Dual', 'Cost_Dual', 'Profit_Dual', 'Row_Status']]
                    final_view.columns = ['日期', '订单号', '商品名称', '数量', f'销售额', f'回款', f'总成本', f'净利', 'Row_Status']
                    
                    def highlight_rows(row):
                        status = row['Row_Status']
                        if status == 'Missing': return ['background-color: #E8F5E9; color: #1B5E20'] * len(row)
                        if status == 'Canceled': return ['background-color: #F3E5F5; color: #4A148C'] * len(row)
                        if status == 'Loss': return ['background-color: #FFEBEE; color: #B71C1C'] * len(row)
                        if status == 'Low': return ['background-color: #FFFDE7; color: #F57F17'] * len(row)
                        if status == 'Rejected': return ['background-color: #8D6E63; color: #FFFFFF'] * len(row)
                        return [''] * len(row)
                    st.dataframe(final_view.style.apply(highlight_rows, axis=1), use_container_width=True)
            else:
                st.info("💡 请在左侧上传数据文件。")

        # ==========================
        # 页面 C: 按照结算单汇总
        # ==========================
        elif app_mode == "📊 按照结算单汇总":
            st.title(f"📊 {current_site} 结算单批量对账")
            st.caption(f"核算货币: {code} | 汇率: 1 {code} ≈ {rate_to_cny:.4f} CNY")
            st.markdown("---")

            if df_merged is not None:
                # 过滤无效数据用于汇总
                df_valid = df_merged[~df_merged['Is_Missing_Cost']]
                
                # 聚合计算
                df_stmt = df_valid.groupby('Statement ID').agg({
                    'Revenue': 'sum', 
                    'Settlement Amount': 'sum', 
                    'Total_Cost': 'sum', 
                    'Net_Profit': 'sum', 
                    'Quantity': 'sum'
                }).reset_index()
                
                df_stmt['销售利润率%'] = (df_stmt['Net_Profit'] / df_stmt['Revenue'] * 100).fillna(0).round(1)
                df_stmt['回款利润率%'] = (df_stmt['Net_Profit'] / df_stmt['Settlement Amount'] * 100).fillna(0).round(1)
                
                g_sales = df_stmt['Revenue'].sum()
                g_settle = df_stmt['Settlement Amount'].sum()
                g_profit = df_stmt['Net_Profit'].sum()
                g_m_sales = (g_profit / g_sales * 100) if g_sales else 0
                g_m_settle = (g_profit / g_settle * 100) if g_settle else 0
                
                st.markdown("#### 💰 总账汇总")
                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("总销售额", f"{symbol} {g_sales:,.0f}", f"≈ ¥ {g_sales*rate_to_cny:,.0f}")
                k2.metric("总回款", f"{symbol} {g_settle:,.0f}", f"≈ ¥ {g_settle*rate_to_cny:,.0f}")
                k3.metric("总净利润", f"{symbol} {g_profit:,.0f}", f"≈ ¥ {g_profit*rate_to_cny:,.0f}")
                k4.metric("总销售利润率", f"{g_m_sales:.1f}%")
                k5.metric("总回款利润率", f"{g_m_settle:.1f}%")
                
                st.markdown("---")
                c_ad1, c_ad2 = st.columns([1, 4])
                with c_ad1: g_ad = st.number_input("👉 投入总广告费 (¥)", 0.0, step=100.0)
                with c_ad2:
                    g_pro_cny = g_profit * rate_to_cny
                    g_sales_cny = g_sales * rate_to_cny
                    g_roi = (g_sales_cny / g_ad) if g_ad > 0 else 0
                    g_real_pro = g_pro_cny - g_ad
                    m1, m2 = st.columns(2)
                    m1.metric("🚀 整体实际 ROI", f"{g_roi:.2f}")
                    m2.metric("💰 实际到手利润", f"¥ {g_real_pro:,.2f}", delta=f"-{g_ad}", delta_color="normal")

                st.markdown("#### 📋 各结算单明细")
                st.markdown("---")
                
                disp_stmt = df_stmt.copy()
                def fmt_dual_list(val): return f"{symbol} {val:,.2f} (¥ {val * rate_to_cny:,.2f})"
                disp_stmt['总销售额'] = disp_stmt['Revenue'].apply(fmt_dual_list)
                disp_stmt['总回款'] = disp_stmt['Settlement Amount'].apply(fmt_dual_list)
                disp_stmt['总成本'] = disp_stmt['Total_Cost'].apply(fmt_dual_list)
                disp_stmt['总净利'] = disp_stmt['Net_Profit'].apply(fmt_dual_list)
                disp_stmt = disp_stmt.rename(columns={'Statement ID': '结算单号', 'Quantity': '订单量'})
                st.dataframe(disp_stmt[['结算单号', '总销售额', '总回款', '总成本', '总净利', '销售利润率%', '回款利润率%', '订单量']], use_container_width=True, hide_index=True)

                st.markdown("---")
                st.subheader("🔍 查看特定结算单明细 (穿透查询)")
                stmt_list = ["(请选择结算单号)"] + sorted(df_stmt['Statement ID'].unique().tolist())
                selected_stmt = st.selectbox("👇 选择结算单号，查看具体订单详情：", stmt_list)
                
                if selected_stmt != "(请选择结算单号)":
                    detail_df = df_merged[df_merged['Statement ID'] == selected_stmt].copy()
                    def fmt_dual(local, cny): return f"{symbol} {local:,.2f} (¥ {cny:,.2f})" if not pd.isna(cny) else "未录入"
                    detail_df['Rev_Dual'] = detail_df.apply(lambda x: fmt_dual(x['Revenue'], x['Revenue']*rate_to_cny), axis=1)
                    detail_df['Settle_Dual'] = detail_df.apply(lambda x: fmt_dual(x['Settlement Amount'], x['Settlement Amount']*rate_to_cny), axis=1)
                    def fmt_c(r): return "❌ 未录入" if r['Is_Missing_Cost'] else fmt_dual(r['Total_Cost'], r['Total_Cost']*rate_to_cny)
                    def fmt_p(r): return "❌ 待计算" if r['Is_Missing_Cost'] else fmt_dual(r['Net_Profit'], r['Net_Profit']*rate_to_cny)
                    detail_df['Cost_Dual'] = detail_df.apply(fmt_c, axis=1)
                    detail_df['Pro_Dual'] = detail_df.apply(fmt_p, axis=1)
                    
                    final_detail = detail_df[['Date', 'Order ID', 'SKU', '商品名称', 'Quantity', 'Rev_Dual', 'Settle_Dual', 'Cost_Dual', 'Pro_Dual', 'Row_Status']]
                    final_detail.columns = ['日期', '订单号', 'SKU', '商品名称', '数量', '销售额', '回款', '总成本', '净利', 'Row_Status']
                    def highlight_rows(row):
                        status = row['Row_Status']
                        if status == 'Missing': return ['background-color: #E8F5E9; color: #1B5E20'] * len(row)
                        if status == 'Canceled': return ['background-color: #F3E5F5; color: #4A148C'] * len(row)
                        if status == 'Loss': return ['background-color: #FFEBEE; color: #B71C1C'] * len(row)
                        if status == 'Low': return ['background-color: #FFFDE7; color: #F57F17'] * len(row)
                        if status == 'Rejected': return ['background-color: #8D6E63; color: #FFFFFF'] * len(row)
                        return [''] * len(row)
                    st.write(f"🧾 结算单 **{selected_stmt}** 的订单明细：")
                    st.dataframe(final_detail.style.apply(highlight_rows, axis=1), use_container_width=True)
                    st.caption("🎨 图例说明：🟫 棕色 = 拒收/配送失败 | 🟥 红色 = 亏损 | 🟨 黄色 = 低利 (<2元) | 🟪 紫色 = 取消/未发货 | 🟩 绿色 = 缺成本")
            else:
                st.info("💡 请在左侧上传数据文件。")
