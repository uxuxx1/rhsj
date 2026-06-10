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
        [InlineKeyboardButton("установить pip", callback_data="install_pip")],
        [InlineKeyboardButton("ии помощник", callback_data="ai_help")],
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
        await query.edit_message_text("отправь python файл, максимум 0.50кб")
        context.user_data["waiting_for"] = "code_file"
    
    if query.data == "run_code":
        await query.edit_message_text("введи название пакета, например requests или numpy")
        context.user_data["waiting_for"] = "pip_package"
    
    elif query.data == "ai_help":
        user_data = get_user_data(user_id)
        if user_data["ai_requests_today"] >= 10:
            await query.edit_message_text("исчерпал лимит вопросов на сегодня, осталось 0")
        else:
            await query.edit_message_text("опиши проблему с кодом")
            context.user_data["waiting_for"] = "ai_question"
    
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
    
    if context.user_data.get("waiting_for") == "code_file":
        document = update.message.document
        
        if not document.file_name.endswith('.py'):
            await update.message.reply_text("отправь python файл с расширением .py")
            return
        
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()
        
        if not check_file_size(file_bytes):
            await update.message.reply_text("файл слишком большой, максимум 0.50кб")
            return
        
        user_data = get_user_data(user_id)
        user_data["code"] = file_bytes.decode('utf-8')
        user_data["uploaded_at"] = datetime.now()
        
        context.user_data["waiting_for"] = None
        
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
                await update.message.reply_text("код выполнился без вывода")
            
            os.remove(temp_file)
            
        except subprocess.TimeoutExpired:
            await update.message.reply_text("код выполнялся слишком долго")
        except Exception as e:
            await update.message.reply_text(f"ошибка\n{str(e)[:200]}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_text = update.message.text
    waiting_for = context.user_data.get("waiting_for")
    
    if waiting_for == "pip_package":
        package = user_text.strip()
        await update.message.reply_text(f"устанавливаю {package}...")
        
        try:
            result = subprocess.run(
                ["pip", "install", package],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                await update.message.reply_text(f"{package} установлен успешно")
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                await update.message.reply_text(f"ошибка при установке {package}\n{error_msg[:300]}")
        except subprocess.TimeoutExpired:
            await update.message.reply_text("установка заняла слишком много времени")
        except Exception as e:
            await update.message.reply_text(f"ошибка при установке\n{str(e)[:200]}")
        
        context.user_data["waiting_for"] = None
    
    elif waiting_for == "ai_question":
        user_data = get_user_data(user_id)
        
        if len(user_text) > 150:
            await update.message.reply_text("максимум 150 букв в вопросе")
            return
        
        if user_data["ai_requests_today"] >= 10:
            await update.message.reply_text("исчерпал лимит на сегодня")
            context.user_data["waiting_for"] = None
            return
        
        code = user_data["code"] if user_data["code"] else "кода нет"
        
        await update.message.reply_text("думаю...")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "google/gemini-2.5-flash-001",
                        "messages": [
                            {
                                "role": "user",
                                "content": f"помоги с кодом python\nкод:\n{code}\n\nпроблема:\n{user_text}"
                            }
                        ],
                        "max_tokens": 500
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    ai_response = data['choices'][0]['message']['content']
                    user_data["ai_requests_today"] += 1
                    
                    ai_left = 10 - user_data["ai_requests_today"]
                    await update.message.reply_text(f"решение\n{ai_response}\n\nвопросов осталось {ai_left}")
                else:
                    await update.message.reply_text("ошибка при обращении к ии")
            except Exception as e:
                await update.message.reply_text(f"ошибка {str(e)}")
        
        context.user_data["waiting_for"] = None

async def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
