import re
import time
import os
import json
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes, CallbackQueryHandler
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError, ChatAdminRequiredError
from telethon.tl.types import Channel, Chat
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4

# Bot tokeni va Admin ID
TOKEN = os.getenv('TOKEN')
MAIN_ADMIN_ID = 8368965746
ADMIN_USERNAME = "MasulyatliOdam"
BOT_USERNAME = "AvtoXabarrBot"

# Papkalarni yaratish
if not os.path.exists('sessions'):
    os.makedirs('sessions')
if not os.path.exists('data'):
    os.makedirs('data')
if not os.path.exists('temp'):
    os.makedirs('temp')

# Suhbat holatlari
PHONE, API_ID, API_HASH, CODE, PASSWORD, MESSAGE, INTERVAL, DELETE_CONFIRM, AD_CHOICE, SUBSCRIPTION_PRICE = range(10)

# Ma'lumotlar
users = {}
user_stats = {}
user_jobs = {}  # Foydalanuvchilarning aktiv joblarini saqlash
admins = set()  # Adminlar ro'yxati
subscription_price = 10000  # Default obuna narxi

def save_data():
    with open('data/users.json', 'w', encoding='utf-8') as f:
        save_users = {}
        for user_id, user_data in users.items():
            save_users[str(user_id)] = {k: v for k, v in user_data.items() if k != 'client'}
        json.dump(save_users, f, ensure_ascii=False, indent=2)
    
    with open('data/user_stats.json', 'w', encoding='utf-8') as f:
        json.dump(user_stats, f, ensure_ascii=False, indent=2)
    
    with open('data/admins.json', 'w', encoding='utf-8') as f:
        json.dump(list(admins), f, ensure_ascii=False, indent=2)
    
    with open('data/subscription_price.json', 'w', encoding='utf-8') as f:
        json.dump(subscription_price, f, ensure_ascii=False, indent=2)

def load_data():
    global users, user_stats, admins, subscription_price
    try:
        with open('data/users.json', 'r', encoding='utf-8') as f:
            loaded_users = json.load(f)
            users = {int(k): v for k, v in loaded_users.items()}
    except (FileNotFoundError, json.JSONDecodeError):
        users = {}
    
    try:
        with open('data/user_stats.json', 'r', encoding='utf-8') as f:
            user_stats = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        user_stats = {}
    
    try:
        with open('data/admins.json', 'r', encoding='utf-8') as f:
            admins = set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        admins = {MAIN_ADMIN_ID}
    
    try:
        with open('data/subscription_price.json', 'r', encoding='utf-8') as f:
            subscription_price = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        subscription_price = 10000

async def clear_user_account(user_id, context=None):
    """Foydalanuvchi akkauntini to'liq tozalash"""
    if user_id in users:
        # Client disconnect qilish
        if users[user_id].get('client'):
            try:
                client = users[user_id]['client']
                if client.is_connected():
                    await client.disconnect()
                await client.__aexit__(None, None, None)
            except Exception as e:
                print(f"Client disconnect xatolik: {e}")
        
        # Session faylini o'chirish
        if users[user_id].get('phone'):
            session_file = f"sessions/{users[user_id]['phone'].replace('+', '')}.session"
            try:
                if os.path.exists(session_file):
                    for attempt in range(3):
                        try:
                            os.remove(session_file)
                            print(f"Session fayli o'chirildi: {session_file}")
                            break
                        except PermissionError:
                            if attempt < 2:
                                await asyncio.sleep(1)
                            else:
                                print(f"Session faylini o'chirib bo'lmadi: {session_file}")
            except Exception as e:
                print(f"Session faylini o'chirishda xatolik: {e}")
        
        # Takroriy yuborishni to'xtatish
        if context:
            job_name = f"repeat_send_{user_id}"
            current_jobs = context.job_queue.get_jobs_by_name(job_name)
            for job in current_jobs:
                job.schedule_removal()
        
        # Akkaunt ma'lumotlarini to'liq tozalash
        users[user_id].update({
            'phone': None, 
            'api_id': None, 
            'api_hash': None, 
            'client': None, 
            'message': None, 
            'sending': False,
            'last_message': None,
            'current_interval': None,
            'next_send_time': None
        })

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id not in users:
        users[user_id] = {
            'subscribed': False, 
            'phone': None, 
            'api_id': None, 
            'api_hash': None, 
            'client': None, 
            'message': None, 
            'sending': False,
            'username': update.message.from_user.username,
            'full_name': update.message.from_user.full_name,
            'subscription_end': None,
            'last_message': None,
            'add_ad': True,
            'current_interval': None,
            'next_send_time': None,
            'registration_date': datetime.now().isoformat()
        }
        save_data()
    
    # Asosiy menyu - doim bir xil tartibda
    keyboard = [
        ['📤 Xabar Yuborish', '📊 Mening Xabarlarim'],
        ['💰 Obunalarim', '➕ Akkaunt Qo\'shish' if not users[user_id].get('phone') else '🗑️ Akkauntni O\'chirish'],
        ['📚 Qo\'llanma']
    ]
    
    if user_id in admins:
        keyboard.append(['👨‍💼 Admin Panel'])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    welcome_text = """🎊 AvtoXabar Botiga Xush Kelibsiz! 🎊

🚀 Bot Imkoniyatlari:
• 📤 Guruhlarga avtomatik xabar yuborish
• 📊 Xabar yuborish statistikasi 
• 💰 Arzon narx - oyiga 10,000 so'm

🎯 Boshlash Uchun:
1️⃣ 💰 Obunalarim - Obuna sotib oling
2️⃣ ➕ Akkaunt Qo'shish - Telefon raqamingizni qo'shing  
3️⃣ 📤 Xabar Yuborish - Xabarlarni yuboring

⚡ Tez va Samarali Marketing!"""
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    return ConversationHandler.END

async def handle_main_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    
    if user_id not in users:
        await start(update, context)
        return ConversationHandler.END
    
    print(f"User {user_id} pressed: {text}")
    
    if text == '💰 Obunalarim':
        if users[user_id].get('subscribed'):
            end_date = datetime.fromisoformat(users[user_id]['subscription_end'])
            days_left = (end_date - datetime.now()).days
            if days_left > 0:
                subscription_text = f"""💎 Sizning Obunangiz

✅ Holat: 🟢 Faol
📅 Muddati: {days_left} kun qoldi
💳 Narxi: {subscription_price} so'm/oy

✨ Xabar yuborish funksiyasi faollashtirilgan"""
            else:
                users[user_id]['subscribed'] = False
                subscription_text = "❌ Obuna muddati tugagan!"
        else:
            subscription_text = f"""💳 Obuna Xizmati

📦 1 oylik obuna: {subscription_price} so'm
⏰ Muddat: 30 kun  
📈 Cheklovsiz xabar yuborish

👨‍💼 Admin bilan bog'lanish: @{ADMIN_USERNAME}

💬 To'lov qilish uchun admin bilan bog'laning."""
        
        await update.message.reply_text(subscription_text)
        return ConversationHandler.END
    
    elif text == '📊 Mening Xabarlarim':
        if not users[user_id].get('subscribed'):
            await update.message.reply_text(
                """❌ Sizda xabarlar mavjud emas!

📤 Yangi xabar yuborish uchun Xabar Yuborish bo'limiga o'ting.
💰 Avval obuna sotib olishingiz kerak!"""
            )
            return ConversationHandler.END
        
        stats = user_stats.get(str(user_id), {'total_groups': 0, 'total_messages': 0, 'last_sent': None})
        if stats['last_sent']:
            last_sent = datetime.fromisoformat(stats['last_sent']).strftime("%Y-%m-%d %H:%M:%S")
        else:
            last_sent = "Hali xabar yuborilmagan"
        
        # Keyingi xabar vaqtini hisoblash
        next_send_info = ""
        has_active_job = False
        
        # Job mavjudligini tekshirish
        job_name = f"repeat_send_{user_id}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        has_active_job = len(current_jobs) > 0
        
        if users[user_id].get('next_send_time'):
            next_time = datetime.fromisoformat(users[user_id]['next_send_time'])
            time_left = next_time - datetime.now()
            if time_left.total_seconds() > 0:
                minutes_left = int(time_left.total_seconds() // 60)
                seconds_left = int(time_left.total_seconds() % 60)
                interval = users[user_id].get('current_interval', 'Noma\'lum')
                next_send_info = f"⏳ Keyingi xabar: {minutes_left}min {seconds_left}sek\n🔄 Interval: {interval}"
            else:
                next_send_info = "⏳ Keyingi xabar: Tez orada"
        else:
            next_send_info = "⏳ Keyingi xabar: Rejalashtirilmagan"
        
        stats_text = f"""📊 Xabar Yuborish Statistikasi

📈 Guruhlar soni: {stats['total_groups']}
📤 Yuborilgan xabarlar: {stats['total_messages']}
⏰ So'ngi yuborilgan: {last_sent}

{next_send_info}
{'🟢 Aktiv xabar yuborish' if has_active_job else '🔴 Xabar yuborish to\'xtatilgan'}

🎯 Sizning marketing faolligingiz"""
        
        # Inline keyboard yaratish
        keyboard = []
        
        if users[user_id].get('last_message'):
            keyboard.append([InlineKeyboardButton("🔄 Oxirgi xabarni qayta yuborish", callback_data=f"resend_{user_id}")])
        
        # Agar aktiv job bo'lsa, to'xtatish tugmasini qo'shish
        if has_active_job:
            keyboard.append([InlineKeyboardButton("⏹️ Xabarni To'xtatish", callback_data=f"stop_{user_id}")])
        
        if keyboard:
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(stats_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(stats_text)
        
        return ConversationHandler.END
    
    elif text == '➕ Akkaunt Qo\'shish':
        if not users[user_id].get('subscribed'):
            await update.message.reply_text(
                f"""❌ Avval obuna sotib olishingiz kerak!

💰 Obunalarim bo'limi orqali obuna sotib oling."""
            )
            return ConversationHandler.END
            
        if users[user_id].get('phone'):
            await update.message.reply_text(
                """❌ Akkaunt allaqachon qo'shilgan!

🗑️ Agar boshqa akkaunt qo'shmoqchi bo'lsangiz, avval joriy akkauntni o'chiring."""
            )
            return ConversationHandler.END
        else:
            keyboard = [['🔙 Bekor qilish']]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text(
                """📱 Telefon Raqamingizni Kiriting:

📞 Format: +XXXXXXXXXXX
💡 Eslatma: Telefon raqamingiz Telegram hisobingizga bog'liq bo'lishi kerak.

🌍 Har qanday davlat nomerini + bilan boshlab yozishingiz mumkin""",
                reply_markup=reply_markup
            )
            return PHONE
    
    elif text == '🗑️ Akkauntni O\'chirish':
        if not users[user_id].get('phone'):
            await update.message.reply_text(
                """❌ Sizda akkaunt mavjud emas!

➕ Avval akkaunt qo'shing."""
            )
            return ConversationHandler.END
        
        keyboard = [
            ['✅ Ha, akkauntni o\'chirish', '❌ Yo\'q, bekor qilish']
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            """⚠️ Akkauntni O'chirish

Haqiqatan ham akkauntingizni o'chirmoqchimisiz?

Bu amalni ortga qaytarib bo'lmaydi!""",
            reply_markup=reply_markup
        )
        return DELETE_CONFIRM
    
    elif text == '📤 Xabar Yuborish':
        if not users[user_id].get('subscribed'):
            await update.message.reply_text(
                f"""❌ Xabar yuborish uchun obuna kerak!

💰 Obuna sotib olish uchun Obunalarim tugmasini bosing."""
            )
            return ConversationHandler.END
        
        if not users[user_id].get('phone') or users[user_id].get('client') is None:
            await update.message.reply_text(
                """❌ Avval akkaunt qo'shishingiz kerak!

➕ Akkaunt Qo'shish tugmasini bosing."""
            )
            return ConversationHandler.END
        
        keyboard = [['🔙 Bekor qilish']]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            """💬 Xabarni Kiriting:

📝 Guruhlarga yuboriladigan xabaringizni yozing:""",
            reply_markup=reply_markup
        )
        return MESSAGE

    elif text == '👨‍💼 Admin Panel':
        if user_id in admins:
            await admin_panel(update, context)
        else:
            await update.message.reply_text("❌ Siz admin emassiz!")
        return ConversationHandler.END

    elif text == '📚 Qo\'llanma':
        await show_manual(update, context)
        return ConversationHandler.END

    return ConversationHandler.END

async def show_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    manual_text = """📚 Bot Qo'llanmasi

🎯 Bot Nima Qiladi?
└─ 📤 Guruhlarga avtomatik xabar yuborish

🛠️ Qanday Ishlatiladi?
├─ 1️⃣ Obuna sotib olish
├─ 2️⃣ Akkaunt qo'shish
├─ 3️⃣ Xabar yuborish
└─ 4️⃣ Statistikani ko'rish

⏰ Xabar Yuborish Intervali
├─ ⏱️ Har 5 daqiqa
├─ ⏱️ Har 10 daqiqa  
├─ ⏱️ Har 30 daqiqa
└─ ⏱️ Har 1 soat

💡 Maslahatlar
├─ ✅ Xabarlar qisqa va tushunarli bo'lsin
├─ ✅ Reklama qo'shish tavsiya etiladi
├─ ✅ Flooddan saqlaning
└─ ✅ Har 2 sekundda 1 xabar

👨‍💼 Admin:
└─ @MasulyatliOdam

🤖 Bot:
└─ @AvtoXabarrBot

🔧 Qo'llab-quvvatlash:
└─ Muammo bo'lsa admin bilan bog'laning"""
    
    await update.message.reply_text(manual_text)

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    if callback_data.startswith('resend_'):
        if not users[user_id].get('last_message'):
            await query.edit_message_text(
                """❌ Qayta yuborish uchun xabar topilmadi!

📤 Avval yangi xabar yuboring."""
            )
            return
        
        message_text = users[user_id]['last_message']
        
        progress_msg = await query.message.reply_text(
            """🔄 Xabar qayta yuborilmoqda...

⏳ Jarayon 1-2 daqiqa davom etadi..."""
        )
        
        sent_count, result_text = await send_message_to_groups(user_id, message_text)
        
        try:
            await progress_msg.delete()
        except:
            pass
        
        if str(user_id) not in user_stats:
            user_stats[str(user_id)] = {'total_groups': 0, 'total_messages': 0, 'last_sent': None, 'daily_messages': {}}
        
        user_stats[str(user_id)]['total_groups'] = sent_count
        user_stats[str(user_id)]['total_messages'] += sent_count
        user_stats[str(user_id)]['last_sent'] = datetime.now().isoformat()
        
        today = datetime.now().date().isoformat()
        if 'daily_messages' not in user_stats[str(user_id)]:
            user_stats[str(user_id)]['daily_messages'] = {}
        user_stats[str(user_id)]['daily_messages'][today] = user_stats[str(user_id)]['daily_messages'].get(today, 0) + sent_count
        
        save_data()
        
        if len(result_text) > 4000:
            result_text = result_text[:4000] + "\n\n... (qolgan qismi qisqartirildi)"
        
        await query.message.reply_text(result_text)
    
    elif callback_data.startswith('stop_'):
        # Xabar yuborishni to'xtatish
        target_user_id = int(callback_data.split('_')[1])
        
        # Faqat o'zining xabarini to'xtatishi mumkin
        if user_id != target_user_id:
            await query.edit_message_text("❌ Siz boshqa foydalanuvchining xabarini to'xtata olmaysiz!")
            return
        
        # Joblarni to'xtatish
        job_name = f"repeat_send_{target_user_id}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        
        if not current_jobs:
            await query.edit_message_text(
                """❌ Aktiv xabar yuborish topilmadi!

📊 Xabar yuborish allaqachon to'xtatilgan."""
            )
            return
        
        # Barcha joblarni o'chirish
        for job in current_jobs:
            job.schedule_removal()
        
        # Foydalanuvchi ma'lumotlarini yangilash
        users[target_user_id]['current_interval'] = None
        users[target_user_id]['next_send_time'] = None
        save_data()
        
        # Xabarni yangilash
        stats = user_stats.get(str(target_user_id), {'total_groups': 0, 'total_messages': 0, 'last_sent': None})
        if stats['last_sent']:
            last_sent = datetime.fromisoformat(stats['last_sent']).strftime("%Y-%m-%d %H:%M:%S")
        else:
            last_sent = "Hali xabar yuborilmagan"
        
        updated_text = f"""📊 Xabar Yuborish Statistikasi

📈 Guruhlar soni: {stats['total_groups']}
📤 Yuborilgan xabarlar: {stats['total_messages']}
⏰ So'ngi yuborilgan: {last_sent}

⏳ Keyingi xabar: Rejalashtirilmagan
🔴 Xabar yuborish to'xtatilgan

✅ Xabar yuborish muvaffaqiyatli to'xtatildi!

📤 Yangi xabar yuborish uchun Xabar Yuborish bo'limiga o'ting."""

        # Yangilangan xabarni yuborish
        keyboard = []
        if users[target_user_id].get('last_message'):
            keyboard.append([InlineKeyboardButton("🔄 Oxirgi xabarni qayta yuborish", callback_data=f"resend_{target_user_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        try:
            await query.edit_message_text(updated_text, reply_markup=reply_markup)
        except Exception as e:
            # Agar xabarni yangilab bo'lmasa, yangi xabar yuborish
            await query.message.reply_text(updated_text, reply_markup=reply_markup)

async def handle_delete_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    
    if text == '✅ Ha, akkauntni o\'chirish':
        await clear_user_account(user_id, context)
        
        await update.message.reply_text(
            """✅ Akkaunt muvaffaqiyatli o'chirildi!

➕ Yangi akkaunt qo'shishingiz mumkin."""
        )
        save_data()
        await start(update, context)
    
    elif text == '❌ Yo\'q, bekor qilish':
        await update.message.reply_text(
            "❌ Akkaunt o'chirish bekor qilindi!"
        )
        await start(update, context)
    
    return ConversationHandler.END

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    
    if text == '🔙 Bekor qilish':
        # Avvalgi ma'lumotlarni tozalash
        if users[user_id].get('phone'):
            await clear_user_account(user_id, context)
        await update.message.reply_text("❌ Akkaunt qo'shish bekor qilindi!")
        await start(update, context)
        return ConversationHandler.END
    
    # Agar avval akkaunt mavjud bo'lsa, tozalash
    if users[user_id].get('phone'):
        await clear_user_account(user_id, context)
    
    if re.match(r'^\+\d{10,15}$', text):
        users[user_id]['phone'] = text
        keyboard = [['🔙 Bekor qilish']]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            """🔐 API ID ni Kiriting:

🌐 Manzil: https://my.telegram.org
📋 API ID raqamini yuboring:""",
            reply_markup=reply_markup
        )
        return API_ID
    else:
        await update.message.reply_text(
            """❌ Noto'g'ri format!

📞 Iltimos, +XXXXXXXXXXX shaklida yuboring.
Misol: +998901234567 yoki +441234567890"""
        )
        return PHONE

async def handle_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    
    if text == '🔙 Bekor qilish':
        # Akkaunt ma'lumotlarini to'liq tozalash
        if users[user_id].get('phone'):
            await clear_user_account(user_id, context)
        await update.message.reply_text("❌ Akkaunt qo'shish bekor qilindi!")
        await start(update, context)
        return ConversationHandler.END
    
    if text.isdigit():
        users[user_id]['api_id'] = int(text)
        keyboard = [['🔙 Bekor qilish']]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            """🔑 API HASH ni Kiriting:

🌐 Manzil: https://my.telegram.org
🔑 API HASH ni yuboring:""",
            reply_markup=reply_markup
        )
        return API_HASH
    else:
        await update.message.reply_text(
            """❌ API ID raqam bo'lishi kerak!

🔢 Faqat raqamlardan iborat bo'lsin."""
        )
        return API_ID

async def handle_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    
    if text == '🔙 Bekor qilish':
        # Akkaunt ma'lumotlarini to'liq tozalash
        if users[user_id].get('phone'):
            await clear_user_account(user_id, context)
        await update.message.reply_text("❌ Akkaunt qo'shish bekor qilindi!")
        await start(update, context)
        return ConversationHandler.END
    
    users[user_id]['api_hash'] = text
    
    session_name = f"sessions/{users[user_id]['phone'].replace('+', '')}"
    
    try:
        # Avvalgi clientni tozalash
        if users[user_id].get('client'):
            try:
                old_client = users[user_id]['client']
                if old_client.is_connected():
                    await old_client.disconnect()
                await old_client.__aexit__(None, None, None)
            except Exception as e:
                print(f"Old client cleanup error: {e}")
        
        client = TelegramClient(session_name, users[user_id]['api_id'], users[user_id]['api_hash'])
        users[user_id]['client'] = client
        
        await client.connect()
        if not await client.is_user_authorized():
            await client.send_code_request(users[user_id]['phone'])
            keyboard = [['🔙 Bekor qilish']]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text(
                """📲 Kod Yuborildi!

✅ Kod Telegram ilovasiga yuborildi (SMS emas)!
📱 Telegram chatini oching va kodni yuboring:""",
                reply_markup=reply_markup
            )
            return CODE
        else:
            await update.message.reply_text("✅ Akkaunt muvaffaqiyatli qo'shilgan!")
            save_data()
            await start(update, context)
            return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(
            f"❌ Xatolik: {str(e)}\n\n"
            "🔧 API ma'lumotlari yoki ulanishni tekshiring.\n"
            "🔄 Jarayonni qayta boshlang."
        )
        # Xatolik yuz bersa ma'lumotlarni tozalash
        await clear_user_account(user_id, context)
        return ConversationHandler.END

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    
    if text == '🔙 Bekor qilish':
        # Akkaunt ma'lumotlarini to'liq tozalash
        if users[user_id].get('phone'):
            await clear_user_account(user_id, context)
        await update.message.reply_text("❌ Akkaunt qo'shish bekor qilindi!")
        await start(update, context)
        return ConversationHandler.END
    
    try:
        await users[user_id]['client'].sign_in(users[user_id]['phone'], text)
        await update.message.reply_text("✅ Akkaunt muvaffaqiyatli qo'shilgan!")
    except SessionPasswordNeededError:
        keyboard = [['🔙 Bekor qilish']]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            """🔒 Ikki faktorli parol kerak!

📝 Iltimos, ikki faktorli autentifikatsiya parolini yuboring:""",
            reply_markup=reply_markup
        )
        return PASSWORD
    except Exception as e:
        await update.message.reply_text(
            f"❌ Xatolik: {str(e)}\n\n"
            "⚠️ Kod xato bo'lishi mumkin, Telegram chatini qayta tekshiring."
        )
        return ConversationHandler.END
    
    save_data()
    await start(update, context)
    return ConversationHandler.END

async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    
    if text == '🔙 Bekor qilish':
        # Akkaunt ma'lumotlarini to'liq tozalash
        if users[user_id].get('phone'):
            await clear_user_account(user_id, context)
        await update.message.reply_text("❌ Akkaunt qo'shish bekor qilindi!")
        await start(update, context)
        return ConversationHandler.END
    
    try:
        await users[user_id]['client'].sign_in(password=text)
        await update.message.reply_text("✅ Akkaunt muvaffaqiyatli qo'shilgan!")
    except Exception as e:
        await update.message.reply_text(
            f"❌ Xatolik: {str(e)}\n\n"
            "⚠️ Parol xato bo'lishi mumkin."
        )
        return ConversationHandler.END
    
    save_data()
    await start(update, context)
    return ConversationHandler.END

async def send_message_to_groups(user_id, message_text):
    user_data = users[user_id]
    
    if user_data.get('client') is None:
        return 0, "❌ Akkaunt topilmadi"
    
    try:
        client = user_data['client']
        await client.connect()
        
        if not await client.is_user_authorized():
            return 0, "❌ Akkaunt avtorizatsiyadan o'tmagan"
        
        groups_sent = 0
        failed_groups = 0
        group_list = []
        
        advertisement = ""
        if user_data.get('add_ad', True):
            advertisement = f"\n\n🤖 @{BOT_USERNAME} - Guruhlarga avtomatik xabar yuborish"
        full_message = message_text + advertisement
        
        async for dialog in client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                try:
                    await client.send_message(dialog.id, full_message)
                    groups_sent += 1
                    group_list.append(f"✅ {dialog.name}")
                    await asyncio.sleep(2)
                except FloodWaitError as e:
                    failed_groups += 1
                    group_list.append(f"❌ {dialog.name} - Flood kutish: {e.seconds}s")
                    await asyncio.sleep(e.seconds)
                except ChatAdminRequiredError:
                    failed_groups += 1
                    group_list.append(f"❌ {dialog.name} - Guruh admini huquqi kerak")
                except Exception as e:
                    failed_groups += 1
                    error_msg = str(e)
                    if "Chat admin privileges are required" in error_msg:
                        error_msg = "Guruh admini huquqi kerak"
                    elif "Forbidden" in error_msg:
                        error_msg = "Guruhga kirish taqiqlangan"
                    elif "Timeout" in error_msg:
                        error_msg = "Vaqt tugadi"
                    elif "PEER_ID_INVALID" in error_msg:
                        error_msg = "Guruh topilmadi"
                    group_list.append(f"❌ {dialog.name} - {error_msg[:50]}")
                    continue
        
        await client.disconnect()
        
        result_text = f"📊 Xabar Yuborish Natijasi:\n\n"
        result_text += f"✅ Muvaffaqiyatli: {groups_sent}\n"
        result_text += f"❌ Xatolik: {failed_groups}\n\n"
        
        if group_list:
            result_text += "Guruhlar:\n" + "\n".join(group_list[:8])
        
        return groups_sent, result_text
        
    except Exception as e:
        return 0, f"❌ Xatolik: {str(e)}"

async def handle_message_sending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    
    if text == '🔙 Bekor qilish':
        await update.message.reply_text("❌ Xabar yuborish bekor qilindi!")
        await start(update, context)
        return ConversationHandler.END
    
    if user_id not in users or users[user_id].get('client') is None:
        await update.message.reply_text(
            """❌ Akkaunt to'g'ri qo'shilgan emas!

➕ Akkaunt Qo'shish ni qayta bajaring."""
        )
        return ConversationHandler.END
    
    message_text = text
    users[user_id]['message'] = message_text
    users[user_id]['last_message'] = message_text
    
    keyboard = [
        ['⏱️ Har 5 daqiqa', '⏱️ Har 10 daqiqa'],
        ['⏱️ Har 30 daqiqa', '⏱️ Har 1 soat'],
        ['🔙 Bekor qilish']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "⏰ Xabarni qancha vaqtda takrorlab yuborishni tanlang:",
        reply_markup=reply_markup
    )
    return INTERVAL

async def handle_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    
    if text == '🔙 Bekor qilish':
        await update.message.reply_text("❌ Xabar yuborish bekor qilindi!")
        await start(update, context)
        return ConversationHandler.END
    
    message_text = users[user_id]['message']
    
    if text == '⏱️ Har 5 daqiqa':
        interval = 300  # 5 daqiqa
        interval_text = "5 daqiqa"
    elif text == '⏱️ Har 10 daqiqa':
        interval = 600  # 10 daqiqa
        interval_text = "10 daqiqa"
    elif text == '⏱️ Har 30 daqiqa':
        interval = 1800  # 30 daqiqa
        interval_text = "30 daqiqa"
    elif text == '⏱️ Har 1 soat':
        interval = 3600  # 1 soat
        interval_text = "1 soat"
    else:
        await update.message.reply_text("❌ Noto'g'ri tanlov!")
        return INTERVAL
    
    notification_text = "✅ Xabaringiz guruhlarga yuborildi!"
    
    # Foydalanuvchi ma'lumotlarini yangilash
    users[user_id]['current_interval'] = interval_text
    users[user_id]['next_send_time'] = datetime.now().isoformat()
    
    save_data()
    
    # Takroriy yuborishni sozlash
    job_name = f"repeat_send_{user_id}"
    
    # Avvalgi jobni o'chirish
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
        print(f"Eski job o'chirildi: {job_name}")
    
    # Yangi job yaratish
    async def repeat_send(context: ContextTypes.DEFAULT_TYPE):
        user_id = context.job.data
        print(f"Takroriy yuborish: {user_id} - {datetime.now()}")
        
        if user_id not in users or not users[user_id].get('last_message'):
            print(f"Xabar topilmadi: {user_id}")
            return
            
        message_text = users[user_id]['last_message']
        
        print(f"Xabar yuborilmoqda: {message_text[:50]}...")
        sent_count, result_text = await send_message_to_groups(user_id, message_text)
        print(f"Yuborildi: {sent_count} guruhga")
        
        # Statistika yangilash
        if str(user_id) not in user_stats:
            user_stats[str(user_id)] = {'total_groups': 0, 'total_messages': 0, 'last_sent': None, 'daily_messages': {}}
        
        user_stats[str(user_id)]['total_groups'] = sent_count
        user_stats[str(user_id)]['total_messages'] += sent_count
        user_stats[str(user_id)]['last_sent'] = datetime.now().isoformat()
        
        today = datetime.now().date().isoformat()
        if 'daily_messages' not in user_stats[str(user_id)]:
            user_stats[str(user_id)]['daily_messages'] = {}
        user_stats[str(user_id)]['daily_messages'][today] = user_stats[str(user_id)]['daily_messages'].get(today, 0) + sent_count
        
        # Keyingi xabar vaqtini yangilash
        users[user_id]['next_send_time'] = (datetime.now() + timedelta(seconds=interval)).isoformat()
        save_data()
        
        # Foydalanuvchini OGOHLANTIRISH
        report_text = f"""{notification_text}

📊 Statistika:
├─ ✅ Yuborildi: {sent_count} guruhga
├─ ⏰ Vaqt: {datetime.now().strftime('%H:%M:%S')}
└─ 📅 Sana: {datetime.now().strftime('%Y-%m-%d')}

🎯 Keyingi xabar {interval_text}dan so'ng yuboriladi"""
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=report_text
            )
            print(f"Ogohlantirish yuborildi: {user_id}")
        except Exception as e:
            print(f"Ogohlantirish yuborishda xatolik: {e}")
    
    # Jobni ishga tushirish
    context.job_queue.run_repeating(
        repeat_send,
        interval=interval,
        first=0,  # Birinchi takrorlash darhol
        name=job_name,
        data=user_id
    )
    
    print(f"Yangi job yaratildi: {job_name}, interval: {interval}s")
    
    await update.message.reply_text(
        f"""✅ Xabar takrorlanib yuboriladi!

⏰ Interval: {interval_text}
📝 Har {interval_text}da 1 ta xabar yuboriladi
🔔 Har safar ogohlantirish olasiz:
   "✅ Xabaringiz guruhlarga yuborildi!"

⏳ Birinchi yuborish: Tez orada
⏳ Keyingi yuborishlar: har {interval_text}da

🏠 Asosiy menyuga qaytildi."""
    )
    
    # Asosiy menyuga qaytish
    await start(update, context)
    return ConversationHandler.END

# ADMIN PANEL
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in admins:
        await update.message.reply_text("❌ Siz admin emassiz!")
        return
    
    # Admin holatini tozalash
    context.user_data['admin_action'] = None
    context.user_data['target_user_input'] = None
    
    # Asosiy admin va boshqa adminlar uchun turli tugmalar
    if user_id == MAIN_ADMIN_ID:
        # Asosiy admin uchun barcha tugmalar
        keyboard = [
            ['✅ Ruxsat Berish', '❌ Ruxsatni Olib Tashlash'],
            ['➕ Admin Qo\'shish', '➖ Admin O\'chirish'],
            ['💰 Obuna Narxi', '📊 Statistika'],
            ['📢 Xabar Yuborish', '🏠 Asosiy Menyu']
        ]
    else:
        # Boshqa adminlar uchun cheklangan tugmalar
        keyboard = [
            ['✅ Ruxsat Berish', '❌ Ruxsatni Olib Tashlash'],
            ['📊 Statistika', '📢 Xabar Yuborish'],
            ['🏠 Asosiy Menyu']
        ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    admin_text = """👑 Admin Paneliga Xush Kelibsiz

⚡ Quyidagi Imkoniyatlar Mavjud:
• ✅ Ruxsat berish
• ❌ Ruxsatni olib tashlash  
• 📊 Statistika ko'rish
• 📢 Barchaga xabar yuborish"""

    # Asosiy admin uchun qo'shimcha imkoniyatlarni ko'rsatish
    if user_id == MAIN_ADMIN_ID:
        admin_text += "\n• ➕ Admin Qo'shish\n• ➖ Admin O'chirish\n• 💰 Obuna narxini o'zgartirish"

    admin_text += "\n\n🎯 Botni Boshqarish"
    
    await update.message.reply_text(admin_text, reply_markup=reply_markup)
    return "ADMIN_ACTIONS"

async def handle_admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in admins:
        return
    
    text = update.message.text
    
    if text == '✅ Ruxsat Berish':
        await update.message.reply_text(
            """👤 Ruxsat Berish

Foydalanuvchi ID sini yoki username ni kiriting:
Misol: 123456789 yoki @username""",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['admin_action'] = 'grant_access'
        return "ADMIN_INPUT"
    
    elif text == '❌ Ruxsatni Olib Tashlash':
        await update.message.reply_text(
            """👤 Ruxsatni Olib Tashlash

Foydalanuvchi ID sini yoki username ni kiriting:
Misol: 123456789 yoki @username""",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['admin_action'] = 'remove_access'
        return "ADMIN_INPUT"
    
    elif text == '➕ Admin Qo\'shish':
        if user_id != MAIN_ADMIN_ID:
            await update.message.reply_text("❌ Sizda admin qo'shish huquqi yo'q!")
            await admin_panel(update, context)
            return "ADMIN_ACTIONS"
            
        await update.message.reply_text(
            """👤 Yangi Admin Qo'shish

Foydalanuvchi ID sini yoki username ni kiriting:
Misol: 123456789 yoki @username""",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['admin_action'] = 'add_admin'
        return "ADMIN_INPUT"
    
    elif text == '➖ Admin O\'chirish':
        if user_id != MAIN_ADMIN_ID:
            await update.message.reply_text("❌ Sizda admin o'chirish huquqi yo'q!")
            await admin_panel(update, context)
            return "ADMIN_ACTIONS"
            
        await update.message.reply_text(
            """👤 Adminni O'chirish

Foydalanuvchi ID sini yoki username ni kiriting:
Misol: 123456789 yoki @username""",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['admin_action'] = 'remove_admin'
        return "ADMIN_INPUT"
    
    elif text == '💰 Obuna Narxi':
        if user_id != MAIN_ADMIN_ID:
            await update.message.reply_text("❌ Sizda obuna narxini o'zgartirish huquqi yo'q!")
            await admin_panel(update, context)
            return "ADMIN_ACTIONS"
            
        await update.message.reply_text(
            f"""💳 Joriy Obuna Narxi: {subscription_price} so'm

Yangi obuna narxini kiriting (so'mda):""",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['admin_action'] = 'set_price'
        return "ADMIN_INPUT"
    
    elif text == '📊 Statistika':
        pdf_filename = 'users_stats.pdf'
        doc = SimpleDocTemplate(pdf_filename, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []
        
        # Sarlavha
        title_style = styles['Title']
        title_style.fontSize = 14
        elements.append(Paragraph("Foydalanuvchilar Statistikasi", title_style))
        elements.append(Spacer(1, 10))

        # Jami statistika
        total_users = len(users)
        subscribed_users = sum(1 for user_data in users.values() if user_data.get('subscribed') and (datetime.fromisoformat(user_data['subscription_end']) - datetime.now()).days > 0)
        total_messages = sum(stats.get('total_messages', 0) for stats in user_stats.values())
        
        today = datetime.now().date().isoformat()
        today_total = sum(stats.get('daily_messages', {}).get(today, 0) for stats in user_stats.values())
        
        normal_style = styles['Normal']
        normal_style.fontSize = 10
        
        elements.append(Paragraph(f"Jami foydalanuvchilar: {total_users}", normal_style))
        elements.append(Paragraph(f"Obuna bo'lganlar: {subscribed_users}", normal_style))
        elements.append(Paragraph(f"Bugun yuborilgan xabarlar: {today_total}", normal_style))
        elements.append(Paragraph(f"Jami yuborilgan xabarlar: {total_messages}", normal_style))
        elements.append(Paragraph(f"Obuna narxi: {subscription_price} so'm", normal_style))
        elements.append(Spacer(1, 10))
        
        # Jadval uchun ma'lumotlar
        data = [['ID', 'Ism', 'Username', 'Telefon', 'Obuna', 'Ro\'yxatdan o\'tgan']]
        
        for uid, user_data in users.items():
            obuna = "❌ Yo'q"
            if user_data.get('subscribed'):
                end_date = datetime.fromisoformat(user_data['subscription_end'])
                days_left = (end_date - datetime.now()).days
                if days_left > 0:
                    obuna = f"✅ Faol ({days_left} kun)"
                else:
                    obuna = "❌ Tugagan"
            
            name = user_data.get('full_name', 'Noma\'lum')[:15]
            username = f"@{user_data.get('username', 'yo\'q')}" if user_data.get('username') else 'yo\'q'
            
            # Telefon raqamini xavfsiz ko'rsatish
            phone = user_data.get('phone', 'yo\'q')
            if phone and phone != 'yo\'q':
                phone = phone[:12]
            
            reg_date = datetime.fromisoformat(user_data.get('registration_date', datetime.now().isoformat())).strftime("%d.%m.%Y")
            
            data.append([str(uid)[:8], name, username, phone, obuna, reg_date])
        
        # Jadvalni yaratish
        table = Table(data, colWidths=[60, 80, 80, 80, 80, 60])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        
        elements.append(table)
        
        try:
            doc.build(elements)
            await update.message.reply_document(
                document=open(pdf_filename, 'rb'), 
                filename='users_stats.pdf',
                caption="📊 Foydalanuvchilar statistikasi"
            )
        except Exception as e:
            error_text = f"❌ Statistika PDF yaratishda xatolik: {str(e)}"
            await update.message.reply_text(error_text)
        finally:
            if os.path.exists(pdf_filename):
                try:
                    os.remove(pdf_filename)
                except:
                    pass
        
        return "ADMIN_ACTIONS"
    
    elif text == '📢 Xabar Yuborish':
        keyboard = [['🔙 Orqaga']]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            """📢 Barcha Foydalanuvchilarga Xabar Yuborish

Yuboriladigan xabarni kiriting:""",
            reply_markup=reply_markup
        )
        context.user_data['admin_action'] = 'broadcast'
        return "ADMIN_INPUT"
    
    elif text == '🏠 Asosiy Menyu':
        await start(update, context)
        return ConversationHandler.END
    
    return "ADMIN_ACTIONS"

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in admins:
        return ConversationHandler.END
    
    text = update.message.text.strip()
    admin_action = context.user_data.get('admin_action')
    
    if text == '🔙 Orqaga':
        context.user_data['admin_action'] = None
        await admin_panel(update, context)
        return "ADMIN_ACTIONS"
    
    if admin_action == 'grant_access':
        context.user_data['target_user_input'] = text
        keyboard = [['Reklama bilan', 'Reklamasiz'], ['🔙 Orqaga']]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "📢 Reklama qo'shishni tanlang:",
            reply_markup=reply_markup
        )
        return AD_CHOICE
    
    elif admin_action == 'remove_access':
        target_user_id = None
        target_username = None
        
        if text.isdigit():
            target_user_id = int(text)
        elif text.startswith('@'):
            target_username = text[1:].lower()
        else:
            target_username = text.lower()
        
        user_found = None
        if target_user_id:
            user_found = users.get(target_user_id)
        elif target_username:
            for uid, user_data in users.items():
                if user_data.get('username', '').lower() == target_username:
                    user_found = user_data
                    target_user_id = uid
                    break
        
        if user_found and target_user_id:
            users[target_user_id]['subscribed'] = False
            
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text="""❌ Obuna Ruxsatingiz Olib Tashlandi!

💰 Yangi obuna sotib olish uchun admin bilan bog'laning.

👨‍💼 Admin: @MasulyatliOdam"""
                )
                user_msg = "✅ Foydalanuvchiga xabar yuborildi"
            except Exception as e:
                user_msg = f"⚠️ Foydalanuvchiga xabar yuborish mumkin emas: {str(e)}"
            
            admin_notification = f"""❌ RUXSAT OLIB TASHLANDI

👤 Foydalanuvchi:
├─ ID: {str(target_user_id)}
├─ Ism: {user_found.get('full_name', "Noma'lum")}
├─ Username: @{user_found.get('username', "yo'q")}
└─ Telefon: {user_found.get('phone', "yo'q")}

📅 Amal vaqti: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
            
            await update.message.reply_text(admin_notification)
            save_data()
        else:
            await update.message.reply_text(
                f"❌ Foydalanuvchi topilmadi!\n"
                f"🔍 Qidiruv: {text}"
            )
        
        context.user_data['admin_action'] = None
        await admin_panel(update, context)
        return "ADMIN_ACTIONS"
    
    elif admin_action == 'add_admin':
        if user_id != MAIN_ADMIN_ID:
            await update.message.reply_text("❌ Sizda admin qo'shish huquqi yo'q!")
            await admin_panel(update, context)
            return "ADMIN_ACTIONS"
            
        target_user_id = None
        target_username = None
        
        if text.isdigit():
            target_user_id = int(text)
        elif text.startswith('@'):
            target_username = text[1:].lower()
        else:
            target_username = text.lower()
        
        user_found = None
        if target_user_id:
            user_found = users.get(target_user_id)
        elif target_username:
            for uid, user_data in users.items():
                if user_data.get('username', '').lower() == target_username:
                    user_found = user_data
                    target_user_id = uid
                    break
        
        if user_found and target_user_id:
            if target_user_id in admins:
                await update.message.reply_text("❌ Bu foydalanuvchi allaqachon admin!")
            else:
                admins.add(target_user_id)
                save_data()
                
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text="""🎉 Tabriklaymiz! Sizga admin huquqi berildi!

✅ Endi admin panelidan foydalanishingiz mumkin."""
                    )
                except Exception as e:
                    print(f"Xabar yuborishda xatolik: {e}")
                
                admin_notification = f"""✅ YANGI ADMIN QO'SHILDI

👤 Foydalanuvchi:
├─ ID: {str(target_user_id)}
├─ Ism: {user_found.get('full_name', "Noma'lum")}
├─ Username: @{user_found.get('username', "yo'q")}
└─ Telefon: {user_found.get('phone', "yo'q")}

📅 Amal vaqti: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
                
                await update.message.reply_text(admin_notification)
        else:
            await update.message.reply_text(
                f"❌ Foydalanuvchi topilmadi!\n"
                f"🔍 Qidiruv: {text}"
            )
        
        context.user_data['admin_action'] = None
        await admin_panel(update, context)
        return "ADMIN_ACTIONS"
    
    elif admin_action == 'remove_admin':
        if user_id != MAIN_ADMIN_ID:
            await update.message.reply_text("❌ Sizda admin o'chirish huquqi yo'q!")
            await admin_panel(update, context)
            return "ADMIN_ACTIONS"
            
        target_user_id = None
        target_username = None
        
        if text.isdigit():
            target_user_id = int(text)
        elif text.startswith('@'):
            target_username = text[1:].lower()
        else:
            target_username = text.lower()
        
        user_found = None
        if target_user_id:
            user_found = users.get(target_user_id)
        elif target_username:
            for uid, user_data in users.items():
                if user_data.get('username', '').lower() == target_username:
                    user_found = user_data
                    target_user_id = uid
                    break
        
        if user_found and target_user_id:
            if target_user_id not in admins:
                await update.message.reply_text("❌ Bu foydalanuvchi admin emas!")
            elif target_user_id == MAIN_ADMIN_ID:
                await update.message.reply_text("❌ Asosiy adminni o'chirib bo'lmaydi!")
            else:
                admins.remove(target_user_id)
                save_data()
                
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text="""❌ Sizning admin huquqingiz olib tashlandi!"""
                    )
                except Exception as e:
                    print(f"Xabar yuborishda xatolik: {e}")
                
                admin_notification = f"""❌ ADMIN O'CHIRILDI

👤 Foydalanuvchi:
├─ ID: {str(target_user_id)}
├─ Ism: {user_found.get('full_name', "Noma'lum")}
├─ Username: @{user_found.get('username', "yo'q")}
└─ Telefon: {user_found.get('phone', "yo'q")}

📅 Amal vaqti: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
                
                await update.message.reply_text(admin_notification)
        else:
            await update.message.reply_text(
                f"❌ Foydalanuvchi topilmadi!\n"
                f"🔍 Qidiruv: {text}"
            )
        
        context.user_data['admin_action'] = None
        await admin_panel(update, context)
        return "ADMIN_ACTIONS"
    
    elif admin_action == 'set_price':
        if user_id != MAIN_ADMIN_ID:
            await update.message.reply_text("❌ Sizda obuna narxini o'zgartirish huquqi yo'q!")
            await admin_panel(update, context)
            return "ADMIN_ACTIONS"
            
        if text.isdigit():
            global subscription_price
            new_price = int(text)
            subscription_price = new_price
            save_data()
            
            await update.message.reply_text(
                f"✅ Obuna narxi muvaffaqiyatli o'zgartirildi!\n\n"
                f"💰 Yangi narx: {subscription_price} so'm"
            )
        else:
            await update.message.reply_text("❌ Iltimos, faqat raqam kiriting!")
        
        context.user_data['admin_action'] = None
        await admin_panel(update, context)
        return "ADMIN_ACTIONS"
    
    elif admin_action == 'broadcast':
        message = text
        successful = 0
        failed = 0
        
        broadcast_text = message
        
        progress_msg = await update.message.reply_text(
            "📤 Xabar barcha foydalanuvchilaga yuborilmoqda..."
        )
        
        for uid in users.keys():
            try:
                await context.bot.send_message(
                    chat_id=uid, 
                    text=broadcast_text
                )
                successful += 1
                await asyncio.sleep(0.1)
            except Exception as e:
                failed += 1
                print(f"Xabar yuborishda xatolik {uid}: {e}")
        
        try:
            await progress_msg.delete()
        except:
            pass
        
        await update.message.reply_text(
            f"""📢 Xabar Yuborish Yakunlandi!

✅ Muvaffaqiyatli: {successful}
❌ Xatolik: {failed}"""
        )
        
        context.user_data['admin_action'] = None
        await admin_panel(update, context)
        return "ADMIN_ACTIONS"
    
    return "ADMIN_ACTIONS"

async def handle_ad_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    
    if text == '🔙 Orqaga':
        context.user_data['admin_action'] = None
        await admin_panel(update, context)
        return "ADMIN_ACTIONS"
    
    target_user_input = context.user_data.get('target_user_input')
    
    add_ad = True
    if text == 'Reklamasiz':
        add_ad = False
    
    target_user_id = None
    target_username = None
    
    if target_user_input.isdigit():
        target_user_id = int(target_user_input)
    elif target_user_input.startswith('@'):
        target_username = target_user_input[1:].lower()
    else:
        target_username = target_user_input.lower()
    
    user_found = None
    if target_user_id:
        user_found = users.get(target_user_id)
    elif target_username:
        for uid, user_data in users.items():
            if user_data.get('username', '').lower() == target_username:
                user_found = user_data
                target_user_id = uid
                break
    
    if user_found and target_user_id:
        users[target_user_id]['subscribed'] = True
        users[target_user_id]['subscription_end'] = (datetime.now() + timedelta(days=30)).isoformat()
        users[target_user_id]['add_ad'] = add_ad
        
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="""🎉 Tabriklaymiz! Obuna Ruxsati Berildi!

✅ Endi siz botdan to'liq foydalanishingiz mumkin!
📤 Xabar yuborish funksiyasi faollashtirildi.

🤖 Bot: @AvtoXabarBot"""
            )
            user_msg = "✅ Foydalanuvchiga xabar yuborildi"
        except Exception as e:
            user_msg = f"⚠️ Foydalanuvchiga xabar yuborish mumkin emas: {str(e)}"
        
        ad_status = "Reklama bilan" if add_ad else "Reklamasiz"
        admin_notification = f"""✅ RUXSAT BERILDI

👤 Foydalanuvchi:
├─ ID: {str(target_user_id)}
├─ Ism: {user_found.get('full_name', "Noma'lum")}
├─ Username: @{user_found.get('username', "yo'q")}
└─ Telefon: {user_found.get('phone', "yo'q")}

⏰ Muddat: 30 kun
📅 Tugash sanasi: {(datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')}
📢 Reklama: {ad_status}"""
        
        await update.message.reply_text(admin_notification)
        save_data()
    else:
        await update.message.reply_text(
            f"❌ Foydalanuvchi topilmadi!\n"
            f"🔍 Qidiruv: {target_user_input}"
        )
    
    # Admin paneliga qaytish
    context.user_data['admin_action'] = None
    context.user_data['target_user_input'] = None
    await admin_panel(update, context)
    return "ADMIN_ACTIONS"

async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
    return ConversationHandler.END

async def debug_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    jobs = context.job_queue.jobs()
    debug_text = f"🔧 Faol joblar: {len(jobs)}\n"
    for job in jobs:
        debug_text += f"📋 {job.name}\n"
    await update.message.reply_text(debug_text)

def main():
    load_data()
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("qollanma", show_manual))
    app.add_handler(CommandHandler("help", show_manual))
    app.add_handler(CommandHandler("jobs", debug_jobs))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    
    admin_conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^👨‍💼 Admin Panel$'), admin_panel)
        ],
        states={
            "ADMIN_ACTIONS": [
                MessageHandler(
                    filters.Regex(r'^(✅ Ruxsat Berish|❌ Ruxsatni Olib Tashlash|➕ Admin Qo\'shish|➖ Admin O\'chirish|💰 Obuna Narxi|📊 Statistika|📢 Xabar Yuborish|🏠 Asosiy Menyu)$'), 
                    handle_admin_actions
                )
            ],
            "ADMIN_INPUT": [
                MessageHandler(filters.TEXT, handle_admin_input)
            ],
            AD_CHOICE: [
                MessageHandler(filters.TEXT, handle_ad_choice)
            ],
        },
        fallbacks=[CommandHandler("start", cancel_admin)],
    )
    
    main_conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_buttons)
        ],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone)],
            API_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_api_id)],
            API_HASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_api_hash)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_password)],
            MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_sending)],
            INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_interval)],
            DELETE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delete_confirmation)],
        },
        fallbacks=[CommandHandler("start", start), MessageHandler(filters.COMMAND, start)],
    )
    
    app.add_handler(admin_conv_handler)
    app.add_handler(main_conv_handler)
    
    print("🤖 Bot ishga tushdi:", time.ctime())
    app.run_polling()

if __name__ == "__main__":

    main()
