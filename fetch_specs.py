import urllib.request
import json
import os

API_URL = "https://www.okx.com/api/v5/public/instruments?instType=SWAP&limit=500"
output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contract_specs.json")

try:
    req = urllib.request.Request(API_URL, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())

    # 过滤 USDT 本位永续合约
    perps = [s for s in data.get("data", []) if s.get("settleCcy") == "USDT"]

    result = {
        "_comment": (
            "OKX USDT本位永续合约规格。\n"
            "contract_size: 1张合约对应的标的物数量（如BTC为0.01，表示1张=0.01BTC）。\n"
            "min_lot: 最小交易数量，单位为张（如BTC为0.01，表示最少交易0.01张）。\n"
            "用户可直接修改此文件以自定义合约规格。"
        ),
        "contracts": {}
    }

    for s in perps:
        symbol = s["instId"].replace("-USDT-SWAP", "")  # BTC-USDT-SWAP → BTC
        result["contracts"][symbol] = {
            "contract_size": float(s.get("ctVal", 0.01)),
            "min_lot": float(s.get("minSz", 0.01)),
            "base_asset": s.get("baseCcy", ""),
            "source": "okx_public_instruments"
        }

    # 按symbol名称排序
    result["contracts"] = dict(sorted(result["contracts"].items()))

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"已生成合约规格文件: {output_path}")
    print(f"包含 {len(result['contracts'])} 个品种")
    for symbol in list(result["contracts"].keys())[:20]:
        info = result["contracts"][symbol]
        print(f"  {symbol}: contract_size={info['contract_size']}, min_lot={info['min_lot']}")

except Exception as e:
    print(f"获取失败: {e}")
    # 如果获取失败，生成一份常见品种的默认配置（基于OKX常见规格）
    fallback = {
        "_comment": (
            "OKX USDT本位永续合约规格（离线默认值，请手动核实）。\n"
            "contract_size: 1张合约对应的标的物数量。\n"
            "min_lot: 最小交易数量（张数）。\n"
            "用户可直接修改此文件以自定义合约规格。"
        ),
        "contracts": {
            "BTC": {"contract_size": 0.01, "min_lot": 0.01, "base_asset": "BTC", "source": "offline_default"},
            "ETH": {"contract_size": 0.1, "min_lot": 0.01, "base_asset": "ETH", "source": "offline_default"},
            "SOL": {"contract_size": 1, "min_lot": 1, "base_asset": "SOL", "source": "offline_default"},
            "XRP": {"contract_size": 10, "min_lot": 1, "base_asset": "XRP", "source": "offline_default"},
            "DOGE": {"contract_size": 1000, "min_lot": 1, "base_asset": "DOGE", "source": "offline_default"},
            "ADA": {"contract_size": 10, "min_lot": 1, "base_asset": "ADA", "source": "offline_default"},
            "AVAX": {"contract_size": 1, "min_lot": 0.1, "base_asset": "AVAX", "source": "offline_default"},
            "LINK": {"contract_size": 1, "min_lot": 0.1, "base_asset": "LINK", "source": "offline_default"},
            "DOT": {"contract_size": 1, "min_lot": 0.1, "base_asset": "DOT", "source": "offline_default"},
            "MATIC": {"contract_size": 10, "min_lot": 1, "base_asset": "MATIC", "source": "offline_default"},
            "ARB": {"contract_size": 1, "min_lot": 1, "base_asset": "ARB", "source": "offline_default"},
            "OP": {"contract_size": 1, "min_lot": 1, "base_asset": "OP", "source": "offline_default"},
            "SUI": {"contract_size": 1, "min_lot": 0.1, "base_asset": "SUI", "source": "offline_default"},
            "APT": {"contract_size": 1, "min_lot": 0.1, "base_asset": "APT", "source": "offline_default"},
            "FIL": {"contract_size": 1, "min_lot": 1, "base_asset": "FIL", "source": "offline_default"},
            "LTC": {"contract_size": 0.1, "min_lot": 0.01, "base_asset": "LTC", "source": "offline_default"},
            "BCH": {"contract_size": 0.01, "min_lot": 0.01, "base_asset": "BCH", "source": "offline_default"},
            "ATOM": {"contract_size": 1, "min_lot": 0.1, "base_asset": "ATOM", "source": "offline_default"},
            "NEAR": {"contract_size": 1, "min_lot": 0.1, "base_asset": "NEAR", "source": "offline_default"},
            "CRV": {"contract_size": 10, "min_lot": 1, "base_asset": "CRV", "source": "offline_default"},
            "TRX": {"contract_size": 100, "min_lot": 1, "base_asset": "TRX", "source": "offline_default"},
            "PEPE": {"contract_size": 100000, "min_lot": 1, "base_asset": "PEPE", "source": "offline_default"},
        }
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(fallback, f, ensure_ascii=False, indent=2)
    print(f"已生成离线默认合约规格文件: {output_path}")
