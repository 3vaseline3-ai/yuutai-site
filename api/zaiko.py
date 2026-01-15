"""
Vercel Serverless Function - 在庫取得API

エンドポイント:
  /api/zaiko          - 全銘柄の在庫取得
  /api/zaiko?code=3387 - 特定銘柄の在庫取得
"""

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError


# gokigen-life アプリ版API（リアルタイム在庫）
APP_API_URL = "https://gokigen-life.tokyo/api/00ForWeb/ForIonicZaikoPon.php"

# Ionicアプリを偽装するヘッダー
APP_HEADERS = {
    "Accept": "*/*",
    "Origin": "ionic://localhost",
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15",
}


def fetch_zaiko_from_gokigen() -> dict:
    """gokigen-life APIから在庫データを取得"""
    try:
        req = Request(APP_API_URL, method="POST", headers=APP_HEADERS)
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))

            # 銘柄コードをキーにした辞書に変換
            result = {}
            for item in data:
                code = item.get("code", "")
                if code and code != "0000":
                    result[code] = {
                        "code": code,
                        "name": item.get("name", ""),
                        "nvol": item.get("nvol", 0),  # 日興
                        "kvol": item.get("kvol", 0),  # カブコム
                        "rvol": item.get("rvol", 0),  # 楽天
                        "svol": item.get("svol", 0),  # SBI
                        "gvol": item.get("gvol", 0),  # GMO
                        "mvol": item.get("mvol", 0),  # 松井
                    }
            return result
    except Exception as e:
        return {"error": str(e)}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        code = params.get('code', [''])[0]

        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, max-age=0')
        self.end_headers()

        # 在庫データ取得
        zaiko_data = fetch_zaiko_from_gokigen()

        if "error" in zaiko_data:
            result = {"error": zaiko_data["error"]}
        elif code:
            # 特定銘柄
            if code in zaiko_data:
                result = {"data": zaiko_data[code]}
            else:
                result = {"error": f"銘柄コード {code} が見つかりません"}
        else:
            # 全銘柄
            result = {"data": zaiko_data, "count": len(zaiko_data)}

        self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
