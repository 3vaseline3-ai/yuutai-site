"""yuutai_record.csv を kachi.csv に変換"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import csv
import json
from config import DATA_DIR, KACHI_CSV

# 入力ファイル
YUUTAI_RECORD = Path("/Users/nakamuraseiichi/YUTAI/yuutai_record.csv")


def load_parsed_stocks() -> dict[str, dict]:
    """parsed_stocks.json から銘柄名を取得"""
    json_file = DATA_DIR / "parsed_stocks.json"
    if not json_file.exists():
        return {}

    with open(json_file, encoding="utf-8") as f:
        stocks = json.load(f)

    # コードをキーにした辞書に変換
    return {s["code"]: s for s in stocks}


def convert():
    """yuutai_record.csv を kachi.csv に変換"""
    # 銘柄情報を読み込み
    stocks_info = load_parsed_stocks()
    print(f"parsed_stocks.json: {len(stocks_info)}銘柄")

    # yuutai_record.csv を読み込み
    records = []
    with open(YUUTAI_RECORD, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)
    print(f"yuutai_record.csv: {len(records)}レコード")

    # 変換
    kachi_records = []
    missing_names = []

    for row in records:
        code = row["コード"]
        settlement_month = int(row["権利付日"])
        required_shares = int(row["株数"])
        yuutai_value = int(row["優待価値"])

        # 銘柄名を取得
        if code in stocks_info:
            name = stocks_info[code].get("name", "")
        else:
            name = ""
            missing_names.append(code)

        kachi_records.append({
            "code": code,
            "name": name,
            "settlement_month": settlement_month,
            "required_shares": required_shares,
            "yuutai_value": yuutai_value,
            "yuutai_content": "",
        })

    # kachi.csv に保存
    fieldnames = ["code", "name", "settlement_month", "required_shares", "yuutai_value", "yuutai_content"]
    with open(KACHI_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kachi_records)

    print(f"\nSaved: {KACHI_CSV}")
    print(f"  合計: {len(kachi_records)}レコード")

    if missing_names:
        print(f"\n銘柄名が見つからなかったコード ({len(missing_names)}件):")
        for code in missing_names[:10]:
            print(f"  {code}")
        if len(missing_names) > 10:
            print(f"  ... 他 {len(missing_names) - 10}件")


if __name__ == "__main__":
    convert()
