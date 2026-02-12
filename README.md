# yuutai-site

優待クロス管理サイト - 株主優待のパフォーマンス管理ダッシュボード

## 概要

株主優待クロス取引のパフォーマンスを計算・表示する静的サイト。
GitHub Actionsで自動ビルド・デプロイ。

## ディレクトリ構造

```
yuutai-site/
├── data/
│   ├── kachi.csv           # 銘柄マスタ（優待価値等）
│   └── ippan_zaiko/        # 一般信用在庫データ（JSON）
├── scripts/
│   ├── calc_performance.py # パフォーマンス計算
│   ├── fetch_zaiko.py      # 在庫データ取得（gokigen-life API）
│   ├── generate_html.py    # HTML生成
│   └── parse_invest_jp.py  # 逆日歩履歴パース
├── templates/              # Jinja2テンプレート
├── html/                   # 生成されたHTML（GitHub Pagesで公開）
└── config.py               # 設定
```

## API情報

### Vercelデプロイ時の依存関係

- `api/zaiko.py` の依存は `api/requirements.txt` に記載する
- `api/pyproject.toml` はVercel Pythonビルド用に保持する（削除しない）
- ルート `requirements.txt` はデータ生成スクリプト向け（`pandas`, `yfinance` など重い依存を含む）
- API関数に重い依存を含めると、VercelのServerless Functionサイズ制限（250MB）を超えてデプロイ失敗する

### gokigen-life 在庫API

**アプリ用API（正確なデータ）**
```
POST https://gokigen-life.tokyo/api/00ForWeb/ForIonicZaikoPon.php
Content-Type: application/x-www-form-urlencoded
Origin: ionic://localhost

（ボディなし）
```

レスポンス（JSON配列）:
```json
{
  "code": "7545",
  "nvol": "0",        // 日興在庫
  "rvol": null,       // 楽天在庫
  "kvol": null,       // カブコム在庫
  "svol": null,       // SBI在庫
  "gvol": null,       // GMO在庫
  "mvol": null,       // 松井在庫
  "xvol": null        // マネックス在庫
}
```

**Web用API（古い・データが不正確な場合あり）**
```
POST https://gokigen-life.tokyo/api/00ForWeb/ForZaiko2.php
data: month=2
```

## settlement_month（権利月）の仕様

- `1-12`: 月末権利日（例: `2` = 2月末）
- `3桁以上`: 月中権利日（例: `220` = 2月20日、`1115` = 11月15日）

HTMLファイル名:
- 月末: `02.html`
- 月中: `0220.html`

## 開発

```bash
# 在庫データ取得
python scripts/fetch_zaiko.py --month 2

# HTML生成
python scripts/generate_html.py

# パフォーマンス確認
python scripts/calc_performance.py --month 2
```

---

# mitmproxy 設定メモ

アプリのAPI通信をキャプチャするための設定。

## 重要: mitmweb（WebUI）のトークン問題

**mitmproxy 12.x以降、WebUIにトークン認証が必須になった。**

- 以前は `http://localhost:8081` で普通にアクセスできた
- 現在は起動時にコンソールに表示される `?token=xxx` をURLに付けないと**403エラー**
- バックグラウンド実行だとトークンがキャプチャできない
- `--set web_password=xxx` も効かない

**結論: mitmdumpを使う（WebUIなし）**
- トークン認証不要
- コマンドラインで十分解析可能
- 安定動作

## 起動方法

### mitmdump（推奨）
```bash
# 起動
mitmdump --listen-host 0.0.0.0 --listen-port 8080 -w /tmp/mitm_flows &

# ログ解析
mitmdump -n -r /tmp/mitm_flows | grep "gokigen"

# 詳細表示
mitmdump -n -r /tmp/mitm_flows --set flow_detail=4 | grep -A20 "ForIonic"
```

### mitmweb（非推奨・トークン問題あり）
```bash
# 起動（フォアグラウンドでないとトークンが取れない）
mitmweb --listen-host 0.0.0.0 --listen-port 8080 \
  --web-host 0.0.0.0 --web-port 8081 \
  --no-web-open-browser

# コンソールに表示される ?token=xxx をURLに付けてアクセス
# 例: http://localhost:8081/?token=5d44e66e0b9b54fb067a735a4c862eec

# ※ バックグラウンド実行(&)するとトークンが取れない → 403エラー
# ※ 素直にmitmdumpを使った方が楽
```

## プロキシ設定

### MacのIPアドレス確認
```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
# 例: 192.168.0.160
```

### iPhone
1. 設定 → Wi-Fi → 接続中のWi-Fi (i) → HTTPプロキシ → 手動
2. サーバ: `192.168.0.160`（MacのIP）
3. ポート: `8080`

### Android（ADB経由）
```bash
# 有効化
adb shell settings put global http_proxy 192.168.0.160:8080

# 無効化
adb shell settings put global http_proxy :0
```

## 証明書インストール

HTTPS通信をキャプチャするには証明書のインストールが必要。

### iPhone
1. プロキシ設定後、Safariで `http://mitm.it` にアクセス
2. Apple選択 → ダウンロード
3. 設定 → 一般 → VPNとデバイス管理 → mitmproxy → インストール
4. **重要**: 設定 → 一般 → 情報 → 証明書信頼設定 → mitmproxyをオン

### Android
```bash
# 証明書をプッシュ
adb push ~/.mitmproxy/mitmproxy-ca-cert.cer /sdcard/Download/
```
設定 → セキュリティ → 暗号化と認証情報 → 証明書をインストール → CA証明書

### Mac
```bash
open ~/.mitmproxy/mitmproxy-ca-cert.cer
# キーチェーンアクセスで「常に信頼」に変更
```

## 停止

```bash
pkill -f mitmdump
pkill -f mitmweb

# iPhoneのプロキシ設定も解除すること
```
