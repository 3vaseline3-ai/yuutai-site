"""優待クロスのパフォーマンス計算

パフォーマンス計算式:
  実現利益係数 × (1株優待価値 + 配当×0.15) ÷ 現在株価 × 100

実現利益係数（各年）:
  過去の優待クロスパフォーマンス ÷ 逆日歩なしパフォーマンス
  = {(1株優待価値 - 逆日歩 + 配当×0.15) / 終値}
    ÷ {(1株優待価値 + 配当×0.15) / 終値}

※ 実現利益係数は過去3年分の平均
※ データがない銘柄はデフォルト係数0.8を使用
※ 0.15 = 配当調整金の還付率（簡略化）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import csv
import json
from dataclasses import dataclass
from config import (
    DATA_DIR,
    KACHI_CSV,
    GYAKU_HIBOKU_DIR,
    STOCK_PRICE_DIR,
    IPPAN_ZAIKO_DIR,
    INVEST_JP_HTML_DIR,
)
from fetch_zaiko import load_latest_zaiko


# 配当調整金の還付率
DIVIDEND_ADJUSTMENT_RATE = 0.15

# デフォルトの実現利益係数（データがない銘柄用）
DEFAULT_REALIZATION_FACTOR = 0.8

# 実現利益係数の計算に使う年数
REALIZATION_FACTOR_YEARS = 3

# invest-jp HTMLフォルダ名（権利月）
INVEST_JP_MONTH_DIRS = {
    1: "01_january",
    2: "02_february",
    3: "03_march",
    4: "04_april",
    5: "05_may",
    6: "06_june",
    7: "07_july",
    8: "08_august",
    9: "09_september",
    10: "10_october",
    11: "11_november",
    12: "12_december",
}


@dataclass
class StockPerformance:
    """銘柄パフォーマンス"""
    code: str
    name: str
    settlement_month: int
    price: float
    required_shares: int
    yuutai_value: float
    yuutai_content: str
    gyaku_hiboku: float
    dividend: float
    performance: float
    is_taishaku: bool = False
    is_differential: bool = False  # 差分エントリかどうか
    restriction: str = ""  # 停止/注意

    @property
    def required_amount(self) -> float:
        """必要資金"""
        return self.price * self.required_shares

    @property
    def yuutai_per_share(self) -> float:
        """1株あたり優待価値"""
        if self.required_shares == 0:
            return 0
        return self.yuutai_value / self.required_shares

    @property
    def dividend_benefit(self) -> float:
        """配当調整金の還付額（1株あたり）"""
        return self.dividend * DIVIDEND_ADJUSTMENT_RATE

    @property
    def net_benefit_per_share(self) -> float:
        """1株あたり純利益"""
        return self.yuutai_per_share - self.gyaku_hiboku + self.dividend_benefit

    @property
    def simple_yield(self) -> float:
        """シンプル利回り（優待価値÷株数÷株価）"""
        if self.price <= 0 or self.required_shares <= 0:
            return 0.0
        return (self.yuutai_per_share / self.price) * 100

    @property
    def required_shares_display(self) -> str:
        """表示用の必要株数（差分の場合は+付き）"""
        formatted = f"{self.required_shares:,}"
        if self.is_differential:
            return f"+{formatted}"
        return formatted

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "settlement_month": self.settlement_month,
            "price": self.price,
            "required_shares": self.required_shares,
            "required_shares_display": self.required_shares_display,
            "required_amount": self.required_amount,
            "yuutai_value": self.yuutai_value,
            "yuutai_content": self.yuutai_content,
            "gyaku_hiboku": self.gyaku_hiboku,
            "dividend": self.dividend,
            "dividend_benefit": round(self.dividend_benefit, 2),
            "net_benefit_per_share": round(self.net_benefit_per_share, 2),
            "simple_yield": round(self.simple_yield, 4),
            "performance": round(self.performance, 4),
            "is_taishaku": self.is_taishaku,
            "is_differential": self.is_differential,
            "restriction": self.restriction,
        }


def get_invest_jp_html_path(code: str, settlement_month: int | None) -> Path | None:
    """invest-jpの保存HTMLパスを取得"""
    if not settlement_month:
        return None
    month_dir = INVEST_JP_MONTH_DIRS.get(settlement_month)
    if not month_dir:
        return None
    html_path = INVEST_JP_HTML_DIR / month_dir / f"{code}.html"
    return html_path if html_path.exists() else None


def load_invest_jp_history(code: str, settlement_month: int | None) -> list[dict]:
    """invest-jp保存HTMLから逆日歩履歴を読み込み"""
    html_path = get_invest_jp_html_path(code, settlement_month)
    if not html_path:
        return []
    try:
        from scripts.parse_invest_jp import parse_stock_html
    except Exception:
        return []

    data = parse_stock_html(html_path)
    if not data:
        return []
    return data.get("gyaku_hiboku", [])


def load_gyaku_history(code: str, settlement_month: int | None = None) -> list[dict]:
    """逆日歩履歴を読み込み（過去3年分）

    Args:
        code: 銘柄コード

    Returns:
        逆日歩履歴リスト [{"gyaku_hiboku": float, "dividend": float, "close_price": float}, ...]
    """
    invest_records = load_invest_jp_history(code, settlement_month)
    if invest_records:
        return invest_records

    csv_file = GYAKU_HIBOKU_DIR / f"{code}.csv"
    if not csv_file.exists():
        return []

    history = []
    try:
        with open(csv_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= REALIZATION_FACTOR_YEARS:
                    break
                try:
                    history.append({
                        "gyaku_hiboku": float(row.get("gyaku_hiboku", 0) or 0),
                        "dividend": float(row.get("dividend", 0) or 0),
                        "close_price": float(row.get("close_price", 0) or 0),
                    })
                except (ValueError, TypeError):
                    continue
    except Exception:
        return []

    return history


def calc_realization_factor(yuutai_per_share: float, history: list[dict]) -> float:
    """実現利益係数を計算（過去3年平均）

    実現利益係数 = (1株優待価値 - 逆日歩 + 配当×0.15) / (1株優待価値 + 配当×0.15)

    Args:
        yuutai_per_share: 1株あたり優待価値
        history: 逆日歩履歴リスト

    Returns:
        実現利益係数（0.0〜1.0）、データがない場合はデフォルト値
    """
    if not history or yuutai_per_share <= 0:
        return DEFAULT_REALIZATION_FACTOR

    factors = []
    for record in history:
        if len(factors) >= REALIZATION_FACTOR_YEARS:
            break
        gyaku = record.get("gyaku_hiboku", 0)
        dividend = record.get("dividend", 0)
        close_price = record.get("close_price", 0)
        if close_price <= 0:
            continue
        dividend_benefit = dividend * DIVIDEND_ADJUSTMENT_RATE

        actual_perf = (yuutai_per_share - gyaku + dividend_benefit) / close_price
        no_gyaku_perf = (yuutai_per_share + dividend_benefit) / close_price
        if no_gyaku_perf <= 0:
            continue

        factor = actual_perf / no_gyaku_perf
        factors.append(factor)

    if not factors:
        return DEFAULT_REALIZATION_FACTOR

    return sum(factors) / len(factors)


def calc_performance(
    yuutai_per_share: float,
    realization_factor: float,
    dividend: float,
    current_price: float,
) -> float:
    """パフォーマンスを計算

    式: 実現利益係数 × (1株優待価値 + 配当×0.15) ÷ 現在株価 × 100

    Args:
        yuutai_per_share: 1株あたり優待価値（円）
        realization_factor: 実現利益係数
        dividend: 配当（1株あたり、円）
        current_price: 現在の株価（円）

    Returns:
        パフォーマンス（%）
    """
    if current_price <= 0:
        return 0.0

    dividend_benefit = dividend * DIVIDEND_ADJUSTMENT_RATE
    theoretical_benefit = yuutai_per_share + dividend_benefit

    return realization_factor * theoretical_benefit / current_price * 100


def load_kachi() -> list[dict]:
    """優待価値データを読み込み（リスト形式）"""
    if not KACHI_CSV.exists():
        return []

    kachi = []
    with open(KACHI_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kachi.append(row)
    return kachi


# 月別の在庫データキャッシュ
_zaiko_cache: dict[int, dict] = {}


def load_zaiko_for_month(month: int) -> dict:
    """指定月の在庫データを読み込み（キャッシュ付き）"""
    global _zaiko_cache
    if month not in _zaiko_cache:
        _zaiko_cache[month] = load_latest_zaiko(month)
    return _zaiko_cache[month]


def get_stock_from_zaiko(code: str, month: int) -> dict | None:
    """在庫データから銘柄情報を取得"""
    zaiko = load_zaiko_for_month(month)
    return zaiko.get(code)


def get_latest_gyaku_hiboku(stock: dict, settlement_month: int = 0) -> float:
    """5年平均逆日歩を取得（1株あたり）

    APIデータのavg5_gyakuを使用
    """
    avg5 = stock.get("avg5_gyaku")
    if avg5 is not None:
        return float(avg5)
    return 0.0


def get_latest_dividend(stock: dict) -> float:
    """配当を取得（1株あたり）

    APIデータのhaitoを使用
    """
    haito = stock.get("haito")
    if haito is not None:
        return float(haito)
    return 0.0


def load_latest_prices() -> dict[str, float]:
    """yfinanceで取得した最新株価を読み込み"""
    price_file = STOCK_PRICE_DIR / "latest_prices.json"
    if not price_file.exists():
        return {}

    with open(price_file, encoding="utf-8") as f:
        data = json.load(f)
        return data.get("prices", {})


def load_close_prices() -> dict[str, float]:
    """gyaku_hiboku CSVから権利付最終日の終値を読み込み

    各銘柄の最新の権利付最終日の終値を取得
    """
    close_prices = {}

    if not GYAKU_HIBOKU_DIR.exists():
        return close_prices

    for csv_file in GYAKU_HIBOKU_DIR.glob("*.csv"):
        code = csv_file.stem
        try:
            with open(csv_file, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 最初の行（最新）のclose_priceを取得
                    close_price = row.get("close_price", "")
                    if close_price:
                        close_prices[code] = float(close_price)
                    break
        except (ValueError, KeyError):
            continue

    return close_prices


# グローバルにキャッシュ
_latest_prices: dict[str, float] | None = None
_close_prices: dict[str, float] | None = None


def get_latest_price(stock: dict, code: str = "") -> float:
    """株価を取得（権利付最終日の終値優先）

    優先順位:
    1. gyaku_hiboku CSVの権利付最終日の終値
    2. yfinanceの現在値（フォールバック）
    3. APIデータのkabuka（フォールバック）
    """
    global _latest_prices, _close_prices

    # 権利付最終日の終値をロード（初回のみ）
    if _close_prices is None:
        _close_prices = load_close_prices()

    # 権利付最終日の終値があればそれを使う（最優先）
    if code and code in _close_prices:
        return _close_prices[code]

    # フォールバック: yfinanceの現在値
    if _latest_prices is None:
        _latest_prices = load_latest_prices()

    if code and code in _latest_prices:
        return _latest_prices[code]

    # フォールバック: APIデータのkabuka
    kabuka = stock.get("kabuka")
    if kabuka is not None:
        return float(kabuka)

    return 0.0


def get_current_price(stock: dict, code: str = "") -> float:
    """現在の株価を取得（パフォーマンス予測用）

    優先順位:
    1. yfinanceの現在値
    2. APIデータのkabuka
    """
    global _latest_prices

    # yfinanceの現在値をロード（初回のみ）
    if _latest_prices is None:
        _latest_prices = load_latest_prices()

    # yfinanceの現在値があればそれを使う
    if code and code in _latest_prices:
        return _latest_prices[code]

    # フォールバック: APIデータのkabuka
    kabuka = stock.get("kabuka")
    if kabuka is not None:
        return float(kabuka)

    return 0.0


def calculate_all_performance(month: int | None = None) -> list[StockPerformance]:
    """全銘柄のパフォーマンスを計算（同一銘柄・異なる株数も別々に表示）

    新しい計算式:
    パフォーマンス = 実現利益係数 × (1株優待価値 + 配当×0.15) ÷ 現在株価 × 100
    """
    kachi_list = load_kachi()

    results = []

    # kachi.csvの各行を個別に処理
    for kachi_data in kachi_list:
        code = kachi_data.get("code", "")

        # 月でフィルタ
        settlement_month = int(kachi_data.get("settlement_month", 0))
        if month and settlement_month != month:
            continue

        # 在庫データから該当銘柄を取得
        stock = get_stock_from_zaiko(code, settlement_month)
        if not stock:
            # 在庫データにない銘柄はスキップ
            continue

        # 各値を取得
        yuutai_value = float(kachi_data.get("yuutai_value", 0))
        required_shares_raw = str(kachi_data.get("required_shares", "0")).strip()
        is_differential = required_shares_raw.startswith("+")
        required_shares = int(required_shares_raw)

        # 1株あたり優待価値
        yuutai_per_share = yuutai_value / required_shares if required_shares > 0 else 0

        # 配当（APIから取得）
        dividend = get_latest_dividend(stock)

        # 過去の逆日歩履歴を取得して実現利益係数を計算
        history = load_gyaku_history(code, settlement_month)
        realization_factor = calc_realization_factor(yuutai_per_share, history)

        # 現在の株価を取得
        current_price = get_current_price(stock, code)

        # パフォーマンス計算（新しい式）
        perf = calc_performance(
            yuutai_per_share=yuutai_per_share,
            realization_factor=realization_factor,
            dividend=dividend,
            current_price=current_price,
        )

        # 表示用に5年平均逆日歩を取得
        gyaku_hiboku_display = get_latest_gyaku_hiboku(stock, settlement_month)

        result = StockPerformance(
            code=code,
            name=kachi_data.get("name") or stock.get("name", ""),
            settlement_month=settlement_month,
            price=current_price,
            required_shares=required_shares,
            yuutai_value=yuutai_value,
            yuutai_content=kachi_data.get("yuutai_content", ""),
            gyaku_hiboku=gyaku_hiboku_display,
            dividend=dividend,
            performance=perf,
            is_taishaku=stock.get("is_taishaku", False),
            is_differential=is_differential,
            restriction=stock.get("restriction", ""),
        )
        results.append(result)

    # パフォーマンス降順でソート
    results.sort(key=lambda x: x.performance, reverse=True)

    return results


def print_performance_table(results: list[StockPerformance]) -> None:
    """パフォーマンステーブルを表示"""
    print(f"\n{'='*100}")
    print(f"{'コード':>6} {'銘柄名':<20} {'株価':>8} {'株数':>6} {'優待価値':>8} {'逆日歩':>8} {'配当':>6} {'利回り':>8}")
    print(f"{'='*100}")

    for r in results:
        name = r.name[:18] if len(r.name) > 18 else r.name
        print(
            f"{r.code:>6} {name:<20} {r.price:>8,.0f} {r.required_shares:>6} "
            f"{r.yuutai_value:>8,.0f} {r.gyaku_hiboku:>8.2f} {r.dividend:>6.0f} {r.performance:>7.2f}%"
        )

    print(f"{'='*100}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="パフォーマンス計算")
    parser.add_argument("--month", "-m", type=int, help="対象月（1-12）")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")
    args = parser.parse_args()

    results = calculate_all_performance(args.month)

    if not results:
        print("データがありません。kachi.csvに銘柄を登録してください。")
        return

    if args.json:
        output = [r.to_dict() for r in results]
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print_performance_table(results)
        print(f"\n合計: {len(results)}銘柄")


if __name__ == "__main__":
    main()
