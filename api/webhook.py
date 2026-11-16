import difflib, html, json, os, re, urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler

TOKEN = os.environ.get("BOT_TOKEN", "")
APP_URL = os.environ.get("APP_URL", "")
MINIAPP_LINK = os.environ.get("MINIAPP_LINK", "")  # необязательно: t.me/бот/bookmap, для кнопки в группах

COUNTRIES = {
    "US": "США", "GB": "Великобритания", "IE": "Ирландия", "FR": "Франция",
    "CA": "Канада", "KR": "Южная Корея", "AM": "Армения", "AU": "Австралия",
    "ES": "Испания", "JP": "Япония", "BY": "Беларусь", "SE": "Швеция",
    "KG": "Киргизия", "RU": "Россия", "TR": "Турция", "GE": "Грузия",
    "DE": "Германия", "IS": "Исландия", "GL": "Гренландия", "SK": "Словакия",
    "PL": "Польша", "AT": "Австрия", "AR": "Аргентина", "VN": "Вьетнам",
    "NO": "Норвегия", "GR": "Греция", "IT": "Италия", "CN": "Китай",
    "IN": "Индия", "BR": "Бразилия", "MX": "Мексика", "UA": "Украина",
    "NL": "Нидерланды", "CZ": "Чехия", "FI": "Финляндия", "DK": "Дания",
}


def flag(code):
    return "".join(chr(127397 + ord(c)) for c in code) if code and len(code) == 2 else ""


def cname(code):
    return COUNTRIES.get(code, code or "")


def esc(s):
    return html.escape(str(s), quote=False)


def norm(s):
    return str(s).lower().replace("ё", "е")


def tokens(s):
    return re.findall(r"[a-zа-я0-9]+", norm(s))


# ---------- каталог: читаем из той же страницы, что открывает Mini App ----------
def parse(page):
    mk = json.loads(re.search(r"const MK=(\{.*?\});", page, re.S).group(1))
    body = re.search(r"const DATA=\{(.*?)\};\s*const ALL", page, re.S).group(1)
    body = re.sub(r'(?<![\w"])(\d{4}):\[', r'"\1":[', body)
    data = json.loads("{" + body + "}")
    books = []
    for year, rows in data.items():
        for r in rows:
            r = list(r) + [""] * (11 - len(r))
            t, a, c, tags, macros, place, _sc, ot, fy, lg, cv = r[:11]
            books.append({
                "i": len(books), "t": t, "a": a, "c": c, "tags": tags, "y": int(year),
                "g": [mk[k] for k in macros], "place": place or "",
                "ot": ot or "", "fy": fy or "", "lg": lg or "", "cv": cv or "",
            })
    return books


def load():
    with urllib.request.urlopen(APP_URL, timeout=8) as r:
        return parse(r.read().decode("utf-8"))


# ---------- Telegram ----------
def api(method, data):
    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/%s" % (TOKEN, method),
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=8)


def send(chat_id, text, markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True}
    if markup:
        data["reply_markup"] = markup
    api("sendMessage", data)


def app_button(private):
    """Кнопка «Открыть карту»: в личке — Mini App, в группах — обычная ссылка (если задана)."""
    if private and APP_URL:
        return {"text": "Открыть карту", "web_app": {"url": APP_URL}}
    if MINIAPP_LINK:
        return {"text": "Открыть карту", "url": MINIAPP_LINK}
    return None


def markup_of(rows):
    rows = [r for r in rows if r]
    return {"inline_keyboard": rows} if rows else None


# ---------- карточка книги ----------
def card_text(b):
    lines = ["📖 <b>%s</b>" % esc(b["t"])]
    if b["ot"]:
        lines.append("<i>%s</i>" % esc(b["ot"]))
    lines += [esc(b["a"]), ""]
    if b["c"]:
        lines.append("🌍 Где издана: %s %s" % (flag(b["c"]), esc(cname(b["c"]))))
    if b["fy"]:
        lines.append("🗓 Первое издание: %s" % esc(b["fy"]))
    if b["lg"]:
        lines.append("🗣 Язык оригинала: %s" % esc(b["lg"]))
    lines.append("📅 Читали: %d" % b["y"])
    if b["place"]:
        lines.append("📍 Место действия: %s" % esc(b["place"]))
    if b["tags"]:
        lines += ["", "🏷 " + esc(b["tags"])]
    return "\n".join(lines)


def cover_url(b):
    return APP_URL.rstrip("/") + "/" + b["cv"] if b.get("cv") and APP_URL else ""


def send_card(chat, b, private):
    text = card_text(b)
    markup = markup_of([[app_button(private)]])
    url = cover_url(b)
    if url:
        try:  # обложка из репозитория; если файла ещё нет, Telegram откажет и пришлём просто текст
            data = {"chat_id": chat, "photo": url, "caption": text, "parse_mode": "HTML"}
            if markup:
                data["reply_markup"] = markup
            api("sendPhoto", data)
            return
        except Exception as e:
            print("photo failed:", e)
    send(chat, text, markup)


# ---------- /search ----------
def find(books, query):
    words = tokens(query)
    found = []
    if not words:
        return found
    for b in books:
        hay = tokens(" ".join([b["t"], b["a"], b["tags"], " ".join(b["g"]),
                               cname(b["c"]), b["place"], b["ot"], str(b["y"])]))
        if all(any(t.startswith(w) for t in hay) for w in words):
            found.append(b)
    found.sort(key=lambda b: (-b["y"], b["t"]))
    return found


def list_text(found):
    lines = ["Найдено: %d. Нажми на книгу, чтобы открыть карточку." % len(found), ""]
    for b in found[:10]:
        lines.append("%s <b>%s</b>\n%s · %s · %d" % (
            flag(b["c"]), esc(b["t"]), esc(b["a"]), esc(cname(b["c"])), b["y"]))
        lines.append("")
    if len(found) > 10:
        lines.append("…и ещё %d. Уточни запрос." % (len(found) - 10))
    return "\n".join(lines).strip()


def do_search(chat, books, query, private):
    if not tokens(query):
        send(chat, "Напиши, что искать: название, автор, жанр, страна или место действия.\n"
                   "Например: <code>/search Этвуд</code> или <code>/search антиутопия</code>")
        return
    found = find(books, query)
    if not found:
        send(chat, "Ничего не нашлось по запросу «%s»." % esc(query))
    elif len(found) == 1:
        send_card(chat, found[0], private)
    else:
        rows = [[{"text": b["t"][:40], "callback_data": "b:%d" % b["i"]}] for b in found[:10]]
        rows.append([app_button(private)])
        send(chat, list_text(found), markup_of(rows))


# ---------- /stats ----------
def books_word(n):
    m, d = n % 100, n % 10
    if 10 < m < 15:
        return "книг"
    return "книга" if d == 1 else "книги" if 1 < d < 5 else "книг"


def summary(books):
    return (Counter(b["c"] for b in books if b["c"]),
            Counter(g for b in books for g in b["g"]),
            Counter(b["a"] for b in books))


def stats_text(books, arg):
    years = sorted({b["y"] for b in books})
    m = re.search(r"\d{4}", arg or "")
    first = {}
    for b in sorted(books, key=lambda b: b["y"]):
        if b["c"] and b["c"] not in first:
            first[b["c"]] = b["y"]

    if m and int(m.group()) in years:
        y = int(m.group())
        sel = [b for b in books if b["y"] == y]
        countries, genres, authors = summary(sel)
        lines = ["📊 <b>%d год</b>: %d %s" % (y, len(sel), books_word(len(sel))),
                 "Авторов: %d, стран: %d" % (len(authors), len(countries))]
        if countries:
            c, n = countries.most_common(1)[0]
            lines.append("Больше всего книг из: %s %s (%d)" % (flag(c), esc(cname(c)), n))
        if genres:
            g, n = genres.most_common(1)[0]
            lines.append("Любимый жанр: %s (%d)" % (esc(g), n))
        if y > years[0]:
            new = [c for c in countries if first.get(c) == y]
            if new:
                lines.append("Новые страны: " + ", ".join(
                    "%s %s" % (flag(c), esc(cname(c))) for c in new))
        return "\n".join(lines)

    countries, genres, authors = summary(books)
    lines = ["📊 <b>Все годы</b>: %d %s" % (len(books), books_word(len(books))),
             "Авторов: %d, стран: %d" % (len(authors), len(countries)), ""]
    for y in years:
        sel = [b for b in books if b["y"] == y]
        cs = {b["c"] for b in sel if b["c"]}
        lines.append("%d — %d %s, стран: %d" % (y, len(sel), books_word(len(sel)), len(cs)))
    lines.append("")
    if countries:
        c, n = countries.most_common(1)[0]
        lines.append("Любимая страна: %s %s (%d)" % (flag(c), esc(cname(c)), n))
    if genres:
        g, n = genres.most_common(1)[0]
        lines.append("Любимый жанр: %s (%d)" % (esc(g), n))
    lines.append("\nПо одному году: <code>/stats 2025</code>")
    return "\n".join(lines)


# ---------- обработка сообщений ----------
KNOWN = ["/start", "/search", "/stats", "/help"]


def handle(msg):
    chat = (msg.get("chat") or {}).get("id")
    text = (msg.get("text") or "").strip()
    if not chat or not text:
        return
    private = (msg.get("chat") or {}).get("type") == "private"

    if text.startswith("/"):
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
        arg = arg.strip()
        if cmd not in KNOWN:
            close = difflib.get_close_matches(cmd, KNOWN, n=1, cutoff=0.7)
            if close:
                cmd = close[0]  # опечатка вроде /seach
            else:
                if private:
                    send(chat, "Не знаю такой команды. Доступны: /search, /stats, /start, /help.")
                return
    elif private:
        cmd, arg = "/search", text  # обычное сообщение в личке = поиск
    else:
        return

    if cmd == "/start":
        send(chat, "📚 Карта нашего книжного клуба\n\n"
                   "Можно просто написать название, автора или жанр, и я найду книгу. "
                   "Команда /stats покажет итоги по годам.",
             markup_of([[app_button(True)]]) if private else None)
    elif cmd == "/search":
        do_search(chat, load() if tokens(arg) else [], arg, private)
    elif cmd == "/stats":
        send(chat, stats_text(load(), arg), markup_of([[app_button(private)]]))
    elif cmd == "/help":
        send(chat, "/search слово — найти книгу, автора или жанр\n"
                   "/stats — итоги по всем годам, <code>/stats 2025</code> — по году\n"
                   "/start — открыть карту")


def handle_callback(cb):
    msg = cb.get("message") or {}
    chat = (msg.get("chat") or {}).get("id")
    private = (msg.get("chat") or {}).get("type") == "private"
    try:
        api("answerCallbackQuery", {"callback_query_id": cb.get("id")})
    except Exception as e:
        print("answer failed:", e)
    data = cb.get("data") or ""
    if chat and data.startswith("b:"):
        i = int(data[2:])
        b = next((x for x in load() if x["i"] == i), None)
        if b:
            send_card(chat, b, private)


class handler(BaseHTTPRequestHandler):
    def _ok(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        self._ok()

    def do_POST(self):
        try:
            n = int(self.headers.get("content-length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            if body.get("callback_query"):
                handle_callback(body["callback_query"])
            else:
                handle(body.get("message") or {})
        except Exception as e:  # всегда отвечаем 200, иначе Telegram будет повторять запрос
            print("error:", e)
        self._ok()
