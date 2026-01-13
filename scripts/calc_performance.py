"""優待クロスのパフォーマンス計算

パフォーマンス計算式:
  (優待価値÷株数 - 逆日歩 + 配当×0.15315) ÷ 株価 × 100

※ 0.15315 = 配当調整金の還付率（源泉徴収20.315% - 所得税5%）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import csv
import json
from dataclasses import dataclass
from config import DATA_DIR, KACHI_CSV, GYAKU_HIBOKU_DIR, STOCK_PRICE_DIR, IPPAN_ZAIKO_DIR
from fetch_zaiko import load_latest_zaiko


# 配当調整金の還付率
DIVIDEND_ADJUSTMENT_RATE = 0.15315


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


def calc_performance(
    yuutai_value: float,
    required_shares: int,
    gyaku_hiboku: float,
    dividend: float,
    price: float,
) -> float:
    """パフォーマンスを計算

    式: (優待価値÷株数 - 逆日歩 + 配当×0.15315) ÷ 株価 × 100

    Args:
        yuutai_value: 優待価値（円）
        required_shares: 必要株数
        gyaku_hiboku: 逆日歩（1株あたり、円）
        dividend: 配当（1株あたり、円）
        price: 株価（円）

    Returns:
        パフォーマンス（%）
    """
    if price <= 0 or required_shares <= 0:
        return 0.0

    yuutai_per_share = yuutai_value / required_shares
    dividend_benefit = dividend * DIVIDEND_ADJUSTMENT_RATE
    net_benefit = yuutai_per_share - gyaku_hiboku + dividend_benefit

    return (net_benefit / price) * 100


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


# グローバルにキャッシュ
_latest_prices: dict[str, float] | None = None


def get_latest_price(stock: dict, code: str = "") -> float:
    """最新の株価を取得（yfinance優先、なければAPIデータから）"""
    global _latest_prices

    # 最新株価をロード（初回のみ）
    if _latest_prices is None:
        _latest_prices = load_latest_prices()

    # yfinanceの最新株価があればそれを使う
    if code and code in _latest_prices:
        return _latest_prices[code]

    # フォールバック: APIデータのkabuka
    kabuka = stock.get("kabuka")
    if kabuka is not None:
        return float(kabuka)

    return 0.0


def calculate_all_performance(month: int | None = None) -> list[StockPerformance]:
    """全銘柄のパフォーマンスを計算（同一銘柄・異なる株数も別々に表示）"""
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
        gyaku_hiboku = get_latest_gyaku_hiboku(stock, settlement_month)
        dividend = get_latest_dividend(stock)
        price = get_latest_price(stock, code)

        # パフォーマンス計算
        perf = calc_performance(
            yuutai_value=yuutai_value,
            required_shares=required_shares,
            gyaku_hiboku=gyaku_hiboku,
            dividend=dividend,
            price=price,
        )

        result = StockPerformance(
            code=code,
            name=kachi_data.get("name") or stock.get("name", ""),
            settlement_month=settlement_month,
            price=price,
            required_shares=required_shares,
            yuutai_value=yuutai_value,
            yuutai_content=kachi_data.get("yuutai_content", ""),
            gyaku_hiboku=gyaku_hiboku,
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
