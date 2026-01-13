"""gokigen-life.tokyo APIから在庫データを取得"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import requests
from datetime import datetime
from config import IPPAN_ZAIKO_DIR


API_URL = "https://gokigen-life.tokyo/api/00ForWeb/ForZaiko2.php"
HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "https://gokigen-life.tokyo/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

# 証券会社の在庫フィールドマッピング
BROKER_FIELDS = {
    "nikko": "nkc",      # 日興
    "kabucom": "kbc",    # カブコム
    "rakuten": "rtc",    # 楽天
    "sbi": "sbc",        # SBI
    "gmo": "gmc",        # GMO
    "matsui": "mtc",     # 松井
    "monex": "mxc",      # マネックス
}


def fetch_zaiko(month: int) -> list[dict]:
    """指定月の在庫データを取得"""
    try:
        response = requests.post(
            API_URL,
            headers=HEADERS,
            data={"month": month},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        # 最初のダミーレコード(code=0000)を除外
        return [item for item in data if item.get("code") != "0000"]

    except requests.RequestException as e:
        print(f"Error fetching zaiko: {e}")
        return []


def parse_zaiko(data: list[dict]) -> dict[str, dict]:
    """在庫データをコードをキーにした辞書に変換"""
    result = {}

    for item in data:
        code = item.get("code")
        if not code or code == "0000":  # ダミーレコード除外
            continue

        # 各証券会社の在庫株数（*volフィールド）
        def parse_int(val):
            if val is None:
                return None
            try:
                v = int(val)
                # タイムスタンプっぽい巨大な値は除外
                return v if v < 100000000 else None
            except (ValueError, TypeError):
                return None

        zaiko = {
            "nikko": parse_int(item.get("nvol")),
            "kabucom": parse_int(item.get("kvol")),
            "rakuten": parse_int(item.get("rvol")),
            "sbi": parse_int(item.get("svol")),
            "gmo": parse_int(item.get("gvol")),
            "matsui": parse_int(item.get("mvol")),
            "monex": parse_int(item.get("xvol")),
        }

        # 理論逆日歩（最大逆日歩）
        riron_gyaku = parse_int(item.get("riron_gyaku"))

        result[code] = {
            "name": item.get("name"),
            "zaiko": zaiko,
            "taisyaku": item.get("taisyaku"),
            "max_gyaku": riron_gyaku,  # 最大逆日歩
            "gyaku_days": parse_int(item.get("gyaku_days")),  # 逆日歩日数
            "updated": datetime.now().isoformat(),
        }

    return result


def save_zaiko(zaiko_data: dict, month: int) -> Path:
    """在庫データをJSONに保存"""
    IPPAN_ZAIKO_DIR.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    output_file = IPPAN_ZAIKO_DIR / f"zaiko_{month:02d}_{today}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(zaiko_data, f, ensure_ascii=False, indent=2)

    print(f"Saved: {output_file} ({len(zaiko_data)}銘柄)")
    return output_file


def fetch_and_save(month: int) -> dict:
    """取得→パース→保存"""
    print(f"Fetching {month}月の在庫データ...")
    raw_data = fetch_zaiko(month)

    if not raw_data:
        print("データが取得できませんでした")
        return {}

    zaiko_data = parse_zaiko(raw_data)
    save_zaiko(zaiko_data, month)

    return zaiko_data


def load_latest_zaiko(month: int) -> dict:
    """最新の在庫データを読み込み"""
    pattern = f"zaiko_{month:02d}_*.json"
    files = sorted(IPPAN_ZAIKO_DIR.glob(pattern), reverse=True)

    if not files:
        return {}

    with open(files[0], encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="在庫データを取得")
    parser.add_argument("--month", "-m", type=int, default=datetime.now().month,
                        help="対象月 (デフォルト: 今月)")
    parser.add_argument("--all", action="store_true", help="全月取得")

    args = parser.parse_args()

    if args.all:
        for m in range(1, 13):
            fetch_and_save(m)
    else:
        fetch_and_save(args.month)
