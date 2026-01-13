"""gokigen-life.tokyoから最大逆日歩を取得"""

import sys
import re
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
from config import DATA_DIR, KACHI_CSV
import csv

MAX_GYAKU_FILE = DATA_DIR / "max_gyaku.json"
ACCESS_INTERVAL = 2  # アクセス間隔（秒）


def fetch_max_gyaku(code: str) -> int | None:
    """
    銘柄コードから最大逆日歩を取得

    Returns:
        int: 最大逆日歩（円）、取得できない場合はNone
    """
    url = f"https://gokigen-life.tokyo/{code}yutai/"

    try:
        response = cffi_requests.get(url, impersonate="chrome", timeout=30)
        response.raise_for_status()

        # 逆日歩最大額を正規表現で抽出
        # パターン: 逆日歩最大額:○○円
        pattern = r'逆日歩最大額[：:](\d+)円'
        matches = re.findall(pattern, response.text)

        if matches:
            # 複数ある場合は最大値を取得
            max_value = max(int(m) for m in matches)
            return max_value

        return None

    except Exception as e:
        print(f"Error fetching {code}: {e}")
        return None


def load_existing_data() -> dict:
    """既存データを読み込み"""
    if MAX_GYAKU_FILE.exists():
        with open(MAX_GYAKU_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_data(data: dict) -> None:
    """データを保存"""
    data["_updated"] = datetime.now().isoformat()
    with open(MAX_GYAKU_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_all_codes() -> list[str]:
    """kachi.csvから全銘柄コードを取得"""
    codes = set()
    with open(KACHI_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row.get("code", "")
            if code:
                codes.add(code)
    return list(codes)


def main():
    parser = argparse.ArgumentParser(description="最大逆日歩を取得")
    parser.add_argument("--code", help="銘柄コード（指定しない場合は全銘柄）")
    parser.add_argument("--all", action="store_true", help="全銘柄を取得")
    parser.add_argument("--update", action="store_true", help="未取得の銘柄のみ更新")
    args = parser.parse_args()

    data = load_existing_data()

    if args.code:
        # 単一銘柄
        codes = [args.code]
    elif args.all or args.update:
        # 全銘柄
        codes = get_all_codes()
    else:
        print("--code, --all, または --update を指定してください")
        return

    print(f"取得対象: {len(codes)}銘柄")

    for i, code in enumerate(codes):
        # 更新モードの場合、既存データがあればスキップ
        if args.update and code in data and data[code] is not None:
            continue

        print(f"[{i+1}/{len(codes)}] {code}...", end=" ")
        max_gyaku = fetch_max_gyaku(code)

        if max_gyaku is not None:
            data[code] = max_gyaku
            print(f"{max_gyaku:,}円")
        else:
            data[code] = None
            print("取得できず")

        # アクセス間隔
        if i < len(codes) - 1:
            time.sleep(ACCESS_INTERVAL)

    save_data(data)
    print(f"\n保存完了: {MAX_GYAKU_FILE}")


if __name__ == "__main__":
    main()
