import os
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import httpx
import subprocess
import signal

TOKEN = "8853718455:AAEEcfMdYKRCDRv3wykOVN_J7QmTmeIxiy4"
OPENROUTER_KEY = "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"
CHANNEL = "@workinuxuxx"

users_data = {}
user_processes = {}

async def check_subscription(user_id, context):
    try:
        member = await context.bot.get_chat_member(CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def get_user_data(user_id):
    if user_id not in users_data:
        users_data[user_id] = {
            "code": None,
            "ai_requests_today": 0,
            "last_ai_reset": datetime.now(),
            "uploaded_at": None
        }
    
    today = datetime.now().date()
    last_reset = users_data[user_id]["last_ai_reset"].date()
    
    if today != last_reset:
        users_data[user_id]["ai_requests_today"] = 0
        users_data[user_id]["last_ai_reset"] = datetime.now()
    
    return users_data[user_id]

def check_file_size(file_bytes):
    size_kb = len(file_bytes) / 1024
    return size_kb <= 0.5

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    is_subscribed = await check_subscription(user_id, context)
    
    if not is_subscribed:
        await update.message.reply_text(f"подпишись на канал {CHANNEL} чтобы использовать бота")
        return
    
    keyboard = [
        [InlineKeyboardButton("запустить код", callback_data="run_code")],
        [InlineKeyboardButton("профиль", callback_data="profile")],
        [InlineKeyboardButton("лимиты", callback_data="limits")],
        [InlineKeyboardButton("остановить код", callback_data="stop_code")],
        [InlineKeyboardButton("документация", callback_data="docs")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("привет в uxt, выбери что нужно", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    if query.data == "run_code":
        await query.edit_message_text("отправь .py файл максимум 0.50кб")
    
    elif query.data == "profile":
        user_data = get_user_data(user_id)
        code_status = "загружен" if user_data["code"] else "не загружен"
        ai_left = 10 - user_data["ai_requests_today"]
        text = f"твой профиль\nпользователь {user_id}\nкод {code_status}\nвопросов ии осталось {ai_left}\nдата входа {datetime.now().strftime('%d.%m.%Y')}"
        await query.edit_message_text(text)
    
    elif query.data == "limits":
        text = "лимиты uxt\nразмер кода максимум 0.50кб\nвопросов ии максимум 10 в день\nкода можно загружать один\nдругие функции без лимитов"
        await query.edit_message_text(text)
    
    elif query.data == "stop_code":
        if user_id in user_processes and user_processes[user_id]:
            try:
                os.killpg(os.getpgid(user_processes[user_id].pid), signal.SIGTERM)
                user_processes[user_id] = None
                await query.edit_message_text("код остановлен")
            except:
                await query.edit_message_text("нечего останавливать")
        else:
            await query.edit_message_text("код не запущен")
    
    elif query.data == "docs":
        text = "документация uxt\nuxt это помощник для программистов на python\nзагружаешь свой код через запустить код максимум 0.50кб\nпотом нажимаешь запустить и бот выполнит твой скрипт\nесли будет ошибка можешь отправить в найти ошибки и бот поможет\nесли не установлены импорты идешь в установить pip и вводишь название пакета\nесли все равно ошибка можешь использовать ии помощник и описать проблему\nии даст решение но максимум 10 вопросов в день\nтвой профиль показывает статус кода и сколько вопросов ии осталось\nлимиты показывает все ограничения\nостановить код останавливает выполнение если оно зависло\nhostинг бесплатный но только 30 дней потом нужна подписка"

        await query.edit_message_text(text)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    document = update.message.document
    
    if not document.file_name.endswith('.py'):
        await update.message.reply_text("отправь .py файл")
        return
    
    file = await context.bot.get_file(document.file_id)
    file_bytes = await file.download_as_bytearray()
    
    if not check_file_size(file_bytes):
        await update.message.reply_text("максимум 0.50кб")
        return
    
    user_data = get_user_data(user_id)
    user_data["code"] = file_bytes.decode('utf-8')
    context.user_data["waiting_for"] = "packages"
    
    await update.message.reply_text("нужны пакеты? напиши названия через пробел или точка если нет")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_text = update.message.text.strip()
    waiting_for = context.user_data.get("waiting_for")
    
    if waiting_for == "packages":
        user_data = get_user_data(user_id)
        context.user_data["waiting_for"] = None
        
        if user_text != ".":
            packages = user_text.split()
            await update.message.reply_text(f"устанавливаю {len(packages)} пакетов...")
            
            for package in packages:
                try:
                    subprocess.run(
                        ["pip", "install", package],
                        capture_output=True,
                        timeout=15
                    )
                except:
                    pass
        
        await update.message.reply_text("запускаю код...")
        
        try:
            temp_file = f"/tmp/code_{user_id}.py"
            with open(temp_file, 'w') as f:
                f.write(user_data["code"])
            
            result = subprocess.run(
                ["python", temp_file],
                capture_output=True,
                text=True,
                timeout=3
            )
            
            output = result.stdout if result.stdout else result.stderr
            if output:
                await update.message.reply_text(f"результат\n{output[:500]}")
            else:
                await update.message.reply_text("выполнено")
            
            os.remove(temp_file)
        except subprocess.TimeoutExpired:
            await update.message.reply_text("таймаут")
        except Exception as e:
            await update.message.reply_text(f"ошибка {str(e)[:100]}")
        
        return

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    app.run_polling()

if __name__ == "__main__":
    main()
