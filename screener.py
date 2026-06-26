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
        # f2:最新价, f3:涨跌幅, f6:成交额, f8:换手率, f12:代码, f14:名称, f20:总市值, f21:流通市值
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "http://quote.eastmoney.com/",
    }
    
    session = requests.Session()
    params = base_params.copy()
    
    # 获取第一页，确定总数
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
    """根据当前日期生成近期财报期候选列表"""
    now = datetime.now()
    year = now.year
    candidates = []
    for y in [year, year - 1, year - 2]:
        for q in ["1231", "0930", "0630", "0331"]:
            candidates.append(f"{y}{q}")
    
    now_str = now.strftime("%Y%m%d")
    candidates = [c for c in candidates if c < now_str]
    candidates.sort(reverse=True)
    return candidates

def find_active_quarters(count=3):
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
    
    # 总市值限制在 50 亿 - 500 亿 (RMB)
    min_cap = 50 * 10**8
    max_cap = 500 * 10**8
    df_filtered = df_filtered[(df_filtered["market_cap"] >= min_cap) & (df_filtered["market_cap"] <= max_cap)]
    
    # 流动性过滤
    min_turnover = 80 * 10**6
    min_turnover_rate = 1.5
    df_liq = df_filtered[(df_filtered["turnover"] >= min_turnover) & (df_filtered["turnover_rate"] >= min_turnover_rate)]
    
    if df_liq.shape[0] < 50:
        print("警告: 严格流动性过滤后标的过少，启动条件降级 (成交额 > 3000万，换手率 > 0.8%)")
        df_liq = df_filtered[(df_filtered["turnover"] >= 30 * 10**6) & (df_filtered["turnover_rate"] >= 0.8)]
        
    print(f"市值与流动性初筛完毕，候选池大小: {df_liq.shape[0]}")
    
    # 3. 动态获取最近 3 个季度的财务数据 (计算二阶加速度)
    active_quarters = find_active_quarters(count=3)
    (q_latest_date, df_latest) = active_quarters[0]
    (q_prev_date, df_prev) = active_quarters[1]
    (q_prev2_date, df_prev2) = active_quarters[2]
    
    # 4. 数据合并与二阶拐点筛选
    print("开始进行第二阶段筛选（财务二阶导数拐点）...")
    
    df_liq["code_str"] = df_liq["code"].astype(str).str.zfill(6)
    df_latest["code_str"] = df_latest["股票代码"].astype(str).str.zfill(6)
    df_prev["code_str"] = df_prev["股票代码"].astype(str).str.zfill(6)
    df_prev2["code_str"] = df_prev2["股票代码"].astype(str).str.zfill(6)
    
    # 最新季度财务
    df_latest_clean = df_latest[[
        "code_str", "净资产收益率", "销售毛利率", 
        "营业总收入-同比增长", "净利润-同比增长", "所处行业"
    ]].copy()
    df_latest_clean.columns = [
        "code_str", "latest_roe", "latest_margin", 
        "revenue_growth", "net_profit_growth", "industry"
    ]
    
    # 前一季度财务
    df_prev_clean = df_prev[["code_str", "净资产收益率", "销售毛利率"]].copy()
    df_prev_clean.columns = ["code_str", "prev_roe", "prev_margin"]
    
    # 前两季度财务
    df_prev2_clean = df_prev2[["code_str", "净资产收益率"]].copy()
    df_prev2_clean.columns = ["code_str", "prev2_roe"]
    
    # 链式合并
    df_merged = pd.merge(df_liq, df_latest_clean, on="code_str", how="inner")
    df_merged = pd.merge(df_merged, df_prev_clean, on="code_str", how="inner")
    df_merged = pd.merge(df_merged, df_prev2_clean, on="code_str", how="inner")
    
    # 转换数值
    for col in ["latest_roe", "prev_roe", "prev2_roe", "latest_margin", "prev_margin", "revenue_growth", "net_profit_growth"]:
        df_merged[col] = pd.to_numeric(df_merged[col], errors="coerce")
        
    # 计算一阶改善差与二阶加速度
    df_merged["roe_change_latest"] = df_merged["latest_roe"] - df_merged["prev_roe"]
    df_merged["roe_change_prev"] = df_merged["prev_roe"] - df_merged["prev2_roe"]
    df_merged["roe_acceleration"] = df_merged["roe_change_latest"] - df_merged["roe_change_prev"]
    df_merged["margin_change"] = df_merged["latest_margin"] - df_merged["prev_margin"]
    
    # 执行优化后的选股策略逻辑：
    # 1. 估值适中：低 ROE 改善阶段 (最新季度 ROE < 12.0%)
    # 2. 一阶改善：ROE TTM 在最新季度确有改善 (roe_change_latest > 0)
    # 3. 二阶加速：ROE 改善斜率呈加速度状态 (roe_acceleration > 0)
    # 4. 毛利率环比提升：最新季度销售毛利率 > 前一季度
    # 5. 高成长验证：营收同比增速 > 15% 或 净利润同比增速 > 20%
    # 6. 数据完整性过滤
    df_final = df_merged[
        (df_merged["latest_roe"] < 12.0) & 
        (df_merged["roe_change_latest"] > 0) &
        (df_merged["roe_acceleration"] > 0) &
        (df_merged["latest_margin"] > df_merged["prev_margin"]) & 
        ((df_merged["revenue_growth"] > 15.0) | (df_merged["net_profit_growth"] > 20.0)) &
        df_merged["latest_roe"].notna() &
        df_merged["latest_margin"].notna() &
        df_merged["prev_margin"].notna() &
        df_merged["prev2_roe"].notna()
    ].copy()
    
    # 按净利润同比增速降序排列
    df_final.sort_values(by="net_profit_growth", ascending=False, inplace=True)
    
    print(f"二阶财务筛选完毕，最终选定标的数: {df_final.shape[0]}")
    
    # 5. 格式化输出为 JSON
    stock_list = []
    for _, row in df_final.iterrows():
        stock_list.append({
            "code": row["code_str"],
            "name": row["name"],
            "price": round(row["price"], 2) if not math.isnan(row["price"]) else None,
            "change_pct": round(row["change_pct"], 2) if not math.isnan(row["change_pct"]) else None,
            "market_cap": round(row["market_cap"] / 10**8, 2) if not math.isnan(row["market_cap"]) else None,
            "turnover": round(row["turnover"] / 10**6, 2) if not math.isnan(row["turnover"]) else None,
            "turnover_rate": round(row["turnover_rate"], 2) if not math.isnan(row["turnover_rate"]) else None,
            "latest_roe": round(row["latest_roe"], 2),
            "prev_roe": round(row["prev_roe"], 2),
            "roe_change": round(row["roe_change_latest"], 2),
            "roe_acceleration": round(row["roe_acceleration"], 2),
            "latest_margin": round(row["latest_margin"], 2),
            "prev_margin": round(row["prev_margin"], 2),
            "margin_change": round(row["margin_change"], 2),
            "revenue_growth": round(row["revenue_growth"], 2) if not math.isnan(row["revenue_growth"]) else None,
            "net_profit_growth": round(row["net_profit_growth"], 2) if not math.isnan(row["net_profit_growth"]) else None,
            "industry": row["industry"] if isinstance(row["industry"], str) else "其它"
        })
        
    output_data = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "latest_quarter": format_quarter_name(q_latest_date),
        "previous_quarter": format_quarter_name(q_prev_date),
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
