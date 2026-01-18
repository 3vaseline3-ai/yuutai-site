#!/usr/bin/env python3
"""
優待CLIツール - 月別ランキング表示

使い方:
  python yuutai_cli.py 1      # 1月優待ランキング（在庫あり・月利回り順）
  python yuutai_cli.py 2      # 2月優待ランキング
  python yuutai_cli.py 1 -n 20  # 上位20件表示
"""

import csv
import json
import sys
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"
ZAIKO_DIR = DATA_DIR / "ippan_zaiko"
KACHI_CSV = DATA_DIR / "kachi.csv"

# 金利計算用定数
INTEREST_RATE = 1.7  # 年利1.7%


def load_kachi_data():
    """kachi.csvを読み込み（優待価値の正しいソース）"""
    kachi = {}
    if not KACHI_CSV.exists():
        return kachi
    with open(KACHI_CSV, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # ヘッダー行をスキップ
        for row in reader:
            if len(row) >= 5:
                code = row[0]
                kachi[code] = {
                    "name": row[1],
                    "month": int(row[2]) if row[2] else 0,
                    "kabusu": int(row[3]) if row[3] else 100,
                    "yutai_value": int(row[4]) if row[4] else 0,
                }
    return kachi


def load_zaiko_data(month: int):
    """最新の在庫データを読み込み"""
    # 最新のファイルを探す
    pattern = f"zaiko_{month:02d}_*.json"
    files = sorted(ZAIKO_DIR.glob(pattern), reverse=True)
    if not files:
        return {}
    with open(files[0], "r", encoding="utf-8") as f:
        return json.load(f)


def has_zaiko(stock):
    """日興証券の一般信用在庫があるかチェック"""
    zaiko = stock.get("zaiko", {})
    nikko = zaiko.get("nikko")
    return nikko is not None and nikko > 0


def calc_months_to_cross(target_month: int) -> int:
    """現在から対象月末まで何回月末をまたぐか計算"""
    now = datetime.now()
    current_month = now.month

    if target_month >= current_month:
        return target_month - current_month + 1
    else:
        # 来年の場合
        return (12 - current_month) + target_month + 1


def calc_monthly_yield(stock, kachi_info, target_month: int):
    """月利回りを計算（%）

    月利回り = (1株優待価値 - 金利) / 株価 * 100 / 月末をまたぐ回数
    """
    kabuka = stock.get("kabuka", 0)

    # kachi.csvの優待価値を使用（正しいソース）
    kabusu = kachi_info.get("kabusu", 100)
    yutai_value = kachi_info.get("yutai_value", 0)

    if kabuka <= 0 or kabusu <= 0 or yutai_value <= 0:
        return 0

    # 月末をまたぐ回数
    months = calc_months_to_cross(target_month)

    # 1株優待価値
    value_per_share = yutai_value / kabusu

    # 金利（1株あたり、月数分）
    interest = kabuka * (INTEREST_RATE / 100) * (months / 12)

    # 月利回り
    monthly_yield = (value_per_share - interest) / kabuka * 100 / months

    return monthly_yield


def show_month_ranking(month: int, limit: int = 50):
    """月別ランキング表示（在庫あり・月利回り順）"""
    data = load_zaiko_data(month)
    kachi_data = load_kachi_data()

    if not data:
        print(f"❌ {month}月の在庫データが見つかりませんでした")
        return

    # 在庫ありの銘柄のみフィルタ（kachi.csvにある銘柄のみ）
    stocks_with_zaiko = []
    for code, stock in data.items():
        if has_zaiko(stock) and code in kachi_data:
            kachi_info = kachi_data[code]
            stock["code"] = code
            stock["monthly_yield"] = calc_monthly_yield(stock, kachi_info, month)
            stocks_with_zaiko.append(stock)

    if not stocks_with_zaiko:
        print(f"❌ {month}月の在庫あり銘柄が見つかりませんでした")
        return

    # 月利回り順でソート（高い順）
    stocks_with_zaiko.sort(key=lambda x: x["monthly_yield"], reverse=True)

    print(f"\n{'='*50}")
    print(f"  📅 {month}月 優待ランキング（在庫あり・月利回り順）")
    print(f"  📊 {len(stocks_with_zaiko)}銘柄")
    print(f"{'='*50}\n")

    print(f"{'順位':>4} {'コード':>6} {'銘柄名':<14} {'月利回り':>8}")
    print("-" * 50)

    for i, stock in enumerate(stocks_with_zaiko[:limit], 1):
        code = stock.get("code", "")
        name = stock.get("name", "")[:12]
        monthly_yield = stock.get("monthly_yield", 0)

        print(f"{i:>4} {code:>6} {name:<14} {monthly_yield:>7.2f}%")

    print("-" * 50)
    print(f"\n💡 詳細: https://3vaseline3-ai.github.io/yuutai-site/{month:02d}.html\n")


def show_all_months_summary():
    """全月サマリー表示（在庫あり銘柄数）"""
    kachi_data = load_kachi_data()

    print(f"\n{'='*50}")
    print(f"  📅 月別優待銘柄数（日興在庫あり）")
    print(f"{'='*50}\n")

    for month in range(1, 13):
        data = load_zaiko_data(month)
        count = 0
        for code, stock in data.items():
            if has_zaiko(stock) and code in kachi_data:
                count += 1
        bar = "█" * (count // 2)
        print(f"  {month:>2}月: {count:>4}銘柄 {bar}")

    print()


def main():
    if len(sys.argv) < 2:
        show_all_months_summary()
        print("使い方: python yuutai_cli.py [月] [-n 件数]")
        print("例: python yuutai_cli.py 1")
        print("例: python yuutai_cli.py 3 -n 30")
        return

    month = int(sys.argv[1])
    limit = 15

    if "-n" in sys.argv:
        idx = sys.argv.index("-n")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])

    show_month_ranking(month, limit)


if __name__ == "__main__":
    main()
