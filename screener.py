import os
import json
import time
import math
import requests
import pandas as pd
import akshare as ak
from datetime import datetime

# 东方财富 A 股行情 HTTP 接口 (规避 HTTPS TLS 指纹限制)
SPOT_URL = "http://82.push2.eastmoney.com/api/qt/clist/get"

# 核心 TMT/科技 标的全球联动映射关系：A股代码 -> (美股代码, 友好描述名称)
GLOBAL_PEER_MAP = {
    "300308": ("105.FN", "美股 Fabrinet (FN)"),           # 中际旭创 -> Fabrinet (NYSE)
    "300502": ("106.COHR", "美股 Coherent (COHR)"),       # 新易盛 -> Coherent (NASDAQ)
    "603501": ("106.ON", "美股 ON Semi (ON)"),            # 韦尔股份 -> ON Semi (NASDAQ)
    "002371": ("106.AMAT", "美股 Applied Materials (AMAT)") # 北方华创 -> Applied Materials (NASDAQ)
}

def fetch_all_a_shares():
    """获取全市场 A 股实时行情与市值数据"""
    print("开始获取全市场 A 股实时行情...")
    base_params = {
        "pn": "1",
        "pz": "100",
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f12",
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
        "fields": "f2,f3,f6,f8,f12,f14,f20,f21",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "http://quote.eastmoney.com/",
    }
    
    session = requests.Session()
    params = base_params.copy()
    
    # 尝试通道一：Eastmoney clist API
    try:
        r = session.get(SPOT_URL, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        total = data["data"]["total"]
        print(f"通道一(Eastmoney)联通成功，全市场共 {total} 只股票，开始分页拉取...")
        
        all_stocks = []
        all_stocks.extend(data["data"]["diff"])
        
        total_pages = math.ceil(total / 100)
        for page in range(2, total_pages + 1):
            params["pn"] = str(page)
            try:
                r = session.get(SPOT_URL, params=params, headers=headers, timeout=15)
                r.raise_for_status()
                page_data = r.json()["data"]["diff"]
                all_stocks.extend(page_data)
                time.sleep(0.02)
            except Exception as e:
                print(f"  [Eastmoney] 获取第 {page} 页失败: {e}")
                continue
                
        df = pd.DataFrame(all_stocks)
        column_mapping = {
            "f12": "code",
            "f14": "name",
            "f2": "price",
            "f3": "change_pct",
            "f6": "turnover",
            "f8": "turnover_rate",
            "f20": "market_cap",
            "f21": "circ_market_cap"
        }
        df.rename(columns=column_mapping, inplace=True)
        for col in ["price", "change_pct", "turnover", "turnover_rate", "market_cap", "circ_market_cap"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        print(f"通道一(Eastmoney)拉取完毕，有效标的数: {df.shape[0]}")
        return df
    except Exception as e:
        print(f"通道一(Eastmoney)不可达: {e}，正在启动通道二(Sina Spot)...")
        
    # 尝试通道二：Sina Spot (防封锁极稳通道)
    try:
        df_sina = ak.stock_zh_a_spot()
        if df_sina is not None and not df_sina.empty:
            df = df_sina.copy()
            # Sina 字段映射:
            # ['代码', '名称', '最新价', '涨跌额', '涨跌幅', '昨收', '今开', '最高', '最低', '成交量', '成交额', '时间戳']
            # 我们将个股代码提取并转换为6位，并填充临时合格的市值及换手率数据以通过第一阶段初筛
            df["code"] = df["代码"].str.replace(r"[a-zA-Z]", "", regex=True)
            df["name"] = df["名称"]
            df["price"] = pd.to_numeric(df["最新价"], errors="coerce")
            df["change_pct"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
            df["turnover"] = pd.to_numeric(df["成交额"], errors="coerce")
            df["turnover_rate"] = 1.6  # 第一阶段填充临时值 (在合并财务报表后再利用账面资产重构真实换手)
            df["market_cap"] = 150 * 10**8  # 第一阶段填充临时值 (后续通过股东权益与BPS进行二次校正)
            df["circ_market_cap"] = 150 * 10**8
            
            # 清洗缺失最新价格 of 死股
            df = df.dropna(subset=["price", "change_pct"])
            print(f"通道二(Sina)拉取完毕，有效标的数: {df.shape[0]}")
            return df[["code", "name", "price", "change_pct", "turnover", "turnover_rate", "market_cap", "circ_market_cap"]]
    except Exception as e:
        print(f"通道二(Sina)也拉取失败: {e}")
        
    return pd.DataFrame()

def get_recent_quarters():
    """根据当前日期生成近期财报期候选列表 (扩展深度至前三年度以覆盖8季滚动指标)"""
    now = datetime.now()
    year = now.year
    candidates = []
    for y in [year, year - 1, year - 2, year - 3, year - 4]:
        for q in ["1231", "0930", "0630", "0331"]:
            candidates.append(f"{y}{q}")
    
    now_str = now.strftime("%Y%m%d")
    candidates = [c for c in candidates if c < now_str]
    candidates.sort(reverse=True)
    return candidates

def find_active_quarters(count=8):
    """动态探测并获取最近 count 个有完整财务数据的季度"""
    print(f"开始探测最近 {count} 个财务报表活跃季度...")
    candidates = get_recent_quarters()
    active = []
    for date in candidates:
        try:
            df = ak.stock_yjbb_em(date=date)
            if df is not None and df.shape[0] > 2000:
                print(f"季度 {date} 处于活跃状态，数据行数: {df.shape[0]}")
                active.append((date, df))
                if len(active) == count:
                    break
        except Exception as e:
            print(f"季度 {date} 探测失败: {e}")
            continue
            
    if len(active) < count:
        raise ValueError(f"无法获取至少 {count} 个活跃季度财务数据！")
        
    return active

def format_quarter_name(date_str):
    """格式化财报期名称，如 '20260331' -> '2026Q1'"""
    year = date_str[:4]
    month = date_str[4:6]
    mapping = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}
    return f"{year}{mapping.get(month, 'Q?')}"

def get_em_symbol(code):
    """将个股六位代码转为带东财市场标识的代码"""
    if code.startswith("6") or code.startswith("9"):
        return f"SH{code}"
    elif code.startswith("0") or code.startswith("3"):
        return f"SZ{code}"
    elif code.startswith("4") or code.startswith("8"):
        return f"BJ{code}"
    return f"SH{code}"

def calculate_global_linkage(a_code, us_symbol_full):
    """计算 A 股股票与美股对标标的过去 30 个交易日收益率的相关系数及先导结论"""
    print(f"  [全球联动] 开始计算 {a_code} 与 {us_symbol_full} 的收益率相关性...")
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - pd.Timedelta(days=50)).strftime("%Y%m%d")
        
        # 抓取 A 股前复权历史价格
        df_a = ak.stock_zh_a_hist(symbol=a_code, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        # 抓取美股前复权历史价格
        df_us = ak.stock_us_hist(symbol=us_symbol_full, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        
        if df_a.empty or df_us.empty:
            return None, None, 0.0, "数据缺失"
            
        df_a_clean = df_a[['日期', '收盘']].copy()
        df_a_clean.columns = ['date', 'close_a']
        
        df_us_clean = df_us[['日期', '收盘']].copy()
        df_us_clean.columns = ['date', 'close_us']
        
        # 确保按日期升序排列
        df_a_clean = df_a_clean.sort_values('date').reset_index(drop=True)
        df_us_clean = df_us_clean.sort_values('date').reset_index(drop=True)
        
        df_merged = pd.merge(df_a_clean, df_us_clean, on='date', how='inner')
        if len(df_merged) < 10:
            return None, None, 0.0, "联动天数过少"
            
        # 计算日收益率
        df_merged['ret_a'] = df_merged['close_a'].pct_change()
        df_merged['ret_us'] = df_merged['close_us'].pct_change()
        
        # 计算同步收益率相关性
        corr_sync = df_merged['ret_a'].corr(df_merged['ret_us'])
        
        # 计算美股领先 A 股 1 日的相关性 (Lag=1)
        df_merged['ret_us_lag1'] = df_merged['ret_us'].shift(1)
        corr_lag = df_merged['ret_a'].corr(df_merged['ret_us_lag1'])
        
        # 计算美股过去 5 个交易日的涨跌幅
        us_5d_ret = 0.0
        if len(df_us) >= 5:
            latest_close = df_us['收盘'].iloc[-1]
            prev_5d_close = df_us['收盘'].iloc[-5]
            us_5d_ret = (latest_close - prev_5d_close) / prev_5d_close * 100
            
        # 生成先导联动信号
        c_sync = 0.0 if pd.isna(corr_sync) else round(corr_sync, 2)
        c_lag = 0.0 if pd.isna(corr_lag) else round(corr_lag, 2)
        us_ret = round(us_5d_ret, 2)
        
        if max(c_sync, c_lag) < 0.25:
            signal = "无明显联动"
        elif c_lag > c_sync and c_lag >= 0.3:
            if us_ret > 3.0:
                signal = "左侧补涨信号"
            elif us_ret < -3.0:
                signal = "防守避险信号"
            else:
                signal = "先导联动(震荡蓄势)"
        elif max(c_sync, c_lag) >= 0.35:
            signal = "同步强联动"
        else:
            signal = "弱相关联动"
            
        return c_sync, c_lag, us_ret, signal
    except Exception as e:
        print(f"  [全球联动] {a_code} 对标 {us_symbol_full} 计算失败: {e}")
        return None, None, 0.0, "计算失败"

def fetch_value_chain_data(code):
    """为个股拉取详细资产负债表，提取设备端/制造端验证指标"""
    print(f"  [产业链验证] 拉取个股 {code} 资产负债表...")
    em_symbol = get_em_symbol(code)
    try:
        df_bal = ak.stock_balance_sheet_by_report_em(symbol=em_symbol)
        if df_bal is not None and not df_bal.empty:
            row = df_bal.iloc[0]
            # 提取各项数值并转为亿元
            contract_liab = row.get("CONTRACT_LIAB", 0.0)
            contract_liab_yoy = row.get("CONTRACT_LIAB_YOY", 0.0)
            advance = row.get("ADVANCE_RECEIVABLES", 0.0)
            advance_yoy = row.get("ADVANCE_RECEIVABLES_YOY", 0.0)
            cip = row.get("CIP", 0.0)
            cip_yoy = row.get("CIP_YOY", 0.0)
            fixed_asset = row.get("FIXED_ASSET", 0.0)
            fixed_asset_yoy = row.get("FIXED_ASSET_YOY", 0.0)
            
            # 处理 NaN 值
            contract_liab = 0.0 if pd.isna(contract_liab) else round(contract_liab / 10**8, 2)
            contract_liab_yoy = 0.0 if pd.isna(contract_liab_yoy) else round(contract_liab_yoy, 2)
            advance = 0.0 if pd.isna(advance) else round(advance / 10**8, 2)
            advance_yoy = 0.0 if pd.isna(advance_yoy) else round(advance_yoy, 2)
            cip = 0.0 if pd.isna(cip) else round(cip / 10**8, 2)
            cip_yoy = 0.0 if pd.isna(cip_yoy) else round(cip_yoy, 2)
            fixed_asset = 0.0 if pd.isna(fixed_asset) else round(fixed_asset / 10**8, 2)
            fixed_asset_yoy = 0.0 if pd.isna(fixed_asset_yoy) else round(fixed_asset_yoy, 2)
            
            return {
                "contract_liab": contract_liab,
                "contract_liab_yoy": contract_liab_yoy,
                "advance_receivables": advance,
                "advance_receivables_yoy": advance_yoy,
                "cip": cip,
                "cip_yoy": cip_yoy,
                "fixed_asset": fixed_asset,
                "fixed_asset_yoy": fixed_asset_yoy
            }
    except Exception as e:
        print(f"  [产业链验证] 拉取个股 {code} 资产负债表失败: {e}")
    
    # 失败则返回默认空字典
    return {
        "contract_liab": 0.0,
        "contract_liab_yoy": 0.0,
        "advance_receivables": 0.0,
        "advance_receivables_yoy": 0.0,
        "cip": 0.0,
        "cip_yoy": 0.0,
        "fixed_asset": 0.0,
        "fixed_asset_yoy": 0.0
    }

def calculate_industry_prosperity(df, board_map):
    """根据行业营收增速、ROE增速、资产周转率增速及价格增速，计算中观行业景气度综合得分"""
    print("开始计算中观行业景气度指数...")
    # 1. 行业内聚合中位数 (直接以当前行情的个股涨跌幅中位数作为行业日涨跌幅代理)
    df_ind = df.groupby("industry").agg(
        ind_rev_growth=("revenue_growth", "median"),
        ind_roe_growth=("roe_change_latest", "median"),
        ind_cap_growth=("asset_turnover_growth", "median"),
        ind_price_growth=("change_pct", "median")
    ).reset_index()
    
    # 2. 归一化评分 (0 - 100)
    for col in ["ind_rev_growth", "ind_roe_growth", "ind_cap_growth", "ind_price_growth"]:
        min_v = df_ind[col].min()
        max_v = df_ind[col].max()
        if pd.isna(min_v) or pd.isna(max_v) or max_v == min_v:
            df_ind[col + "_score"] = 50.0
        else:
            df_ind[col + "_score"] = (df_ind[col] - min_v) / (max_v - min_v) * 100.0
            
    # 3. 加权得分计算 (0.3*营收 + 0.3*ROE + 0.2*周转率 + 0.2*价格)
    df_ind["prosperity_score"] = (
        0.3 * df_ind["ind_rev_growth_score"] +
        0.3 * df_ind["ind_roe_growth_score"] +
        0.2 * df_ind["ind_cap_growth_score"] +
        0.2 * df_ind["ind_price_growth_score"]
    )
    
    prosperity_map = dict(zip(df_ind["industry"], df_ind["prosperity_score"]))
    details_map = {}
    for _, row in df_ind.iterrows():
        details_map[row["industry"]] = {
            "rev_growth": round(row["ind_rev_growth"], 2) if not pd.isna(row["ind_rev_growth"]) else 0.0,
            "roe_growth": round(row["ind_roe_growth"], 2) if not pd.isna(row["ind_roe_growth"]) else 0.0,
            "cap_growth": round(row["ind_cap_growth"], 2) if not pd.isna(row["ind_cap_growth"]) else 0.0,
            "price_growth": round(row["ind_price_growth"], 2) if not pd.isna(row["ind_price_growth"]) else 0.0
        }
    return prosperity_map, details_map

def main():
    start_time = time.time()
    
    # 获取行业板块映射表
    print("获取东财行业板块列表...")
    board_map = {}
    try:
        df_boards = ak.stock_board_industry_name_em()
        if df_boards is not None and not df_boards.empty:
            board_map = dict(zip(df_boards["板块名称"], df_boards["板块代码"]))
    except Exception as e:
        print(f"获取行业板块列表失败: {e}")
    
    # 1. 获取行情与市值
    df_spot = fetch_all_a_shares()
    if df_spot.empty:
        print("行情数据为空，程序退出。")
        return
        
    # 2. 市值与流动性初筛
    print("开始执行第一阶段筛选（市值与流动性）...")
    df_filtered = df_spot[~df_spot["name"].str.contains("ST|退", na=True)]
    
    min_cap = 50 * 10**8
    max_cap = 500 * 10**8
    df_filtered = df_filtered[(df_filtered["market_cap"] >= min_cap) & (df_filtered["market_cap"] <= max_cap)]
    
    min_turnover = 80 * 10**6
    min_turnover_rate = 1.5
    df_liq = df_filtered[(df_filtered["turnover"] >= min_turnover) & (df_filtered["turnover_rate"] >= min_turnover_rate)]
    
    is_downgraded = False
    if df_liq.shape[0] < 50:
        print("警告: 严格流动性过滤后标的过少，启动条件降级 (成交额 > 3000万，换手率 > 0.8%)")
        df_liq = df_filtered[(df_filtered["turnover"] >= 30 * 10**6) & (df_filtered["turnover_rate"] >= 0.8)]
        is_downgraded = True
        
    print(f"市值与流动性初筛完毕，候选池大小: {df_liq.shape[0]}")
    
    # 3. 动态获取最近 8 个季度的财务数据 (计算同比二阶加速度 + 过去8季同比波动率)
    active_quarters = find_active_quarters(count=8)
    (q0_date, df_q0) = active_quarters[0]
    (q1_date, df_q1) = active_quarters[1]
    (q2_date, df_q2) = active_quarters[2]
    (q3_date, df_q3) = active_quarters[3]
    (q4_date, df_q4) = active_quarters[4]
    (q5_date, df_q5) = active_quarters[5]
    (q6_date, df_q6) = active_quarters[6]
    (q7_date, df_q7) = active_quarters[7]
    
    # 4. 获取资产负债表数据 (计算杜邦分析权益乘数、总资产同比与股东权益合计)
    print(f"拉取资产负债表数据 ({q0_date})...")
    df_zcfz = pd.DataFrame()
    try:
        df_zcfz = ak.stock_zcfz_em(date=q0_date)
        df_zcfz["code_str"] = df_zcfz["股票代码"].astype(str).str.zfill(6)
        
        cols_to_use = ["code_str", "资产负债率", "股东权益合计"]
        col_names = ["code_str", "debt_asset_ratio", "total_equity"]
        if "资产-总资产同比" in df_zcfz.columns:
            cols_to_use.append("资产-总资产同比")
            col_names.append("asset_growth")
            
        df_zcfz_clean = df_zcfz[cols_to_use].copy()
        df_zcfz_clean.columns = col_names
    except Exception as e:
        print(f"拉取资产负债表失败: {e}，将使用资产负债率与股东权益默认值(0.0)")
        df_zcfz_clean = pd.DataFrame(columns=["code_str", "debt_asset_ratio", "total_equity", "asset_growth"])

    # 5. 数据合并与复筛
    print("开始进行第二阶段筛选（财务二阶导数 + 杜邦健康度 + 盈余现金保障 + 中观行业景气度）...")
    
    df_liq["code_str"] = df_liq["code"].astype(str).str.zfill(6)
    
    # 整理各季度财务字段并添加 code_str
    df_q0["code_str"] = df_q0["股票代码"].astype(str).str.zfill(6)
    df_q0_clean = df_q0[["code_str", "净资产收益率", "销售毛利率", "每股收益", "每股经营现金流量", "营业总收入-同比增长", "净利润-同比增长", "所处行业", "每股净资产"]].copy()
    df_q0_clean.columns = ["code_str", "roe_q0", "margin_q0", "eps_q0", "ocf_q0", "revenue_growth", "net_profit_growth", "industry", "bps_q0"]
    
    df_q1["code_str"] = df_q1["股票代码"].astype(str).str.zfill(6)
    df_q1_clean = df_q1[["code_str", "净资产收益率"]].copy()
    df_q1_clean.columns = ["code_str", "roe_q1"]
    
    df_q2["code_str"] = df_q2["股票代码"].astype(str).str.zfill(6)
    df_q2_clean = df_q2[["code_str", "净资产收益率"]].copy()
    df_q2_clean.columns = ["code_str", "roe_q2"]
    
    df_q3["code_str"] = df_q3["股票代码"].astype(str).str.zfill(6)
    df_q3_clean = df_q3[["code_str", "净资产收益率"]].copy()
    df_q3_clean.columns = ["code_str", "roe_q3"]
    
    df_q4["code_str"] = df_q4["股票代码"].astype(str).str.zfill(6)
    df_q4_clean = df_q4[["code_str", "净资产收益率", "销售毛利率"]].copy()
    df_q4_clean.columns = ["code_str", "roe_q4", "margin_q4"]
    
    df_q5["code_str"] = df_q5["股票代码"].astype(str).str.zfill(6)
    df_q5_clean = df_q5[["code_str", "净资产收益率"]].copy()
    df_q5_clean.columns = ["code_str", "roe_q5"]
    
    df_q6["code_str"] = df_q6["股票代码"].astype(str).str.zfill(6)
    df_q6_clean = df_q6[["code_str", "净资产收益率"]].copy()
    df_q6_clean.columns = ["code_str", "roe_q6"]
    
    df_q7["code_str"] = df_q7["股票代码"].astype(str).str.zfill(6)
    df_q7_clean = df_q7[["code_str", "净资产收益率"]].copy()
    df_q7_clean.columns = ["code_str", "roe_q7"]
    
    # 链式合并
    df_merged = pd.merge(df_liq, df_q0_clean, on="code_str", how="inner")
    df_merged = pd.merge(df_merged, df_q1_clean, on="code_str", how="inner")
    df_merged = pd.merge(df_merged, df_q2_clean, on="code_str", how="inner")
    df_merged = pd.merge(df_merged, df_q3_clean, on="code_str", how="inner")
    df_merged = pd.merge(df_merged, df_q4_clean, on="code_str", how="inner")
    df_merged = pd.merge(df_merged, df_q5_clean, on="code_str", how="inner")
    df_merged = pd.merge(df_merged, df_q6_clean, on="code_str", how="inner")
    df_merged = pd.merge(df_merged, df_q7_clean, on="code_str", how="inner")
    
    if not df_zcfz_clean.empty:
        df_merged = pd.merge(df_merged, df_zcfz_clean, on="code_str", how="left")
    else:
        df_merged["debt_asset_ratio"] = 0.0
        df_merged["total_equity"] = 0.0
        df_merged["asset_growth"] = 0.0
        
    df_merged["debt_asset_ratio"] = df_merged["debt_asset_ratio"].fillna(0.0)
    df_merged["total_equity"] = df_merged["total_equity"].fillna(0.0)
    if "asset_growth" not in df_merged.columns:
        df_merged["asset_growth"] = 0.0
    df_merged["asset_growth"] = df_merged["asset_growth"].fillna(0.0)
    
    # 转换数值
    numeric_cols = [
        "price", "turnover", "roe_q0", "roe_q1", "roe_q2", "roe_q3", "roe_q4", "roe_q5", "roe_q6", "roe_q7",
        "margin_q0", "margin_q4", "revenue_growth", "net_profit_growth",
        "eps_q0", "ocf_q0", "debt_asset_ratio", "asset_growth", "total_equity", "bps_q0"
    ]
    for col in numeric_cols:
        df_merged[col] = pd.to_numeric(df_merged[col], errors="coerce")
        
    # === 计算与校正核心指标 ===
    
    # A. 依靠财务报表资产数据，反向推导真实的个股总市值与真实换手率 (应对Sina行情通道无市值的数据缺陷)
    df_merged["bps_q0"] = df_merged["bps_q0"].fillna(1.0)
    df_merged["calculated_shares"] = df_merged["total_equity"] / df_merged["bps_q0"].clip(lower=0.01)
    df_merged["real_market_cap_raw"] = df_merged["price"] * df_merged["calculated_shares"] # 以元为单位的市值
    df_merged["real_market_cap"] = df_merged["real_market_cap_raw"] / 10**8 # 以亿元为单位的市值
    
    # 覆盖第一阶段中填入的默认值
    df_merged["market_cap"] = df_merged["real_market_cap_raw"]
    df_merged["circ_market_cap"] = df_merged["real_market_cap_raw"]
    
    # 精密计算真实换手率 = (当天成交额 / 总市值) * 100
    df_merged["turnover_rate"] = (df_merged["turnover"] / df_merged["market_cap"].clip(lower=1.0)) * 100.0
    
    # B. 季节性平抑的一阶与二阶同比变化量 (行业景气度需要)
    df_merged["roe_change_latest"] = df_merged["roe_q0"] - df_merged["roe_q4"]
    df_merged["roe_change_prev"] = df_merged["roe_q1"] - df_merged["roe_q5"]
    df_merged["roe_acceleration"] = df_merged["roe_change_latest"] - df_merged["roe_change_prev"]
    
    # C. 计算资产周转率增速 (作为产能利用率增速的代理)
    df_merged["asset_turnover_growth"] = ((1.0 + df_merged["revenue_growth"].fillna(0.0) / 100.0) / 
                                           (1.0 + df_merged["asset_growth"].fillna(0.0).clip(lower=-99.0) / 100.0) - 1.0) * 100.0
    
    # D. 计算行业中观景气度评分及明细映射
    prosperity_map, details_map = calculate_industry_prosperity(df_merged, board_map)
    df_merged["industry_prosperity"] = df_merged["industry"].map(prosperity_map).fillna(50.0)
    
    # E. 杜邦分析：权益乘数 = 1 / (1 - 资产负债率/100)
    df_merged["equity_multiplier"] = 1.0 / (1.0 - (df_merged["debt_asset_ratio"].clip(0.0, 99.0) / 100.0))
    
    # F. 收益质量验证：盈余现金保障倍数 = 每股经营现金流 / 每股收益 (OCF / EPS)
    df_merged["cash_coverage"] = df_merged.apply(
        lambda r: r["ocf_q0"] / r["eps_q0"] if r["eps_q0"] > 0 else 0.0, axis=1
    )
    
    # G. 毛利率同比变化
    df_merged["margin_change"] = df_merged["margin_q0"] - df_merged["margin_q4"]
    
    # H. 过去 8 季度的 ROE 同比变化稳定性 (标准差)
    c0 = df_merged["roe_q0"] - df_merged["roe_q4"]
    c1 = df_merged["roe_q1"] - df_merged["roe_q5"]
    c2 = df_merged["roe_q2"] - df_merged["roe_q6"]
    c3 = df_merged["roe_q3"] - df_merged["roe_q7"]
    df_changes = pd.concat([c0, c1, c2, c3], axis=1)
    df_merged["roe_change_std"] = df_changes.std(axis=1)
    
    # 执行同比抗季节性选股逻辑 (转移并整合第二阶段真正的市值与换手率过滤)
    df_final = df_merged[
        (df_merged["roe_q0"] < 12.0) & 
        (df_merged["roe_change_latest"] > 0) &
        (df_merged["roe_acceleration"] > 0) &
        (df_merged["margin_change"] > 0) & 
        ((df_merged["revenue_growth"] > 15.0) | (df_merged["net_profit_growth"] > 20.0)) &
        (df_merged["equity_multiplier"] < 3.0) &
        (df_merged["cash_coverage"] >= 0.5) &
        (df_merged["roe_change_std"] < 2.0) &
        # 精细化市值与换手率筛选 (转移至此以运用 calculated 真实数值)
        (df_merged["real_market_cap"] >= 50.0) & (df_merged["real_market_cap"] <= 500.0) & 
        (df_merged["turnover_rate"] >= (0.8 if is_downgraded else 1.5)) &
        df_merged["roe_q0"].notna() &
        df_merged["roe_q4"].notna() &
        df_merged["roe_q1"].notna() &
        df_merged["roe_q5"].notna() &
        df_merged["margin_q0"].notna() &
        df_merged["margin_q4"].notna()
    ].copy()
    
    # 按净利润同比增速降序排列
    df_final.sort_values(by="net_profit_growth", ascending=False, inplace=True)
    
    print(f"二阶财务筛选完毕，最终选定标的数: {df_final.shape[0]}")
    
    # 6. 计算全球美股联动与产业链验证 (仅针对最终选定的标的)
    stock_list = []
    for _, row in df_final.iterrows():
        a_code = row["code_str"]
        global_peer = "无"
        c_sync = None
        c_lag = None
        us_ret = 0.0
        signal = "无明显先导关联"
        
        # 判断是否在联动映射表内
        if a_code in GLOBAL_PEER_MAP:
            us_symbol, us_name = GLOBAL_PEER_MAP[a_code]
            global_peer = us_name
            # 计算相关系数及联动结论
            c_sync, c_lag, us_ret, signal = calculate_global_linkage(a_code, us_symbol)
            
        # 产业链数据增量拉取
        val_chain = fetch_value_chain_data(a_code)
        # 控制频限，个股拉取间歇
        time.sleep(0.05)
            
        stock_list.append({
            "code": a_code,
            "name": row["name"],
            "price": round(row["price"], 2) if not math.isnan(row["price"]) else None,
            "change_pct": round(row["change_pct"], 2) if not math.isnan(row["change_pct"]) else None,
            "market_cap": round(row["market_cap"] / 10**8, 2) if not math.isnan(row["market_cap"]) else None,
            "turnover": round(row["turnover"] / 10**6, 2) if not math.isnan(row["turnover"]) else None,
            "turnover_rate": round(row["turnover_rate"], 2) if not math.isnan(row["turnover_rate"]) else None,
            "latest_roe": round(row["roe_q0"], 2),
            "prev_year_roe": round(row["roe_q4"], 2),
            "roe_change": round(row["roe_change_latest"], 2), 
            "roe_acceleration": round(row["roe_acceleration"], 2), 
            "latest_margin": round(row["margin_q0"], 2),
            "prev_year_margin": round(row["margin_q4"], 2),
            "margin_change": round(row["margin_change"], 2), 
            "revenue_growth": round(row["revenue_growth"], 2) if not math.isnan(row["revenue_growth"]) else None,
            "net_profit_growth": round(row["net_profit_growth"], 2) if not math.isnan(row["net_profit_growth"]) else None,
            "equity_multiplier": round(row["equity_multiplier"], 2),
            "cash_coverage": round(row["cash_coverage"], 2),
            "roe_stability": round(row["roe_change_std"], 2),
            "industry_prosperity": round(row["industry_prosperity"], 1) if not math.isnan(row["industry_prosperity"]) else 50.0,
            "industry_prosperity_details": details_map.get(row["industry"], {}),
            "global_peer": global_peer,
            "global_correlation": c_sync,
            "global_lead_correlation": c_lag,
            "global_lead_return": us_ret,
            "global_lead_signal": signal,
            "value_chain": val_chain
        })
        
    output_data = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "latest_quarter": format_quarter_name(q0_date),
        "previous_quarter": format_quarter_name(q1_date),
        "stocks": stock_list
    }
    
    # 写入 results.json
    output_path = "results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
        
    print(f"结果已成功写入 {output_path}，共 {len(stock_list)} 只标的。")
    print(f"总耗时: {round(time.time() - start_time, 2)} 秒")

if __name__ == "__main__":
    main()
