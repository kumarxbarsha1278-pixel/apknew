"""
⚔️ RAGEBITE DD BOT
Sirf owner commands
"""

import os
import sqlite3
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


DD_BOT_TOKEN = "8650600804:AAEjG0LscwdMjClRuMS8fI7nAmShqPyaato"
OWNER_ID = 6321758394
DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ragebite.db')


def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)


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


async def d_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🚫 Ye bot sirf owner ke liye hai.")
        return
    msg = ("⚔️ *RAGEBITE DD BOT* ⚔️\n\n"
           "👑 *Owner Commands:*\n"
           "`/addapikey <name> <key>`\n"
           "`/delapikey <name>` | `/listapikeys`\n"
           "`/addserver <name> <ip> <port>` | `/listservers`\n"
           "`/slots`")
    await update.message.reply_text(msg, parse_mode='Markdown')


async def d_slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    slots = get_all_slots()
    msg = "📊 *SLOTS*\n\n"
    for s in slots:
        if s[9] == 1:
            rem = (datetime.strptime(s[8], '%Y-%m-%d %H:%M:%S') - datetime.now()).seconds
            dev = (s[1][:12] + "..." if s[1] else "?")
            msg += f"🔴 Slot #{s[0]} — `{dev}` | {rem}s\n"
        else:
            msg += f"🟢 Slot #{s[0]}: FREE\n"
    msg += f"\n📋 Queue: {get_queue_count()}"
    await update.message.reply_text(msg, parse_mode='Markdown')


async def d_addapikey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or len(context.args) < 2:
        return
    add_api_key(context.args[0].lower(), context.args[1])
    await update.message.reply_text(f"✅ Added")


async def d_delapikey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or not context.args:
        return
    delete_api_key(context.args[0].lower())
    await update.message.reply_text(f"🗑️ Deleted")


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


def main():
    print("=" * 60)
    print("⚔️ RAGEBITE DD BOT")
    print("=" * 60)
    d_app = Application.builder().token(DD_BOT_TOKEN).build()
    d_app.add_handler(CommandHandler("start", d_start))
    d_app.add_handler(CommandHandler("slots", d_slots))
    d_app.add_handler(CommandHandler("addapikey", d_addapikey))
    d_app.add_handler(CommandHandler("delapikey", d_delapikey))
    d_app.add_handler(CommandHandler("listapikeys", d_listapikeys))
    d_app.add_handler(CommandHandler("addserver", d_addserver))
    d_app.add_handler(CommandHandler("listservers", d_listservers))
    print("⚔️ DD Bot running...")
    d_app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()