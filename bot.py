import re
import os
import json
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, ContextTypes, CallbackQueryHandler
)
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError, ChatAdminRequiredError
from telethon.tl.types import Channel, Chat
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4

# ==========================
# BOT SOZLAMLARI
# ==========================
TOKEN = os.getenv('TOKEN')
if not TOKEN:
    raise ValueError("TOKEN environment variable topilmadi! Render'da qo'shing.")

MAIN_ADMIN_ID = 8368965746
ADMIN_USERNAME = "MasulyatliOdam"
BOT_USERNAME = "AvtoXabarrBot"

# Papkalar
for folder in ['sessions', 'data', 'temp']:
    os.makedirs(folder, exist_ok=True)

# ==========================
# HOLATLAR
# ==========================
PHONE, API_ID, API_HASH, CODE, PASSWORD, MESSAGE, INTERVAL, DELETE_CONFIRM, AD_CHOICE = range(9)

# ==========================
# GLOBAL MA'LUMOTLAR
# ==========================
users = {}
user_stats = {}
admins = set()
subscription_price = 10000

# ==========================
# MA'LUMOT SAQLASH
# ==========================
def save_data():
    try:
        with open('data/users.json', 'w', encoding='utf-8') as f:
            save_users = {str(k): {kk: vv for kk, vv in v.items() if kk != 'client'} for k, v in users.items()}
            json.dump(save_users, f, ensure_ascii=False, indent=2)
        with open('data/user_stats.json', 'w', encoding='utf-8') as f:
            json.dump(user_stats, f, ensure_ascii=False, indent=2)
        with open('data/admins.json', 'w', encoding='utf-8') as f:
            json.dump(list(admins), f, ensure_ascii=False, indent=2)
        with open('data/subscription_price.json', 'w', encoding='utf-8') as f:
            json.dump(subscription_price, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[SAQLASH XATOSI] {e}")

def load_data():
    global users, user_stats, admins, subscription_price
    try:
        with open('data/users.json', 'r', encoding='utf-8') as f:
            loaded = json.load(f)
            users = {int(k): v for k, v in loaded.items()}
    except: users = {}
    try:
        with open('data/user_stats.json', 'r', encoding='utf-8') as f:
            user_stats = json.load(f)
    except: user_stats = {}
    try:
        with open('data/admins.json', 'r', encoding='utf-8') as f:
            admins = set(json.load(f))
    except: admins = {MAIN_ADMIN_ID}
    try:
        with open('data/subscription_price.json', 'r', encoding='utf-8') as f:
            subscription_price = json.load(f)
    except: subscription_price = 10000

# ==========================
# AKKAUNT TOZALASH
# ==========================
async def clear_user_account(user_id, context=None):
    if user_id in users:
        if users[user_id].get('client'):
            try:
                client = users[user_id]['client']
                if client.is_connected():
                    await client.disconnect()
            except: pass
        session_file = f"sessions/{users[user_id].get('phone', '').replace('+', '')}.session"
        if os.path.exists(session_file):
            try: os.remove(session_file)
            except: pass
        if context:
            for job in context.job_queue.get_jobs_by_name(f"repeat_send_{user_id}"):
                job.schedule_removal()
        users[user_id].update({
            'phone': None, 'api_id': None, 'api_hash': None, 'client': None,
            'message': None, 'last_message': None, 'current_interval': None, 'next_send_time': None
        })

# ==========================
# /start
# ==========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in users:
        users[user_id] = {
            'subscribed': False, 'phone': None, 'api_id': None, 'api_hash': None, 'client': None,
            'message': None, 'username': update.message.from_user.username,
            'full_name': update.message.from_user.full_name, 'subscription_end': None,
            'last_message': None, 'add_ad': True, 'current_interval': None,
            'next_send_time': None, 'registration_date': datetime.now().isoformat()
        }
        save_data()

    keyboard = [
        ['Xabar Yuborish', 'Mening Xabarlarim'],
        ['Obunalarim', 'Akkaunt Qo\'shish' if not users[user_id].get('phone') else 'Akkauntni O\'chirish'],
        ['Qo\'llanma']
    ]
    if user_id in admins:
        keyboard.append(['Admin Panel'])
    await update.message.reply_text(
        "AvtoXabar Botiga Xush Kelibsiz!\n\n"
        "• Guruhlarga avto xabar\n"
        "• 10,000 so'm/oy\n"
        "1. Obuna → 2. Akkaunt → 3. Xabar",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return ConversationHandler.END

# ==========================
# ASOSIY TUGMALAR
# ==========================
async def handle_main_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    if user_id not in users: return await start(update, context)

    if text == 'Obunalarim':
        if users[user_id].get('subscribed'):
            days = (datetime.fromisoformat(users[user_id]['subscription_end']) - datetime.now()).days
            txt = f"Faol: {days} kun qoldi\nNarx: {subscription_price} so'm"
        else:
            txt = f"Obuna: {subscription_price} so'm\nAdmin: @{ADMIN_USERNAME}"
        await update.message.reply_text(txt)
        return ConversationHandler.END

    elif text == 'Mening Xabarlarim':
        if not users[user_id].get('subscribed'):
            await update.message.reply_text("Obuna kerak!")
            return ConversationHandler.END
        stats = user_stats.get(str(user_id), {'total_groups': 0, 'total_messages': 0, 'last_sent': None})
        last = datetime.fromisoformat(stats['last_sent']).strftime("%H:%M") if stats['last_sent'] else "Yo'q"
        active = len(context.job_queue.get_jobs_by_name(f"repeat_send_{user_id}")) > 0
        txt = f"Guruh: {stats['total_groups']}\nYuborilgan: {stats['total_messages']}\nSo'ngi: {last}\n{'Aktiv' if active else 'To\'xtagan'}"
        kb = []
        if users[user_id].get('last_message'): kb.append([InlineKeyboardButton("Qayta yuborish", callback_data=f"resend_{user_id}")])
        if active: kb.append([InlineKeyboardButton("To'xtatish", callback_data=f"stop_{user_id}")])
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb) if kb else None)
        return ConversationHandler.END

    elif text == 'Akkaunt Qo\'shish':
        if not users[user_id].get('subscribed'): await update.message.reply_text("Obuna kerak!"); return ConversationHandler.END
        if users[user_id].get('phone'): await update.message.reply_text("Akkaunt bor!"); return ConversationHandler.END
        await update.message.reply_text("Telefon: +998901234567", reply_markup=ReplyKeyboardMarkup([['Bekor qilish']], resize_keyboard=True))
        return PHONE

    elif text == 'Akkauntni O\'chirish':
        if not users[user_id].get('phone'): await update.message.reply_text("Akkaunt yo'q!"); return ConversationHandler.END
        await update.message.reply_text("O'chirish?", reply_markup=ReplyKeyboardMarkup([['Ha', 'Yo\'q']], resize_keyboard=True))
        return DELETE_CONFIRM

    elif text == 'Xabar Yuborish':
        if not users[user_id].get('subscribed') or not users[user_id].get('client'):
            await update.message.reply_text("Obuna + Akkaunt kerak!")
            return ConversationHandler.END
        await update.message.reply_text("Xabar yozing:", reply_markup=ReplyKeyboardMarkup([['Bekor qilish']], resize_keyboard=True))
        return MESSAGE

    elif text == 'Admin Panel' and user_id in admins:
        return await admin_panel(update, context)

    elif text == 'Qo\'llanma':
        await update.message.reply_text(
            f"Qo'llanma\n"
            f"1. Obuna → @{ADMIN_USERNAME}\n"
            f"2. Akkaunt → +998...\n"
            f"3. Xabar → Interval\n"
            f"Interval: 5, 10, 30 min, 1 soat\n"
            f"Bot: @{BOT_USERNAME}"
        )
        return ConversationHandler.END

    return ConversationHandler.END

# ==========================
# CALLBACK
# ==========================
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith('resend_'):
        if not users[user_id].get('last_message'): await query.edit_message_text("Xabar yo'q!"); return
        msg = await query.message.reply_text("Yuborilmoqda...")
        sent, res = await send_message_to_groups(user_id, users[user_id]['last_message'])
        try: await msg.delete()
        except: pass
        await query.message.reply_text(res)

    elif data.startswith('stop_'):
        uid = int(data.split('_')[1])
        if uid != user_id: await query.edit_message_text("Bu sizniki emas!"); return
        for job in context.job_queue.get_jobs_by_name(f"repeat_send_{uid}"):
            job.schedule_removal()
        users[uid]['current_interval'] = None
        users[uid]['next_send_time'] = None
        save_data()
        await query.edit_message_text("To'xtatildi!")

# ==========================
# AKKAUNT QO'SHISH
# ==========================
async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    if text == 'Bekor qilish': await clear_user_account(user_id, context); return await start(update, context)
    if re.match(r'^\+\d{10,15}$', text):
        users[user_id]['phone'] = text
        await update.message.reply_text("API ID:", reply_markup=ReplyKeyboardMarkup([['Bekor qilish']], resize_keyboard=True))
        return API_ID
    await update.message.reply_text("Noto'g'ri! + bilan boshlang")
    return PHONE

async def handle_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    if text == 'Bekor qilish': await clear_user_account(user_id, context); return await start(update, context)
    if text.isdigit():
        users[user_id]['api_id'] = int(text)
        await update.message.reply_text("API HASH:", reply_markup=ReplyKeyboardMarkup([['Bekor qilish']], resize_keyboard=True))
        return API_HASH
    await update.message.reply_text("Raqam kiriting!")
    return API_ID

async def handle_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    if text == 'Bekor qilish': await clear_user_account(user_id, context); return await start(update, context)
    users[user_id]['api_hash'] = text
    client = TelegramClient(f"sessions/{text.replace('+', '')}", users[user_id]['api_id'], users[user_id]['api_hash'])
    users[user_id]['client'] = client
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.send_code_request(users[user_id]['phone'])
            await update.message.reply_text("Kod keldi! Kiriting:", reply_markup=ReplyKeyboardMarkup([['Bekor qilish']], resize_keyboard=True))
            return CODE
        await update.message.reply_text("Akkaunt qo'shildi!")
        save_data()
        return await start(update, context)
    except Exception as e:
        await update.message.reply_text(f"Xato: {e}")
        await clear_user_account(user_id, context)
        return ConversationHandler.END

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    if text == 'Bekor qilish': await clear_user_account(user_id, context); return await start(update, context)
    try:
        await users[user_id]['client'].sign_in(users[user_id]['phone'], text)
        await update.message.reply_text("Muvaffaqiyatli!")
        save_data()
        return await start(update, context)
    except SessionPasswordNeededError:
        await update.message.reply_text("Parol kiriting:", reply_markup=ReplyKeyboardMarkup([['Bekor qilish']], resize_keyboard=True))
        return PASSWORD
    except Exception as e:
        await update.message.reply_text(f"Kod xato: {e}")
        return CODE

async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    if text == 'Bekor qilish': await clear_user_account(user_id, context); return await start(update, context)
    try:
        await users[user_id]['client'].sign_in(password=text)
        await update.message.reply_text("Muvaffaqiyatli!")
        save_data()
        return await start(update, context)
    except Exception as e:
        await update.message.reply_text(f"Parol xato: {e}")
        return PASSWORD

# ==========================
# XABAR YUBORISH
# ==========================
async def send_message_to_groups(user_id, text):
    client = users[user_id].get('client')
    if not client: return 0, "Akkaunt yo'q"
    try:
        await client.connect()
        if not await client.is_user_authorized(): return 0, "Avtorizatsiya yo'q"
        sent = failed = 0
        ad = f"\n\n@{BOT_USERNAME}" if users[user_id].get('add_ad', True) else ""
        msg = text + ad
        async for dialog in client.iter_dialogs():
            if isinstance(dialog.entity, (Channel, Chat)):
                try:
                    await client.send_message(dialog.entity, msg)
                    sent += 1
                    await asyncio.sleep(2)
                except FloodWaitError as e: failed += 1; await asyncio.sleep(e.seconds)
                except: failed += 1
        await client.disconnect()
        return sent, f"Muvaffaqiyatli: {sent}\nXato: {failed}"
    except Exception as e:
        return 0, f"Xato: {e}"

async def handle_message_sending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    if text == 'Bekor qilish': return await start(update, context)
    users[user_id]['last_message'] = text
    await update.message.reply_text("Interval:", reply_markup=ReplyKeyboardMarkup([
        ['Har 5 daqiqa', 'Har 10 daqiqa'], ['Har 30 daqiqa', 'Har 1 soat'], ['Bekor qilish']
    ], resize_keyboard=True))
    return INTERVAL

async def handle_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    if text == 'Bekor qilish': return await start(update, context)
    intervals = {'Har 5 daqiqa': 300, 'Har 10 daqiqa': 600, 'Har 30 daqiqa': 1800, 'Har 1 soat': 3600}
    if text not in intervals: await update.message.reply_text("Noto'g'ri!"); return INTERVAL
    interval = intervals[text]
    users[user_id]['current_interval'] = text[4:]
    for job in context.job_queue.get_jobs_by_name(f"repeat_send_{user_id}"):
        job.schedule_removal()

    async def repeat_send(ctx):
        uid = ctx.job.data
        if uid not in users or not users[uid].get('last_message'): return
        sent, _ = await send_message_to_groups(uid, users[uid]['last_message'])
        if str(uid) not in user_stats: user_stats[str(uid)] = {'total_groups': 0, 'total_messages': 0, 'last_sent': None, 'daily_messages': {}}
        user_stats[str(uid)]['total_groups'] = sent
        user_stats[str(uid)]['total_messages'] += sent
        user_stats[str(uid)]['last_sent'] = datetime.now().isoformat()
        today = datetime.now().date().isoformat()
        user_stats[str(uid)]['daily_messages'][today] = user_stats[str(uid)]['daily_messages'].get(today, 0) + sent
        users[uid]['next_send_time'] = (datetime.now() + timedelta(seconds=interval)).isoformat()
        save_data()
        try: await ctx.bot.send_message(uid, f"Yuborildi: {sent} ta\nKeyingi: {text[4:]}")
        except: pass

    context.job_queue.run_repeating(repeat_send, interval, first=0, name=f"repeat_send_{user_id}", data=user_id)
    await update.message.reply_text(f"Har {text[4:]}da yuboriladi!")
    return await start(update, context)

# ==========================
# ADMIN PANEL
# ==========================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in admins: await update.message.reply_text("Admin emas!"); return ConversationHandler.END
    context.user_data['admin_action'] = None
    kb = [['Ruxsat Berish', 'Ruxsatni Olib Tashlash'], ['Statistika', 'Xabar Yuborish'], ['Asosiy Menyu']]
    if user_id == MAIN_ADMIN_ID:
        kb.insert(1, ['Admin Qo\'shish', 'Admin O\'chirish'])
        kb.insert(2, ['Obuna Narxi'])
    await update.message.reply_text("Admin Panel", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return "ADMIN_ACTIONS"

async def handle_admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    if text == 'Asosiy Menyu': return await start(update, context)
    if text in ['Ruxsat Berish', 'Ruxsatni Olib Tashlash', 'Admin Qo\'shish', 'Admin O\'chirish', 'Obuna Narxi', 'Xabar Yuborish']:
        context.user_data['admin_action'] = text
        if text == 'Xabar Yuborish':
            await update.message.reply_text("Xabar yozing:", reply_markup=ReplyKeyboardMarkup([['Orqaga']], resize_keyboard=True))
            return "ADMIN_INPUT"
        await update.message.reply_text(f"{text} uchun ID yoki @username:", reply_markup=ReplyKeyboardRemove())
        return "ADMIN_INPUT"
    if text == 'Statistika':
        # PDF
        doc = SimpleDocTemplate("temp/stats.pdf", pagesize=A4)
        elements = [Paragraph("Statistika", getSampleStyleSheet()['Title'])]
        data = [['ID', 'Ism', 'Obuna', 'Telefon']]
        for uid, u in users.items():
            obuna = "Yo'q"
            if u.get('subscribed'):
                days = (datetime.fromisoformat(u['subscription_end']) - datetime.now()).days
                obuna = f"{days} kun" if days > 0 else "Tugagan"
            data.append([str(uid)[:8], u.get('full_name', '')[:10], obuna, u.get('phone', '')[:12]])
        elements.append(Table(data))
        doc.build(elements)
        await update.message.reply_document(open("temp/stats.pdf", 'rb'), caption="Statistika")
        os.remove("temp/stats.pdf")
        return "ADMIN_ACTIONS"
    return "ADMIN_ACTIONS"

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    action = context.user_data['admin_action']
    if text == 'Orqaga': return await admin_panel(update, context)
    if action == 'Xabar Yuborish':
        sent = 0
        for uid in users:
            try:
                await context.bot.send_message(uid, text)
                sent += 1
                await asyncio.sleep(0.1)
            except: pass
        await update.message.reply_text(f"Yuborildi: {sent}")
        return await admin_panel(update, context)
    # Boshqa amallar...
    return "ADMIN_ACTIONS"

# ==========================
# MAIN — POLLING
# ==========================
def main():
    load_data()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_buttons)],
        states={
            PHONE: [MessageHandler(filters.TEXT, handle_phone)],
            API_ID: [MessageHandler(filters.TEXT, handle_api_id)],
            API_HASH: [MessageHandler(filters.TEXT, handle_api_hash)],
            CODE: [MessageHandler(filters.TEXT, handle_code)],
            PASSWORD: [MessageHandler(filters.TEXT, handle_password)],
            MESSAGE: [MessageHandler(filters.TEXT, handle_message_sending)],
            INTERVAL: [MessageHandler(filters.TEXT, handle_interval)],
            DELETE_CONFIRM: [MessageHandler(filters.TEXT, handle_delete_confirmation)],
        },
        fallbacks=[CommandHandler("start", start)]
    )
    app.add_handler(conv)

    admin_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Admin Panel$"), admin_panel)],
        states={"ADMIN_ACTIONS": [MessageHandler(filters.TEXT, handle_admin_actions)], "ADMIN_INPUT": [MessageHandler(filters.TEXT, handle_admin_input)]},
        fallbacks=[CommandHandler("start", start)]
    )
    app.add_handler(admin_conv)

    print("Bot POLLING rejimida ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
