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
from config import DATA_DIR, KACHI_CSV, GYAKU_HIBOKU_DIR, STOCK_PRICE_DIR


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


def load_parsed_stocks() -> list[dict]:
    """パース済み銘柄データを読み込み"""
    json_file = DATA_DIR / "parsed_stocks.json"
    if not json_file.exists():
        return []

    with open(json_file, encoding="utf-8") as f:
        return json.load(f)


def get_latest_gyaku_hiboku(stock: dict, settlement_month: int = 0) -> float:
    """過去3年分の逆日歩平均を取得（1株あたり）

    全ての権利月のデータを使用（2月銘柄でも8月のデータを含む）
    """
    records = stock.get("gyaku_hiboku", [])
    if not records:
        return 0.0

    # 過去3年分（最大6レコード程度）を取得
    recent_records = records[:6]

    if not recent_records:
        return 0.0

    # 平均を計算
    total = sum(r.get("gyaku_hiboku", 0.0) for r in recent_records)
    return total / len(recent_records)


def get_latest_dividend(stock: dict) -> float:
    """最新の配当を取得（1株あたり）"""
    records = stock.get("dividend", [])
    # 実績の最新を取得（予想を除く）
    for r in records:
        if not r.get("is_forecast", False):
            continue
    # 予想がなければ実績の最新
    for r in reversed(records):
        if not r.get("is_forecast", False):
            return r.get("amount", 0.0)
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
    """最新の株価を取得（yfinance優先、なければ逆日歩履歴から）"""
    global _latest_prices

    # 最新株価をロード（初回のみ）
    if _latest_prices is None:
        _latest_prices = load_latest_prices()

    # yfinanceの最新株価があればそれを使う
    if code and code in _latest_prices:
        return _latest_prices[code]

    # フォールバック: 逆日歩履歴の終値
    records = stock.get("gyaku_hiboku", [])
    if not records:
        return 0.0
    return records[0].get("close_price", 0.0)


def calculate_all_performance(month: int | None = None) -> list[StockPerformance]:
    """全銘柄のパフォーマンスを計算（同一銘柄・異なる株数も別々に表示）"""
    kachi_list = load_kachi()
    parsed_stocks = load_parsed_stocks()

    # parsed_stocksを辞書化（高速検索用）
    stocks_dict = {s.get("code", ""): s for s in parsed_stocks}

    results = []

    # kachi.csvの各行を個別に処理
    for kachi_data in kachi_list:
        code = kachi_data.get("code", "")

        # 月でフィルタ
        settlement_month = int(kachi_data.get("settlement_month", 0))
        if month and settlement_month != month:
            continue

        # parsed_stocksから該当銘柄を取得
        stock = stocks_dict.get(code)
        if not stock:
            # parsed_stocks.jsonにない銘柄はスキップ
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
            name=kachi_data.get("name", stock.get("name", "")),
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
