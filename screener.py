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
    
    try:
        r = session.get(SPOT_URL, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        total = data["data"]["total"]
        print(f"全市场共 {total} 只股票，开始分页拉取...")
    except Exception as e:
        print(f"获取行情首面失败: {e}")
        return pd.DataFrame()
        
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
            time.sleep(0.05)
        except Exception as e:
            print(f"获取第 {page} 页失败: {e}")
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
        
    print(f"行情拉取完毕，有效标的数: {df.shape[0]}")
    return df

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

def calculate_global_linkage(a_code, us_symbol_full):
    """计算 A 股股票与美股对标标的过去 30 个交易日的相关系数及美股 5 日收益率"""
    print(f"  [全球联动] 开始计算 {a_code} 与 {us_symbol_full} 的相关性...")
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - pd.Timedelta(days=45)).strftime("%Y%m%d")
        
        # 抓取 A 股前复权历史价格
        df_a = ak.stock_zh_a_hist(symbol=a_code, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        # 抓取美股前复权历史价格
        df_us = ak.stock_us_hist(symbol=us_symbol_full, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        
        if df_a.empty or df_us.empty:
            return None, 0.0
            
        df_a_clean = df_a[['日期', '收盘']].copy()
        df_a_clean.columns = ['date', 'close_a']
        
        df_us_clean = df_us[['日期', '收盘']].copy()
        df_us_clean.columns = ['date', 'close_us']
        
        df_merged = pd.merge(df_a_clean, df_us_clean, on='date', how='inner')
        if len(df_merged) < 10:
            return None, 0.0
            
        corr = df_merged['close_a'].corr(df_merged['close_us'])
        
        # 计算美股过去 5 个交易日的涨跌幅
        us_5d_ret = 0.0
        if len(df_us) >= 5:
            latest_close = df_us['收盘'].iloc[-1]
            prev_5d_close = df_us['收盘'].iloc[-5]
            us_5d_ret = (latest_close - prev_5d_close) / prev_5d_close * 100
            
        return round(corr, 2), round(us_5d_ret, 2)
    except Exception as e:
        print(f"  [全球联动] {a_code} 对标 {us_symbol_full} 计算失败: {e}")
        return None, 0.0

def main():
    start_time = time.time()
    
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
    
    if df_liq.shape[0] < 50:
        print("警告: 严格流动性过滤后标的过少，启动条件降级 (成交额 > 3000万，换手率 > 0.8%)")
        df_liq = df_filtered[(df_filtered["turnover"] >= 30 * 10**6) & (df_filtered["turnover_rate"] >= 0.8)]
        
    print(f"市值与流动性初筛完毕，候选池大小: {df_liq.shape[0]}")
    
    # 3. 动态获取最近 8 个季度的财务数据 (计算同比二阶加速度 + 过去8季同比波动率)
    active_quarters = find_active_quarters(count=8)
    (q0_date, df_q0) = active_quarters[0]
    (q1_date, df_q1) = active_quarters[1]
    (q4_date, df_q4) = active_quarters[4]
    (q5_date, df_q5) = active_quarters[5]
    (q6_date, df_q6) = active_quarters[6]
    (q7_date, df_q7) = active_quarters[7]
    
    # 4. 获取资产负债表数据 (计算杜邦分析权益乘数)
    print(f"拉取资产负债表数据 ({q0_date})...")
    df_zcfz = pd.DataFrame()
    try:
        df_zcfz = ak.stock_zcfz_em(date=q0_date)
        df_zcfz["code_str"] = df_zcfz["股票代码"].astype(str).str.zfill(6)
        df_zcfz_clean = df_zcfz[["code_str", "资产负债率"]].copy()
        df_zcfz_clean.columns = ["code_str", "debt_asset_ratio"]
    except Exception as e:
        print(f"拉取资产负债表失败: {e}，将使用资产负债率默认值(0.0)")
        df_zcfz_clean = pd.DataFrame(columns=["code_str", "debt_asset_ratio"])

    # 5. 数据合并与复筛
    print("开始进行第二阶段筛选（财务二阶导数 + 杜邦健康度 + 盈余现金保障 + 中观行业景气度）...")
    
    df_liq["code_str"] = df_liq["code"].astype(str).str.zfill(6)
    
    # 整理各季度财务字段
    df_q0_clean = df_q0[["code_str", "净资产收益率", "销售毛利率", "每股收益", "每股经营现金流量", "营业总收入-同比增长", "净利润-同比增长", "所处行业"]].copy()
    df_q0_clean.columns = ["code_str", "roe_q0", "margin_q0", "eps_q0", "ocf_q0", "revenue_growth", "net_profit_growth", "industry"]
    
    df_q1_clean = df_q1[["code_str", "净资产收益率"]].copy()
    df_q1_clean.columns = ["code_str", "roe_q1"]
    
    df_q4_clean = df_q4[["code_str", "净资产收益率", "销售毛利率"]].copy()
    df_q4_clean.columns = ["code_str", "roe_q4", "margin_q4"]
    
    df_q5_clean = df_q5[["code_str", "净资产收益率"]].copy()
    df_q5_clean.columns = ["code_str", "roe_q5"]
    
    df_q6_clean = df_q6[["code_str", "净资产收益率"]].copy()
    df_q6_clean.columns = ["code_str", "roe_q6"]
    
    df_q7_clean = df_q7[["code_str", "净资产收益率"]].copy()
    df_q7_clean.columns = ["code_str", "roe_q7"]
    
    # 链式合并
    df_merged = pd.merge(df_liq, df_q0_clean, on="code_str", how="inner")
    df_merged = pd.merge(df_merged, df_q1_clean, on="code_str", how="inner")
    df_merged = pd.merge(df_merged, df_q4_clean, on="code_str", how="inner")
    df_merged = pd.merge(df_merged, df_q5_clean, on="code_str", how="inner")
    df_merged = pd.merge(df_merged, df_q6_clean, on="code_str", how="inner")
    df_merged = pd.merge(df_merged, df_q7_clean, on="code_str", how="inner")
    
    if not df_zcfz_clean.empty:
        df_merged = pd.merge(df_merged, df_zcfz_clean, on="code_str", how="left")
    else:
        df_merged["debt_asset_ratio"] = 0.0
        
    df_merged["debt_asset_ratio"] = df_merged["debt_asset_ratio"].fillna(0.0)
    
    # 转换数值
    numeric_cols = [
        "roe_q0", "roe_q1", "roe_q4", "roe_q5", "roe_q6", "roe_q7",
        "margin_q0", "margin_q4", "revenue_growth", "net_profit_growth",
        "eps_q0", "ocf_q0", "debt_asset_ratio"
    ]
    for col in numeric_cols:
        df_merged[col] = pd.to_numeric(df_merged[col], errors="coerce")
        
    # === 计算量化核心指标 ===
    
    # 1. 中观行业景气度综合指数（在合并全市场数据后，按行业计算平均增速）
    # 使用 0.5 * 行业平均营收增速 + 0.5 * 行业平均净利增速 来作为“行业中观景气度”
    df_merged["ind_avg_rev_growth"] = df_merged.groupby("industry")["revenue_growth"].transform("mean")
    df_merged["ind_avg_net_profit_growth"] = df_merged.groupby("industry")["net_profit_growth"].transform("mean")
    df_merged["industry_prosperity"] = 0.5 * df_merged["ind_avg_rev_growth"] + 0.5 * df_merged["ind_avg_net_profit_growth"]
    
    # 2. 杜邦分析：权益乘数 = 1 / (1 - 资产负债率/100)
    df_merged["equity_multiplier"] = 1.0 / (1.0 - (df_merged["debt_asset_ratio"].clip(0.0, 99.0) / 100.0))
    
    # 3. 收益质量验证：盈余现金保障倍数 = 每股经营现金流 / 每股收益 (OCF / EPS)
    df_merged["cash_coverage"] = df_merged.apply(
        lambda r: r["ocf_q0"] / r["eps_q0"] if r["eps_q0"] > 0 else 0.0, axis=1
    )
    
    # 4. 季节性平抑的一阶同比变化量
    df_merged["roe_change_latest"] = df_merged["roe_q0"] - df_merged["roe_q4"]
    df_merged["roe_change_prev"] = df_merged["roe_q1"] - df_merged["roe_q5"]
    
    # 5. 同比加速度 (二阶导数)
    df_merged["roe_acceleration"] = df_merged["roe_change_latest"] - df_merged["roe_change_prev"]
    
    # 6. 毛利率同比变化
    df_merged["margin_change"] = df_merged["margin_q0"] - df_merged["margin_q4"]
    
    # 7. 过去 8 季度的 ROE 同比变化稳定性 (标准差)
    c0 = df_merged["roe_q0"] - df_merged["roe_q4"]
    c1 = df_merged["roe_q1"] - df_merged["roe_q5"]
    c2 = df_merged["roe_q2"] - df_merged["roe_q6"]
    c3 = df_merged["roe_q3"] - df_merged["roe_q7"]
    df_changes = pd.concat([c0, c1, c2, c3], axis=1)
    df_merged["roe_change_std"] = df_changes.std(axis=1)
    
    # 执行同比抗季节性选股逻辑
    df_final = df_merged[
        (df_merged["roe_q0"] < 12.0) & 
        (df_merged["roe_change_latest"] > 0) &
        (df_merged["roe_acceleration"] > 0) &
        (df_merged["margin_change"] > 0) & 
        ((df_merged["revenue_growth"] > 15.0) | (df_merged["net_profit_growth"] > 20.0)) &
        (df_merged["equity_multiplier"] < 3.0) &
        (df_merged["cash_coverage"] >= 0.5) &
        (df_merged["roe_change_std"] < 2.0) &
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
    
    # 6. 计算全球美股联动相关系数 (仅针对最终选定的标的中属于核心科技龙头的股)
    stock_list = []
    for _, row in df_final.iterrows():
        a_code = row["code_str"]
        global_peer = "无"
        global_corr = None
        global_lead_ret = 0.0
        
        # 判断是否在联动映射表内
        if a_code in GLOBAL_PEER_MAP:
            us_symbol, us_name = GLOBAL_PEER_MAP[a_code]
            global_peer = us_name
            # 计算相关系数
            corr, us_ret = calculate_global_linkage(a_code, us_symbol)
            global_corr = corr
            global_lead_ret = us_ret
            
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
            "industry_prosperity": round(row["industry_prosperity"], 2) if not math.isnan(row["industry_prosperity"]) else 0.0,
            "global_peer": global_peer,
            "global_correlation": global_corr,
            "global_lead_return": global_lead_ret
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
