"""Jinja2テンプレートからHTMLを生成"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import csv
from datetime import datetime, date, timedelta
import jpholiday
from jinja2 import Environment, FileSystemLoader
from config import (
    TEMPLATES_DIR,
    HTML_DIR,
    MONTHS_DIR,
    STOCKS_DIR,
    KACHI_CSV,
    GYAKU_HIBOKU_DIR,
)
from scripts.calc_performance import calculate_all_performance, StockPerformance
from scripts.fetch_zaiko import load_latest_zaiko

# 金利計算用定数
INTEREST_RATE = 1.7  # 年利1.7%
# 期待利回り計算の保有資産（円）
PORTFOLIO_CAPITAL = 6_000_000


def parse_settlement_month(settlement_month: int) -> tuple[int, int | None]:
    """settlement_monthを月と日に分解

    Args:
        settlement_month: 1-12は月末権利、101-1231は月中権利（例：220=2月20日）

    Returns:
        (month, day): dayはNoneなら月末権利
    """
    if settlement_month <= 12:
        return (settlement_month, None)
    # 3桁以上は月中権利（例：220 → 2月20日、1115 → 11月15日）
    month = settlement_month // 100
    day = settlement_month % 100
    return (month, day)


def is_business_day(d: date) -> bool:
    """営業日かどうかを判定（土日祝を除く）"""
    if d.weekday() >= 5:  # 土日
        return False
    if jpholiday.is_holiday(d):  # 祝日
        return False
    return True


def get_next_business_day(d: date) -> date:
    """次の営業日を取得（当日が営業日なら当日を返す）"""
    while not is_business_day(d):
        d += timedelta(days=1)
    return d


def get_last_business_day_of_month(year: int, month: int) -> date:
    """月末の最終営業日を取得"""
    # 翌月1日から1日戻って月末日を取得
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    # 最終営業日を探す
    while not is_business_day(last_day):
        last_day -= timedelta(days=1)
    return last_day


def get_kenri_tsuki_bi(year: int, month: int) -> date:
    """権利付日を取得（月末最終営業日の2営業日前）"""
    last_biz_day = get_last_business_day_of_month(year, month)

    # 2営業日前を計算
    kenri_bi = last_biz_day
    business_days_back = 0
    while business_days_back < 2:
        kenri_bi -= timedelta(days=1)
        if is_business_day(kenri_bi):
            business_days_back += 1

    return kenri_bi


def get_kenri_date_for_day(year: int, month: int, day: int) -> date:
    """月中権利日の権利付日を取得（指定日の2営業日前）

    Args:
        year: 年
        month: 月
        day: 権利確定日

    Returns:
        権利付日
    """
    # 権利確定日
    kenri_kakutei = date(year, month, day)

    # 2営業日前を計算
    kenri_bi = kenri_kakutei
    business_days_back = 0
    while business_days_back < 2:
        kenri_bi -= timedelta(days=1)
        if is_business_day(kenri_bi):
            business_days_back += 1

    return kenri_bi


def calculate_month_interest(settlement_month: int, base_date: date | None = None) -> dict:
    """
    指定月の金利情報を計算

    Args:
        settlement_month: 1-12は月末権利、3桁以上は月中権利（例：220=2月20日）

    Returns:
        dict: {
            'kenri_date': 権利付日,
            'start_date': 計算開始日,
            'days': 日数,
            'interest': 金利%,
        }
    """
    if base_date is None:
        base_date = date.today()

    # 今日が休日なら翌営業日を起点とする
    start_date = get_next_business_day(base_date)

    # settlement_monthを分解
    month, day = parse_settlement_month(settlement_month)

    # 権利付日を計算（今年または来年）
    year = base_date.year
    if day is None:
        # 月末権利
        kenri_date = get_kenri_tsuki_bi(year, month)
        if kenri_date < start_date:
            kenri_date = get_kenri_tsuki_bi(year + 1, month)
    else:
        # 月中権利
        kenri_date = get_kenri_date_for_day(year, month, day)
        if kenri_date < start_date:
            kenri_date = get_kenri_date_for_day(year + 1, month, day)

    # 日数計算（カレンダー日数）
    days = (kenri_date - start_date).days

    # 金利計算: 年利 × (日数 / 365)
    interest = INTEREST_RATE * (days / 365)

    return {
        'kenri_date': kenri_date,
        'start_date': start_date,
        'days': days,
        'interest': round(interest, 3),
    }


def load_stocks() -> list[dict]:
    """銘柄データを読み込み"""
    if not KACHI_CSV.exists():
        return []

    with open(KACHI_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def get_stocks_with_performance(month: int | None = None) -> list[dict]:
    """パフォーマンス計算済みの銘柄リストを取得"""
    results = calculate_all_performance(month)
    return [r.to_dict() for r in results]


def load_gyaku_hiboku(code: str) -> list[dict]:
    """逆日歩履歴を読み込み"""
    gyaku_file = GYAKU_HIBOKU_DIR / f"{code}.csv"

    if not gyaku_file.exists():
        return []

    with open(gyaku_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def setup_jinja_env() -> Environment:
    """Jinja2環境をセットアップ"""
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
    )
    return env


def get_mid_month_pages() -> list[dict]:
    """月中権利のページ情報を取得"""
    all_months = get_all_settlement_months()
    mid_months = []
    for sm in all_months:
        if sm > 12:  # 月中権利のみ
            mid_months.append({
                "settlement_month": sm,
                "filename": get_settlement_month_filename(sm),
                "display": get_settlement_month_display(sm),
            })
    return mid_months


def generate_index(env: Environment, stocks: list[dict]) -> None:
    """トップページを生成"""
    template = env.get_template("index.html")

    # 月中権利のページ情報を取得
    mid_month_pages = get_mid_month_pages()

    html = template.render(
        stock_count=len(stocks),
        last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        mid_month_pages=mid_month_pages,
        base_path="./",
    )

    output_file = HTML_DIR / "index.html"
    output_file.write_text(html, encoding="utf-8")
    print(f"Generated: {output_file}")


def calculate_max_portfolio_yield(stocks: list[dict], capital: float) -> float:
    """最大利回りとなるように資金内で銘柄を選ぶ（簡易貪欲）"""
    candidates = []
    for stock in stocks:
        amount = float(stock.get("required_amount") or 0)
        performance = stock.get("performance")
        if amount > 0 and performance is not None:
            candidates.append((float(performance), amount))

    candidates.sort(key=lambda x: x[0], reverse=True)

    remaining = capital
    total_amount = 0.0
    weighted_perf = 0.0
    for performance, amount in candidates:
        if amount <= remaining:
            remaining -= amount
            total_amount += amount
            weighted_perf += performance * amount

    return (weighted_perf / total_amount) if total_amount > 0 else 0.0


def compute_monthly_expected_yields(capital: float) -> dict[int, float]:
    """各月の期待利回り（最大資金内の収益利回り）を計算"""
    expected = {}
    for month in range(1, 13):
        stocks = get_stocks_with_performance(month)
        expected[month] = calculate_max_portfolio_yield(stocks, capital)
    return expected


def get_all_settlement_months() -> list[int]:
    """kachi.csvからユニークなsettlement_monthを取得"""
    stocks = load_stocks()
    months = set()
    for stock in stocks:
        try:
            sm = int(stock.get("settlement_month", 0))
            if sm > 0:
                months.add(sm)
        except (ValueError, TypeError):
            continue
    # 月末権利（1-12）を先に、月中権利（3桁以上）を後に
    return sorted(months, key=lambda x: (x > 12, x))


def get_settlement_month_filename(settlement_month: int) -> str:
    """settlement_monthからファイル名を生成"""
    if settlement_month <= 12:
        return f"{settlement_month:02d}.html"
    # 月中権利: 220 → 0220.html
    return f"{settlement_month:04d}.html"


def get_settlement_month_display(settlement_month: int) -> str:
    """settlement_monthから表示用文字列を生成"""
    month, day = parse_settlement_month(settlement_month)
    if day is None:
        return f"{month}月"
    return f"{month}月{day}日"


def generate_month_pages(env: Environment) -> None:
    """月別ページを生成（パフォーマンス降順）"""
    template = env.get_template("month.html")
    expected_yields = compute_monthly_expected_yields(PORTFOLIO_CAPITAL)

    # kachi.csvから全てのsettlement_monthを取得
    all_settlement_months = get_all_settlement_months()

    # 各settlement_monthのページを生成
    for settlement_month in all_settlement_months:
        # パフォーマンス計算済みデータを取得（既に降順ソート済み）
        month_stocks = get_stocks_with_performance(settlement_month)

        # 月を取得（在庫データ取得用）
        month, day = parse_settlement_month(settlement_month)

        # 在庫データを読み込んでマージ
        zaiko_data = load_latest_zaiko(month)
        for stock in month_stocks:
            code = stock.get("code", "")
            if code in zaiko_data:
                stock["zaiko"] = zaiko_data[code].get("zaiko", {})
                # 制限データをマージ（APIデータから取得）
                stock["restriction"] = zaiko_data[code].get("restriction", "")
                # 最大逆日歩率を計算（1株あたり÷株価×100）
                max_gyaku = zaiko_data[code].get("max_gyaku")
                price = stock.get("price", 0)
                required_shares = stock.get("required_shares", 0)
                if max_gyaku and price > 0 and required_shares > 0:
                    per_share = max_gyaku / required_shares
                    stock["max_gyaku_rate"] = round(per_share / price * 100, 2)
                else:
                    stock["max_gyaku_rate"] = None
            else:
                stock["zaiko"] = {}
                stock["restriction"] = ""
                stock["max_gyaku_rate"] = None

        # 金利情報を計算
        interest_info = calculate_month_interest(settlement_month)

        # 現在の月を取得（月利回り計算用）
        current_month = date.today().month

        # 表示用の月
        month_display = get_settlement_month_display(settlement_month)

        html = template.render(
            month=settlement_month,
            month_display=month_display,
            stocks=month_stocks,
            interest_info=interest_info,
            current_month=current_month,
            expected_yield_threshold=sum(
                expected_yields.get(m, 0) for m in range(1, month + 1)
            ),
            base_path="../",
        )

        output_file = MONTHS_DIR / get_settlement_month_filename(settlement_month)
        output_file.write_text(html, encoding="utf-8")
        print(f"Generated: {output_file} ({len(month_stocks)}銘柄)")


def generate_stock_pages(env: Environment) -> None:
    """銘柄別ページを生成（パフォーマンス計算済みデータを使用）"""
    template = env.get_template("stock.html")

    # 全月のパフォーマンスデータを取得（基本株数のみ、+xxxは除外）
    all_stocks = get_stocks_with_performance()

    # コードごとに最初のエントリのみ使用（重複排除）
    seen_codes = set()
    unique_stocks = []
    for stock in all_stocks:
        code = stock.get("code", "")
        # 差分エントリ（+xxx株）はスキップ
        if stock.get("is_differential", False):
            continue
        if code and code not in seen_codes:
            seen_codes.add(code)
            unique_stocks.append(stock)

    for stock in unique_stocks:
        code = stock.get("code", "")
        if not code:
            continue

        gyaku_history = load_gyaku_hiboku(code)

        # 利回り計算（simple_yieldは既に%表記）
        simple_yield = stock.get("simple_yield", 0)
        stock["yield"] = round(simple_yield, 2) if simple_yield else None

        # 必要資金計算
        price = stock.get("price", 0)
        required_shares = stock.get("required_shares", 0)
        stock["required_amount"] = price * required_shares if price and required_shares else 0

        html = template.render(
            stock=stock,
            gyaku_hiboku_history=gyaku_history,
            base_path="../",
        )

        output_file = STOCKS_DIR / f"{code}.html"
        output_file.write_text(html, encoding="utf-8")
        print(f"Generated: {output_file}")


def generate_all() -> None:
    """全HTMLを生成"""
    env = setup_jinja_env()
    stocks = load_stocks()

    print(f"Loaded {len(stocks)} stocks from kachi.csv")

    # ディレクトリ作成
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    MONTHS_DIR.mkdir(parents=True, exist_ok=True)
    STOCKS_DIR.mkdir(parents=True, exist_ok=True)

    generate_index(env, stocks)
    generate_month_pages(env)  # パフォーマンス計算結果を使用
    generate_stock_pages(env)  # パフォーマンス計算結果を使用

    print("Done!")


if __name__ == "__main__":
    generate_all()
