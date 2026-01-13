"""invest-jpから優待情報HTMLをダウンロード"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import re
import time
import argparse
from curl_cffi import requests
from config import HTML_CACHE_DIR

# アクセス制限回避用ヘッダー
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
    "Connection": "keep-alive",
}

# URL
BASE_URL = "https://www.invest-jp.net"
MONTH_URL = BASE_URL + "/yuutai/index/{month}"
DETAIL_URL = BASE_URL + "/yuutai/detail/{code}"

# アクセス間隔（秒）
ACCESS_INTERVAL = 3


def extract_stock_codes(html: str) -> list[str]:
    """月別ページHTMLから銘柄コードを抽出"""
    pattern = r'/yuutai/detail/(\d+)'
    codes = re.findall(pattern, html)
    # 重複を除去して返す
    return list(dict.fromkeys(codes))


def download_page(url: str) -> str | None:
    """指定URLのHTMLをダウンロード"""
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
            impersonate="chrome120"
        )
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"  Error: {e}")
        return None


def download_month(month: int, force: bool = False) -> None:
    """指定月の優待情報HTMLをダウンロード"""
    month_str = f"{month:02d}"
    cache_dir = HTML_CACHE_DIR / month_str
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[{month}月] 月別ページを取得中...")

    # 月別ページをダウンロード
    month_url = MONTH_URL.format(month=month)
    html = download_page(month_url)

    if not html:
        print(f"  月別ページの取得に失敗しました")
        return

    # 銘柄コードを抽出
    codes = extract_stock_codes(html)
    print(f"  {len(codes)}銘柄を検出")

    if not codes:
        return

    # 各銘柄の詳細ページをダウンロード
    for i, code in enumerate(codes, 1):
        output_file = cache_dir / f"{code}.html"

        # 既存ファイルのスキップ判定
        if output_file.exists() and not force:
            print(f"  [{i}/{len(codes)}] {code} - スキップ（既存）")
            continue

        print(f"  [{i}/{len(codes)}] {code} - ダウンロード中...", end="")

        detail_url = DETAIL_URL.format(code=code)
        detail_html = download_page(detail_url)

        if detail_html:
            output_file.write_text(detail_html, encoding="utf-8")
            print(" OK")
        else:
            print(" 失敗")

        # アクセス間隔を空ける
        time.sleep(ACCESS_INTERVAL)

    print(f"[{month}月] 完了")


def download_all_months(force: bool = False) -> None:
    """全月（1〜12月）の優待情報をダウンロード"""
    for month in range(1, 13):
        download_month(month, force)


def main():
    parser = argparse.ArgumentParser(
        description="invest-jpから優待情報HTMLをダウンロード"
    )
    parser.add_argument(
        "--month", "-m",
        type=int,
        choices=range(1, 13),
        metavar="N",
        help="N月のみダウンロード（1-12）"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="全月（1〜12月）をダウンロード"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="既存ファイルを上書き（デフォルトはスキップ）"
    )
    args = parser.parse_args()

    # 引数チェック
    if not args.month and not args.all:
        parser.print_help()
        print("\n--month または --all を指定してください")
        sys.exit(1)

    if args.month and args.all:
        print("--month と --all は同時に指定できません")
        sys.exit(1)

    # 実行
    if args.month:
        download_month(args.month, args.force)
    elif args.all:
        download_all_months(args.force)


if __name__ == "__main__":
    main()
