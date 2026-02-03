"""優待クロス管理サイト 設定ファイル"""

from pathlib import Path

# ベースディレクトリ
BASE_DIR = Path(__file__).parent

# データディレクトリ
DATA_DIR = BASE_DIR / "data"
HTML_CACHE_DIR = DATA_DIR / "html_cache"
GYAKU_HIBOKU_DIR = DATA_DIR / "gyaku_hiboku"
STOCK_PRICE_DIR = DATA_DIR / "stock_price"
DIVIDEND_DIR = DATA_DIR / "dividend"
IPPAN_ZAIKO_DIR = DATA_DIR / "ippan_zaiko"
KACHI_CSV = DATA_DIR / "kachi.csv"

# 出力ディレクトリ
HTML_DIR = BASE_DIR / "html"
MONTHS_DIR = HTML_DIR / "months"
STOCKS_DIR = HTML_DIR / "stocks"

# テンプレートディレクトリ
TEMPLATES_DIR = BASE_DIR / "templates"

# 外部URL
INVEST_JP_BASE_URL = "https://invest.jp"
