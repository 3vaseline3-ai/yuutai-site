# 優待クロス管理サイト

## プロジェクト概要
優待クロス取引のパフォーマンス管理サイト（静的HTML）

## データ取得状況
| 月 | 状態 |
|----|------|
| 1月 | ✅ 完了（14銘柄表示） |
| 2月 | ✅ 完了（35銘柄表示） |
| 3月 | ✅ 完了（104銘柄表示） |
| 4〜12月 | ❌ 未取得 |

## ディレクトリ構成

```
yuutai-site/
├── config.py                    # 設定ファイル（パス定義）
├── scripts/
│   ├── download_invest_jp.py    # invest-jpからHTMLダウンロード
│   ├── parse_invest_jp.py       # HTMLパース → parsed_stocks.json
│   ├── fetch_stock_price.py     # yfinanceで株価取得
│   ├── generate_html.py         # Jinja2でHTML生成
│   ├── calc_performance.py      # パフォーマンス計算
│   ├── fetch_zaiko.py           # 一般信用在庫取得（gokigen-life API）
│   ├── scrape_nikko_zaiko.py    # 日興在庫スクレイピング（未使用）
│   └── convert_yuutai_record.py # 優待記録変換
├── data/
│   ├── kachi.csv                # 銘柄マスタ（優待価値入力）
│   ├── parsed_stocks.json       # パース済み銘柄データ
│   ├── html_cache/{月}/         # ダウンロードしたHTML
│   ├── gyaku_hiboku/            # 逆日歩履歴CSV
│   ├── dividend/                # 配当履歴CSV
│   ├── stock_price/             # 株価データ
│   └── ippan_zaiko/             # 一般信用在庫データ（JSON）
├── templates/                   # Jinja2テンプレート
│   ├── base.html
│   ├── index.html
│   ├── month.html
│   └── stock.html
└── html/                        # 生成されたHTML
    ├── index.html
    ├── months/{01-12}.html
    └── stocks/{code}.html
```

## 主要コマンド

```bash
# 仮想環境有効化
source .venv/bin/activate

# N月のデータダウンロード
python scripts/download_invest_jp.py --month N
python scripts/parse_invest_jp.py --all --save-gyaku --save-dividend

# 株価更新
python scripts/fetch_stock_price.py --all

# 一般信用在庫取得
python scripts/fetch_zaiko.py --month N   # 指定月
python scripts/fetch_zaiko.py --all       # 全月

# HTML再生成
python scripts/generate_html.py
```

## 設計決定事項

| 項目 | 方針 | 理由 |
|------|------|------|
| 株価 | yfinance優先、フォールバックで権利日終値 | APIで最新取得可能 |
| 逆日歩 | 過去3年平均 | 単年だと異常値に引っ張られる |
| リンク | 相対パス | ローカルで動作するように |
| 同一銘柄・異なる株数 | 別々にランキング表示 | 株数によって利回りが異なるため個別評価 |

### パフォーマンス計算式
```
(優待価値÷株数 - 逆日歩 + 配当×0.15315) ÷ 株価 × 100
```
- 配当×0.15315: 配当調整金（税引後還付分）

## 一般信用在庫API（重要）

### API情報
- **URL**: `https://gokigen-life.tokyo/api/00ForWeb/ForZaiko2.php`
- **メソッド**: POST
- **パラメータ**: `month=N`（1〜12）
- **必須ヘッダー**: `Referer: https://gokigen-life.tokyo/`

### フィールドマッピング（証券会社別在庫株数）

| フィールド | 証券会社 | 備考 |
|-----------|---------|------|
| `nvol` | 日興 | ✅ 在庫株数 |
| `kvol` | カブコム | ✅ 在庫株数 |
| `rvol` | 楽天 | ✅ 在庫株数 |
| `svol` | SBI | ✅ 在庫株数 |
| `gvol` | GMO | ✅ 在庫株数 |
| `mvol` | 松井 | ✅ 在庫株数 |
| `xvol` | マネックス | ✅ 在庫株数 |
| `nkc`, `nkct` | 日興 | ❌ 在庫株数ではない（用途不明、株価に近い値） |
| `kbc`, `kbct`, `kbcv` 等 | 各社 | ❌ 在庫株数ではない |

### 注意事項
- 最初のレコード（code=0000）はダミー。`*vol`フィールドがタイムスタンプ（更新時刻）になっている
- 実際の銘柄レコードでは`*vol`が在庫株数
- タイムスタンプ判定: 値が1億以上は除外する

## 残りタスク

1. kachi.csv の優待価値入力（手動作業）

## 注意点

- kachi.csv にない銘柄は表示されない
- invest-jp.net はCloudflare対策で `curl_cffi` 使用
- 貸借銘柄 = `data-taishaku="true"` / バッジ表示
- ダウンロード間隔: 3秒（ACCESS_INTERVAL）
