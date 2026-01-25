# 優待クロス管理サイト

## プロジェクト概要
優待クロス取引のパフォーマンス管理サイト（静的HTML）

**データソース**: gokigen-life.tokyo API（invest-jpのHTMLパースは廃止済み）

## データ取得状況
| 月 | 状態 |
|----|------|
| 1月 | ✅ 完了（14銘柄表示） |
| 2月 | ✅ 完了（46銘柄表示） |
| 3月 | ✅ 完了（122銘柄表示） |
| 4〜12月 | ⏳ kachi.csv登録待ち |

## ディレクトリ構成

```
yuutai-site/
├── config.py                    # 設定ファイル（パス定義）
├── scripts/
│   ├── fetch_zaiko.py           # 一般信用在庫取得（gokigen-life API）★メイン
│   ├── fetch_stock_price.py     # yfinanceで株価取得
│   ├── calc_performance.py      # パフォーマンス計算
│   ├── generate_html.py         # Jinja2でHTML生成
│   ├── fetch_max_gyaku.py       # 最大逆日歩取得
│   ├── download_invest_jp.py    # [旧] invest-jpからHTMLダウンロード（未使用）
│   ├── parse_invest_jp.py       # [旧] HTMLパース（未使用）
│   ├── scrape_nikko_zaiko.py    # [旧] 日興在庫スクレイピング（未使用）
│   └── convert_yuutai_record.py # 優待記録変換
├── data/
│   ├── kachi.csv                # 銘柄マスタ（優待価値入力）★重要
│   ├── ippan_zaiko/             # 一般信用在庫データ（JSON）
│   ├── stock_price/             # 株価データ
│   ├── gyaku_hiboku/            # [旧] 逆日歩履歴CSV（参照用）
│   ├── dividend/                # [旧] 配当履歴CSV（参照用）
│   ├── html_cache/              # [旧] ダウンロードしたHTML
│   └── parsed_stocks.json       # [旧] パース済み銘柄データ
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

# 在庫更新（gokigen-life API）
python scripts/fetch_zaiko.py --month N   # 指定月
python scripts/fetch_zaiko.py --all       # 全月

# 株価更新
python scripts/fetch_stock_price.py --all

# HTML再生成
python scripts/generate_html.py
```

## データフロー

```
gokigen-life API → fetch_zaiko.py → ippan_zaiko/*.json
                                          ↓
kachi.csv → calc_performance.py ← ←←←←←←←←
                     ↓
            generate_html.py → html/
```

**重要**: kachi.csvに登録されていない銘柄はHTML出力されません。

## 設計決定事項

| 項目 | 方針 | 理由 |
|------|------|------|
| 株価 | yfinance優先、フォールバックでAPIデータ | 最新値取得可能 |
| 逆日歩 | APIの5年平均（avg5_gyaku） | 過去実績ベース |
| 配当 | APIのhaito | 最新予想値 |
| 制限（停止/注意） | APIのrecent_gyaku_kisei | リアルタイム |
| リンク | 相対パス | ローカルで動作するように |
| 同一銘柄・異なる株数 | 別々にランキング表示 | 株数によって利回りが異なるため |

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
| `avg5_gyaku` | - | 5年平均逆日歩 |
| `haito` | - | 配当（1株あたり） |
| `kabuka` | - | 株価 |
| `recent_gyaku_kisei` | - | 規制状態（停止/注意） |
| `riron_gyaku` | - | 最大逆日歩 |
| `gyaku_days` | - | 逆日歩日数 |

### 注意事項
- 最初のレコード（code=0000）はダミー。`*vol`フィールドがタイムスタンプ（更新時刻）になっている
- 実際の銘柄レコードでは`*vol`が在庫株数
- タイムスタンプ判定: 値が1億以上は除外する

## 残りタスク

1. kachi.csv の優待価値入力（手動作業）
2. 4〜12月の銘柄をkachi.csvに追加

## 変更履歴

- 2026/01/13: invest-jp HTMLパースからgokigen-life API完全移行
