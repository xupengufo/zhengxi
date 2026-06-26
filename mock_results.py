import json
from datetime import datetime

mock_data = {
  "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " (MOCK)",
  "latest_quarter": "2026Q1",
  "previous_quarter": "2025Q4",
  "stocks": [
    {
      "code": "300308",
      "name": "中际旭创",
      "price": 145.20,
      "change_pct": 3.45,
      "market_cap": 380.50,
      "turnover": 450.20,
      "turnover_rate": 2.10,
      "latest_roe": 6.80,
      "prev_year_roe": 4.50,
      "roe_change": 2.30,
      "roe_acceleration": 1.10,
      "latest_margin": 32.40,
      "prev_year_margin": 28.50,
      "margin_change": 3.90,
      "revenue_growth": 45.20,
      "net_profit_growth": 88.60,
      "equity_multiplier": 1.45,
      "cash_coverage": 1.25,
      "roe_stability": 0.85,
      "industry_prosperity": 85.5,
      "industry_prosperity_details": {
        "rev_growth": 42.15,
        "roe_growth": 1.85,
        "cap_growth": 12.34,
        "price_growth": 15.62
      },
      "global_peer": "美股 Fabrinet (FN)",
      "global_correlation": 0.42,
      "global_lead_correlation": 0.58,
      "global_lead_return": 6.20,
      "global_lead_signal": "左侧补涨信号",
      "value_chain": {
        "contract_liab": 12.54,
        "contract_liab_yoy": 158.45,
        "advance_receivables": 1.20,
        "advance_receivables_yoy": -12.40,
        "cip": 8.42,
        "cip_yoy": 312.45,
        "fixed_asset": 45.20,
        "fixed_asset_yoy": 35.60
      }
    },
    {
      "code": "603501",
      "name": "韦尔股份",
      "price": 98.50,
      "change_pct": -1.20,
      "market_cap": 1150.30,
      "turnover": 520.40,
      "turnover_rate": 0.95,
      "latest_roe": 3.40,
      "prev_year_roe": 2.10,
      "roe_change": 1.30,
      "roe_acceleration": 0.50,
      "latest_margin": 21.30,
      "prev_year_margin": 19.50,
      "margin_change": 1.80,
      "revenue_growth": 23.40,
      "net_profit_growth": 45.60,
      "equity_multiplier": 1.62,
      "cash_coverage": 0.82,
      "roe_stability": 0.45,
      "industry_prosperity": 68.2,
      "industry_prosperity_details": {
        "rev_growth": 20.45,
        "roe_growth": 0.95,
        "cap_growth": 4.12,
        "price_growth": -2.45
      },
      "global_peer": "美股 ON Semi (ON)",
      "global_correlation": 0.65,
      "global_lead_correlation": 0.42,
      "global_lead_return": -4.20,
      "global_lead_signal": "防守避险信号",
      "value_chain": {
        "contract_liab": 4.12,
        "contract_liab_yoy": -8.50,
        "advance_receivables": 0.35,
        "advance_receivables_yoy": 5.40,
        "cip": 12.45,
        "cip_yoy": 12.40,
        "fixed_asset": 125.40,
        "fixed_asset_yoy": 8.50
      }
    },
    {
      "code": "002371",
      "name": "北方华创",
      "price": 285.40,
      "change_pct": 2.15,
      "market_cap": 1512.40,
      "turnover": 920.60,
      "turnover_rate": 1.80,
      "latest_roe": 11.20,
      "prev_year_roe": 8.50,
      "roe_change": 2.70,
      "roe_acceleration": 0.90,
      "latest_margin": 41.50,
      "prev_year_margin": 38.60,
      "margin_change": 2.90,
      "revenue_growth": 38.50,
      "net_profit_growth": 65.40,
      "equity_multiplier": 1.52,
      "cash_coverage": 1.42,
      "roe_stability": 0.95,
      "industry_prosperity": 92.4,
      "industry_prosperity_details": {
        "rev_growth": 35.60,
        "roe_growth": 2.45,
        "cap_growth": 25.40,
        "price_growth": 18.20
      },
      "global_peer": "美股 Applied Materials (AMAT)",
      "global_correlation": 0.52,
      "global_lead_correlation": 0.48,
      "global_lead_return": 1.20,
      "global_lead_signal": "同步强联动",
      "value_chain": {
        "contract_liab": 145.20,
        "contract_liab_yoy": 68.45,
        "advance_receivables": 2.45,
        "advance_receivables_yoy": 15.60,
        "cip": 35.60,
        "cip_yoy": 85.40,
        "fixed_asset": 82.50,
        "fixed_asset_yoy": 24.50
      }
    },
    {
      "code": "600406",
      "name": "国电南瑞",
      "price": 24.80,
      "change_pct": -0.85,
      "market_cap": 480.20,
      "turnover": 120.40,
      "turnover_rate": 1.20,
      "latest_roe": 7.20,
      "prev_year_roe": 6.10,
      "roe_change": 1.10,
      "roe_acceleration": 0.40,
      "latest_margin": 26.80,
      "prev_year_margin": 25.10,
      "margin_change": 1.70,
      "revenue_growth": 18.50,
      "net_profit_growth": 22.40,
      "equity_multiplier": 1.82,
      "cash_coverage": 0.95,
      "roe_stability": 0.32,
      "industry_prosperity": 45.2,
      "industry_prosperity_details": {
        "rev_growth": 15.40,
        "roe_growth": 0.85,
        "cap_growth": 2.12,
        "price_growth": 1.50
      },
      "global_peer": "无",
      "global_correlation": None,
      "global_lead_correlation": None,
      "global_lead_return": 0.0,
      "global_lead_signal": "无明显先导关联",
      "value_chain": {
        "contract_liab": 42.15,
        "contract_liab_yoy": 12.45,
        "advance_receivables": 0.85,
        "advance_receivables_yoy": -5.12,
        "cip": 12.35,
        "cip_yoy": -8.50,
        "fixed_asset": 154.20,
        "fixed_asset_yoy": 4.12
      }
    }
  ]
}

with open("results.json", "w", encoding="utf-8") as f:
    json.dump(mock_data, f, ensure_ascii=False, indent=2)

print("Updated mock results.json created successfully.")
