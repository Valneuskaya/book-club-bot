import json, os, urllib.request
from http.server import BaseHTTPRequestHandler

TOKEN = os.environ["BOT_TOKEN"]
APP_URL = os.environ["APP_URL"]

def send(chat_id, text, markup):
    data = {"chat_id": chat_id, "text": text, "reply_markup": markup}
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req)

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        msg = body.get("message") or {}
        chat = (msg.get("chat") or {}).get("id")
        if chat and msg.get("text", "").startswith("/start"):
            send(chat, "📚 Карта нашего книжного клуба",
                 {"inline_keyboard": [[{"text": "Открыть карту",
                                        "web_app": {"url": APP_URL}}]]})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
