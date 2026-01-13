"""ダウンロード済みHTMLをパースして優待情報を抽出"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import re
import csv
import json
from bs4 import BeautifulSoup
from config import HTML_CACHE_DIR, DATA_DIR, GYAKU_HIBOKU_DIR, DIVIDEND_DIR


def parse_stock_html(html_path: Path) -> dict | None:
    """銘柄HTMLをパースして情報を抽出"""
    if not html_path.exists():
        return None

    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    data = {}

    # 銘柄コード
    code_elem = soup.find("span", id="code")
    if not code_elem:
        return None
    data["code"] = code_elem.text.strip()

    # 銘柄名
    h1 = soup.find("h1")
    if h1:
        name_match = re.match(r"(.+?)\(", h1.text)
        if name_match:
            data["name"] = name_match.group(1).strip()

    # 売買単位
    lot_elem = soup.find("td", id="lot")
    if lot_elem:
        lot_match = re.search(r"(\d+)", lot_elem.text)
        if lot_match:
            data["lot"] = int(lot_match.group(1))

    # 権利確定月
    kenri_row = soup.find("th", string="優待権利日")
    if kenri_row:
        td = kenri_row.find_next_sibling("td")
        if td:
            month_match = re.search(r"(\d+)月", td.text)
            if month_match:
                data["settlement_month"] = int(month_match.group(1))

    # 貸借銘柄かどうか
    taishaku = soup.find("span", class_="taishaku")
    data["is_taishaku"] = taishaku is not None

    # 現在の制限状態（停止/注意）
    seigen_span = soup.find("span", class_=lambda c: c and c.startswith("seigen"))
    if seigen_span:
        # taishakuより前にある最初のseigenが現在の制限
        # 逆日歩テーブル外のものを取得
        jsf_table = soup.find("table", id="jsf_list")
        if jsf_table:
            # テーブル外のseigenを探す
            for span in soup.find_all("span", class_=lambda c: c and c.startswith("seigen")):
                if not span.find_parent("table"):
                    data["current_restriction"] = span.text.strip()
                    break
            else:
                data["current_restriction"] = ""
        else:
            data["current_restriction"] = seigen_span.text.strip()
    else:
        data["current_restriction"] = ""

    # 逆日歩履歴
    data["gyaku_hiboku"] = parse_gyaku_hiboku_table(soup)

    # 配当履歴
    data["dividend"] = parse_dividend_table(soup)

    # 優待内容
    data["yuutai"] = parse_yuutai_content(soup)

    return data


def parse_gyaku_hiboku_table(soup: BeautifulSoup) -> list[dict]:
    """逆日歩テーブルをパース"""
    records = []
    table = soup.find("table", id="jsf_list")
    if not table:
        return records

    tbody = table.find("tbody")
    if not tbody:
        return records

    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 10:
            continue

        # 日付（PC表示用のdivから取得）
        date_div = tds[0].find("div", class_="d-none d-md-table-cell")
        if date_div:
            date_str = date_div.text.strip()
        else:
            date_str = tds[0].text.strip()

        record = {
            "date": date_str,
            "gyaku_hiboku": parse_number(tds[1].text),
            "max_rate": parse_number(tds[2].text),
            "days": parse_int(tds[3].text),
            "taishaku_diff": parse_int(tds[4].text.replace(",", "")),
            "volume": parse_int(tds[6].text.replace(",", "")),
            "close_price": parse_int(tds[7].text.replace(",", "")),
            "gap": parse_int(tds[8].text.replace(",", "")),
            "dividend": parse_number(tds[9].text),
        }

        # 制限措置
        if len(tds) > 10:
            seigen = tds[10].find("span")
            record["restriction"] = seigen.text.strip() if seigen else ""

        records.append(record)

    return records


def parse_dividend_table(soup: BeautifulSoup) -> list[dict]:
    """配当テーブルをパース"""
    records = []
    h3 = soup.find("h3", string="配当金")
    if not h3:
        return records

    table = h3.find_next("table")
    if not table:
        return records

    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        period = tds[0].text.strip()
        amount_text = tds[1].text.strip()
        amount_match = re.search(r"([\d.]+)", amount_text)
        amount = float(amount_match.group(1)) if amount_match else 0

        # 実績か予想か
        is_forecast = "予" in period

        records.append({
            "period": period,
            "amount": amount,
            "is_forecast": is_forecast,
        })

    return records


def parse_yuutai_content(soup: BeautifulSoup) -> dict:
    """優待内容をパース"""
    result = {"content": "", "tiers": []}

    yuutai_body = soup.find("div", class_="yuutai-body")
    if not yuutai_body:
        return result

    # 優待説明（h3の後のp）
    h3 = yuutai_body.find("h3")
    if h3:
        result["title"] = h3.text.strip()
        p = yuutai_body.find("p")
        if p:
            result["content"] = p.text.strip()

    # 株数ごとの優待内容
    table = yuutai_body.find("table")
    if table:
        for tr in table.find_all("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if th and td:
                shares_match = re.search(r"([\d,]+)", th.text)
                shares = int(shares_match.group(1).replace(",", "")) if shares_match else 0

                value_match = re.search(r"([\d,]+)", td.text)
                value = int(value_match.group(1).replace(",", "")) if value_match else 0

                result["tiers"].append({
                    "shares": shares,
                    "value": value,
                    "description": td.text.strip(),
                })

    return result


def parse_number(text: str) -> float:
    """数値をパース（空文字は0）"""
    text = text.strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_int(text: str) -> int:
    """整数をパース（空文字は0）"""
    text = text.strip().replace(",", "")
    if not text:
        return 0
    try:
        return int(text)
    except ValueError:
        return 0


def parse_month(month: int) -> list[dict]:
    """指定月のHTMLをすべてパース"""
    month_dir = HTML_CACHE_DIR / f"{month:02d}"
    if not month_dir.exists():
        print(f"ディレクトリが存在しません: {month_dir}")
        return []

    stocks = []
    html_files = list(month_dir.glob("*.html"))

    for html_file in html_files:
        data = parse_stock_html(html_file)
        if data:
            stocks.append(data)
            print(f"  {data['code']} {data.get('name', '?')}")

    return stocks


def save_gyaku_hiboku(stocks: list[dict]) -> None:
    """逆日歩履歴を銘柄別CSVに保存"""
    GYAKU_HIBOKU_DIR.mkdir(parents=True, exist_ok=True)

    for stock in stocks:
        code = stock["code"]
        records = stock.get("gyaku_hiboku", [])
        if not records:
            continue

        output_file = GYAKU_HIBOKU_DIR / f"{code}.csv"
        fieldnames = ["date", "gyaku_hiboku", "max_rate", "days", "dividend", "close_price", "restriction"]

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)


def save_dividend(stocks: list[dict]) -> None:
    """配当履歴を銘柄別CSVに保存"""
    DIVIDEND_DIR.mkdir(parents=True, exist_ok=True)

    for stock in stocks:
        code = stock["code"]
        records = stock.get("dividend", [])
        if not records:
            continue

        output_file = DIVIDEND_DIR / f"{code}.csv"
        fieldnames = ["period", "amount", "is_forecast"]

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)


def save_stocks_json(stocks: list[dict], output_file: Path) -> None:
    """全銘柄データをJSONに保存"""
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(stocks, f, ensure_ascii=False, indent=2)
    print(f"Saved: {output_file}")


def get_latest_gyaku_hiboku(stock: dict) -> dict:
    """最新の逆日歩情報を取得"""
    records = stock.get("gyaku_hiboku", [])
    if not records:
        return {"gyaku_hiboku": 0, "days": 0, "dividend": 0, "close_price": 0}
    return records[0]


def get_min_yuutai_tier(stock: dict) -> dict:
    """最小株数の優待情報を取得"""
    tiers = stock.get("yuutai", {}).get("tiers", [])
    if not tiers:
        return {"shares": 0, "value": 0}
    return min(tiers, key=lambda x: x["shares"])


def main():
    import argparse

    parser = argparse.ArgumentParser(description="HTMLをパースして優待情報を抽出")
    parser.add_argument("--month", "-m", type=int, help="対象月（1-12）")
    parser.add_argument("--all", "-a", action="store_true", help="全月をパース")
    parser.add_argument("--save-gyaku", action="store_true", help="逆日歩履歴を保存")
    parser.add_argument("--save-dividend", action="store_true", help="配当履歴を保存")
    args = parser.parse_args()

    if not args.month and not args.all:
        parser.print_help()
        print("\n--month または --all を指定してください")
        sys.exit(1)

    all_stocks = []

    if args.month:
        print(f"\n[{args.month}月] パース中...")
        stocks = parse_month(args.month)
        all_stocks.extend(stocks)
    elif args.all:
        for month in range(1, 13):
            print(f"\n[{month}月] パース中...")
            stocks = parse_month(month)
            all_stocks.extend(stocks)

    print(f"\n合計: {len(all_stocks)}銘柄")

    if args.save_gyaku:
        save_gyaku_hiboku(all_stocks)
        print(f"逆日歩履歴を保存しました: {GYAKU_HIBOKU_DIR}")

    if args.save_dividend:
        save_dividend(all_stocks)
        print(f"配当履歴を保存しました: {DIVIDEND_DIR}")

    # JSON出力
    output_file = DATA_DIR / "parsed_stocks.json"
    save_stocks_json(all_stocks, output_file)


if __name__ == "__main__":
    main()
