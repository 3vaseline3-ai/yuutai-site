"""gokigen-life.tokyo APIから在庫データを取得"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from curl_cffi import requests
from datetime import datetime
from config import IPPAN_ZAIKO_DIR


API_URL = "https://gokigen-life.tokyo/api/00ForWeb/ForZaiko2.php"
HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "https://gokigen-life.tokyo/",
}


def fetch_zaiko(month: int) -> list[dict]:
    """指定月の在庫データを取得"""
    try:
        response = requests.post(
            API_URL,
            headers=HEADERS,
            data={"month": month},
            timeout=30,
            impersonate="chrome"
        )
        response.raise_for_status()
        data = response.json()

        # 最初のダミーレコード(code=0000)を除外
        return [item for item in data if item.get("code") != "0000"]

    except Exception as e:
        print(f"Error fetching zaiko: {e}")
        return []


def parse_zaiko(data: list[dict]) -> dict[str, dict]:
    """在庫データをコードをキーにした辞書に変換（API全データ保存）"""
    result = {}

    def parse_int(val):
        if val is None:
            return None
        try:
            v = int(val)
            # タイムスタンプっぽい巨大な値は除外
            return v if v < 100000000 else None
        except (ValueError, TypeError):
            return None

    def parse_float(val):
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    for item in data:
        code = item.get("code")
        if not code or code == "0000":  # ダミーレコード除外
            continue

        # 各証券会社の在庫株数（*volフィールド）
        zaiko = {
            "nikko": parse_int(item.get("nvol")),
            "kabucom": parse_int(item.get("kvol")),
            "rakuten": parse_int(item.get("rvol")),
            "sbi": parse_int(item.get("svol")),
            "gmo": parse_int(item.get("gvol")),
            "matsui": parse_int(item.get("mvol")),
            "monex": parse_int(item.get("xvol")),
        }

        # 貸借銘柄判定
        taisyaku_val = item.get("taisyaku", "")
        is_taishaku = "貸借" in taisyaku_val

        # 逆日歩規制（停止/注意）
        restriction_raw = item.get("recent_gyaku_kisei") or ""
        if "停止" in restriction_raw:
            restriction = "停止"
        elif "注意" in restriction_raw:
            restriction = "注意"
        else:
            restriction = ""

        result[code] = {
            "name": item.get("name"),
            "zaiko": zaiko,
            "taisyaku": taisyaku_val,
            "is_taishaku": is_taishaku,
            "kabuka": parse_int(item.get("kabuka")),  # 株価
            "kabusu": parse_int(item.get("kabusu")),  # 必要株数
            "max_gyaku": parse_int(item.get("riron_gyaku")),  # 最大逆日歩
            "gyaku_days": parse_int(item.get("gyaku_days")),  # 逆日歩日数
            "avg5_gyaku": parse_float(item.get("avg5_gyaku")),  # 5年平均逆日歩
            "haito": parse_int(item.get("haito")),  # 配当
            "gl_value": parse_int(item.get("gl_value")),  # 優待価値（gokigen-life評価）
            "yutai": item.get("yutai"),  # 優待内容
            "yutai_syubetsu": item.get("yutai_syubetsu"),  # 優待種別
            "restriction": restriction,  # 停止/注意
            "d_kenri": item.get("d_kenri"),  # 権利確定日
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
