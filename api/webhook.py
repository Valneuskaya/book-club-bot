import csv, datetime, difflib, html, io, json, os, re, urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler

TOKEN = os.environ.get("BOT_TOKEN", "")
APP_URL = os.environ.get("APP_URL", "")
MINIAPP_LINK = os.environ.get("MINIAPP_LINK", "")  # необязательно: t.me/бот/bookmap, для кнопки в группах
SHEET_BOOKS_CSV = os.environ.get("SHEET_BOOKS_CSV", "")  # опубликованная вкладка с книгами (CSV)
SHEET_NEXT_CSV = os.environ.get("SHEET_NEXT_CSV", "")    # опубликованная вкладка «Встреча» (CSV)
TZ_HOURS = int(os.environ.get("TZ_HOURS", "3"))  # часовой пояс клуба относительно UTC

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
    "ZA": "ЮАР", "EG": "Египет", "NG": "Нигерия", "KE": "Кения", "MA": "Марокко",
    "DZ": "Алжир", "TN": "Тунис", "ET": "Эфиопия", "IL": "Израиль", "IR": "Иран",
    "IQ": "Ирак", "SA": "Саудовская Аравия", "PK": "Пакистан", "BD": "Бангладеш",
    "TH": "Таиланд", "ID": "Индонезия", "PH": "Филиппины", "MY": "Малайзия",
    "SG": "Сингапур", "NZ": "Новая Зеландия", "CL": "Чили", "CO": "Колумбия",
    "PE": "Перу", "VE": "Венесуэла", "CU": "Куба", "UY": "Уругвай", "CH": "Швейцария",
    "BE": "Бельгия", "PT": "Португалия", "HU": "Венгрия", "RO": "Румыния",
    "BG": "Болгария", "RS": "Сербия", "HR": "Хорватия", "SI": "Словения",
    "LT": "Литва", "LV": "Латвия", "EE": "Эстония", "KZ": "Казахстан",
    "UZ": "Узбекистан", "AZ": "Азербайджан", "MD": "Молдова", "CY": "Кипр",
    "MT": "Мальта", "LU": "Люксембург", "TW": "Тайвань", "KP": "Северная Корея",
    "MN": "Монголия", "NP": "Непал", "LK": "Шри-Ланка", "GH": "Гана", "SN": "Сенегал",
    "AL": "Албания", "BA": "Босния и Герцеговина", "ME": "Черногория", "MK": "Северная Македония",
    "LB": "Ливан", "SY": "Сирия", "JO": "Иордания", "AF": "Афганистан",
}
NAME2CODE = {n.lower().replace("ё", "е"): c for c, n in COUNTRIES.items()}
NAME2CODE.update({"сша": "US", "америка": "US", "англия": "GB", "шотландия": "GB",
                  "уэльс": "GB", "британия": "GB", "корея": "KR", "республика корея": "KR",
                  "кыргызстан": "KG", "белоруссия": "BY"})


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
    body = re.search(r"const DATA=\{(.*?)\};\s*const (?:WARN|ALL)", page, re.S).group(1)
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


def fetch(url):
    with urllib.request.urlopen(url, timeout=8) as r:
        return r.read().decode("utf-8-sig")


def to_code(s):
    s = (s or "").strip()
    if not s:
        return ""
    k = s.lower().replace("ё", "е")
    if k in NAME2CODE:
        return NAME2CODE[k]
    if re.fullmatch(r"[A-Za-z]{2}", s):
        return s.upper()
    print("страна не распознана:", s)
    return ""


def parse_sheet(text):
    """Книги из опубликованной Google Таблицы (те же столбцы, что читает приложение)."""
    rows = list(csv.reader(io.StringIO(text)))
    books = []
    for r in rows[1:]:
        r = [x.strip() for x in r] + [""] * (12 - len(r))
        y, t, a, c, tags, gr, place, _sc, ot, fy, lg, cv = r[:12]
        if not t or not re.fullmatch(r"\d{4}", y):
            continue
        books.append({
            "i": len(books), "t": t if t.startswith("«") else "«%s»" % t, "a": a,
            "c": to_code(c), "tags": tags, "y": int(y),
            "g": [g.strip() for g in re.split(r"[;,]", gr) if g.strip()],
            "place": place, "ot": ot, "fy": fy, "lg": lg,
            "cv": cv if ("/" in cv or "." in cv or not cv) else "covers/%s.jpg" % cv,
        })
    return books


def load():
    if SHEET_BOOKS_CSV:
        try:
            books = parse_sheet(fetch(SHEET_BOOKS_CSV))
            if books:
                return books
        except Exception as e:
            print("таблица недоступна, берём страницу:", e)
    return parse(fetch(APP_URL))


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


# ---------- /next: дата ближайшей встречи (из вкладки «Встреча» в Таблице) ----------
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
NO_DATE = "Дата следующей встречи пока не назначена."


MONTH_PREFIX = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def parse_date(s):
    s = (s or "").strip()
    m = re.fullmatch(r"(\d{1,2})\s+([А-Яа-яЁё]+)\.?,?\s+(\d{4})(?:\s.*)?", s)  # «14 декабря 2026», «14 дек. 2026»
    if m:
        p = m.group(2).lower()[:3]
        p = "мая" if p == "май" else p
        if p in MONTH_PREFIX:
            try:
                return datetime.date(int(m.group(3)), MONTH_PREFIX.index(p) + 1, int(m.group(1)))
            except ValueError:
                return None
    first = s.split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d.%m.%y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(first, fmt).date()
        except ValueError:
            pass
    return None


def days_word(n):
    m, d = n % 100, n % 10
    if 10 < m < 15:
        return "дней"
    return "день" if d == 1 else "дня" if 1 < d < 5 else "дней"


def next_text(today=None):
    if not SHEET_NEXT_CSV:
        return "Вкладка «Встреча» не подключена: в Vercel нет переменной SHEET_NEXT_CSV."
    try:
        rows = list(csv.reader(io.StringIO(fetch(SHEET_NEXT_CSV))))
    except Exception as e:
        print("next failed:", e)
        return "Не получилось загрузить вкладку «Встреча». Проверь ссылку или попробуй чуть позже."
    today = today or (datetime.datetime.utcnow() + datetime.timedelta(hours=TZ_HOURS)).date()
    dates = []
    for row in rows[:10]:          # ищем даты в любых ячейках первых строк
        for cell in row:
            d = parse_date(cell)
            if d:
                dates.append(d)
    if not dates:
        return ("В таблице не нашлось ни одной даты. Напиши её в ячейку, например 2026-12-14. "
                "Первые ячейки, которые я увидела: " + esc(" | ".join(c for r in rows[:3] for c in r)[:150]))
    future = [d for d in dates if d >= today]
    if not future:
        return NO_DATE
    d = min(future)
    n = (d - today).days
    when = "сегодня!" if n == 0 else "завтра" if n == 1 else "через %d %s" % (n, days_word(n))
    return "📅 Следующая встреча: <b>%d %s %d, %s</b>\n%s" % (
        d.day, MONTHS[d.month - 1], d.year, WEEKDAYS[d.weekday()], when.capitalize())


# ---------- обработка сообщений ----------
KNOWN = ["/start", "/search", "/stats", "/next", "/help"]


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
                    send(chat, "Не знаю такой команды. Доступны: /search, /stats, /next, /start, /help.")
                return
    elif private:
        cmd, arg = "/search", text  # обычное сообщение в личке = поиск
    else:
        return

    if cmd == "/start":
        send(chat, "📚 Привет! Это бот нашего книжного клуба.\n\n"
                   "🌍 Открой карту кнопкой ниже: книги по странам и жанрам, поиск, итоги по годам.\n"
                   "🔎 Напиши название, автора или жанр, и я пришлю карточку книги.\n"
                   "📊 /stats — итоги по годам\n"
                   "📅 /next — дата следующей встречи",
             markup_of([[app_button(True)]]) if private else None)
    elif cmd == "/search":
        do_search(chat, load() if tokens(arg) else [], arg, private)
    elif cmd == "/stats":
        send(chat, stats_text(load(), arg), markup_of([[app_button(private)]]))
    elif cmd == "/next":
        send(chat, next_text())
    elif cmd == "/help":
        send(chat, "/search слово — найти книгу, автора или жанр\n"
                   "/next — дата следующей встречи\n"
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
