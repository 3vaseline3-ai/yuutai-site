"""日興証券の一般信用在庫を取得"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import csv
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from config import IPPAN_ZAIKO_DIR


def fetch_nikko_zaiko() -> list[dict]:
    """日興証券の一般信用在庫を取得"""
    # TODO: 実際のURLとパース処理を実装
    # 日興証券の一般信用売り在庫ページからデータを取得

    url = "https://trade.smbcnikko.co.jp/..."  # 実際のURLに置き換え

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    stocks = []

    # try:
    #     response = requests.get(url, headers=headers, timeout=30)
    #     response.raise_for_status()
    #     soup = BeautifulSoup(response.text, "lxml")
    #
    #     # パース処理
    #
    # except requests.RequestException as e:
    #     print(f"Error fetching: {e}")

    return stocks


def save_zaiko(stocks: list[dict]) -> None:
    """在庫情報をCSVに保存"""
    today = datetime.now().strftime("%Y%m%d")
    output_file = IPPAN_ZAIKO_DIR / f"nikko_{today}.csv"

    if not stocks:
        print("保存する在庫データがありません")
        return

    fieldnames = ["code", "name", "zaiko", "timestamp"]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stocks)

    print(f"Saved: {output_file}")


if __name__ == "__main__":
    stocks = fetch_nikko_zaiko()
    save_zaiko(stocks)
