"""yfinanceで最新株価を取得"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import csv
import json
import time
from datetime import datetime
import yfinance as yf
import pandas as pd
from config import STOCK_PRICE_DIR, DATA_DIR, KACHI_CSV


LATEST_PRICES_FILE = STOCK_PRICE_DIR / "latest_prices.json"


def fetch_stock_price(code: str) -> dict | None:
    """指定銘柄の最新株価を取得"""
    # 東証銘柄はコード.Tで取得
    ticker_symbol = f"{code}.T"

    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info

        return {
            "code": code,
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "previous_close": info.get("previousClose"),
            "volume": info.get("volume"),
            "market_cap": info.get("marketCap"),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        print(f"Error fetching {code}: {e}")
        return None


def fetch_stock_history(code: str, period: str = "1y") -> pd.DataFrame:
    """指定銘柄の株価履歴を取得"""
    ticker_symbol = f"{code}.T"

    try:
        ticker = yf.Ticker(ticker_symbol)
        history = ticker.history(period=period)
        return history
    except Exception as e:
        print(f"Error fetching history {code}: {e}")
        return pd.DataFrame()


def save_stock_price(code: str, history: pd.DataFrame) -> None:
    """株価履歴をCSVに保存"""
    output_file = STOCK_PRICE_DIR / f"{code}.csv"
    history.to_csv(output_file)
    print(f"Saved: {output_file}")


def fetch_all_prices(codes: list[str]) -> list[dict]:
    """複数銘柄の株価を一括取得"""
    prices = []
    for code in codes:
        price = fetch_stock_price(code)
        if price:
            prices.append(price)
    return prices


def fetch_all_from_kachi() -> dict[str, float]:
    """kachi.csvの全銘柄の最新株価を取得"""
    if not KACHI_CSV.exists():
        print("kachi.csv が見つかりません")
        return {}

    # 銘柄コードを取得（重複除去）
    codes = set()
    with open(KACHI_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            codes.add(row["code"])

    print(f"取得対象: {len(codes)}銘柄")

    prices = {}
    failed = []
    for i, code in enumerate(sorted(codes), 1):
        print(f"[{i}/{len(codes)}] {code}...", end=" ", flush=True)
        data = fetch_stock_price(code)
        if data and data.get("price"):
            prices[code] = data["price"]
            print(f"{data['price']:,.0f}円")
        else:
            failed.append(code)
            print("失敗")
        time.sleep(0.3)

    if failed:
        print(f"\n取得失敗: {len(failed)}銘柄")
        print(f"  {', '.join(failed[:10])}{'...' if len(failed) > 10 else ''}")

    return prices


def save_latest_prices(prices: dict[str, float]) -> None:
    """最新株価をJSONに保存"""
    STOCK_PRICE_DIR.mkdir(parents=True, exist_ok=True)

    data = {
        "updated_at": datetime.now().isoformat(),
        "prices": prices,
    }

    with open(LATEST_PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nSaved: {LATEST_PRICES_FILE}")
    print(f"  {len(prices)}銘柄")


def load_latest_prices() -> dict[str, float]:
    """保存済みの最新株価を読み込み"""
    if not LATEST_PRICES_FILE.exists():
        return {}

    with open(LATEST_PRICES_FILE, encoding="utf-8") as f:
        data = json.load(f)
        return data.get("prices", {})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="yfinanceで株価を取得")
    parser.add_argument("--code", "-c", type=str, help="銘柄コード")
    parser.add_argument("--history", action="store_true", help="履歴を取得")
    parser.add_argument("--all", "-a", action="store_true", help="kachi.csvの全銘柄を取得")
    args = parser.parse_args()

    if args.all:
        prices = fetch_all_from_kachi()
        save_latest_prices(prices)
    elif args.code:
        if args.history:
            history = fetch_stock_history(args.code)
            if not history.empty:
                save_stock_price(args.code, history)
                print(history.tail())
        else:
            price = fetch_stock_price(args.code)
            if price:
                print(f"{args.code}: {price['price']:,.0f}円")
    else:
        parser.print_help()
