import os
import asyncio
import time
import signal
import subprocess
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

TOKEN = "8853718455:AAEEcfMdYKRCDRv3wykOVN_J7QmTmeIxiy4"
CHANNEL = "@workinuxuxx"

# ---------- настройки ----------
MAX_CODE_SIZE_KB = 0.45
CODE_TIMEOUT_SEC = 35
PACKAGE_INSTALL_TIMEOUT = 10
MAX_PACKAGES = 3
USER_COOLDOWN_SEC = 10
MAX_CONCURRENT_EXECUTIONS = 2
# ------------------------------

users_data = {}
user_processes = {}
last_global_start = datetime.now()
bot_start_time = datetime.now()
user_last_run = {}

execution_semaphore = asyncio.Semaphore(MAX_CONCURRENT_EXECUTIONS)

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
            "last_start": datetime.now(),
            "uploaded_at": None,
            "has_executed": False
        }
    return users_data[user_id]

def check_file_size(file_bytes):
    return len(file_bytes) / 1024 <= MAX_CODE_SIZE_KB

def run_code_sync(code, user_id):
    temp_file = f"/tmp/code_{user_id}.py"
    try:
        with open(temp_file, 'w') as f:
            f.write(code)

        proc = subprocess.Popen(
            ["python", temp_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True
        )
        user_processes[user_id] = proc

        try:
            stdout, stderr = proc.communicate(timeout=CODE_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            proc.wait()
            return "код выполнялся дольше 5 секунд и был остановлен"

        output = stdout if stdout else stderr
        return output if output else "выполнено"

    except Exception as e:
        return f"ошибка: {str(e)[:200]}"
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        if user_id in user_processes and user_processes[user_id] is proc:
            del user_processes[user_id]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_global_start, bot_start_time
    user_id = update.message.from_user.id

    if not await check_subscription(user_id, context):
        await update.message.reply_text(f"подпишись на канал {CHANNEL} чтобы использовать бота")
        return

    days_from_start = (datetime.now() - bot_start_time).days
    if days_from_start >= 30:
        await update.message.reply_text("бот проработал 30 дней, нужна перезагрузка на railway")
        return

    days_passed = (datetime.now() - last_global_start).days
    if days_passed >= 3:
        await update.message.reply_text("бот отключен за неиспользованием 3 дня")
        return

    last_global_start = datetime.now()
    user_data = get_user_data(user_id)
    user_data["last_start"] = datetime.now()

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
        await query.edit_message_text("отправь .py файл максимум 0.45кб")

    elif query.data == "profile":
        user_data = get_user_data(user_id)
        code_status = "загружен" if user_data["code"] else "не загружен"
        text = (
            f"профиль\n"
            f"пользователь {user_id}\n"
            f"код {code_status}\n"
            f"последний вход {user_data['last_start'].strftime('%d.%m.%Y %H:%M')}"
        )
        await query.edit_message_text(text)

    elif query.data == "limits":
        text = (
            "лимиты uxt\n"
            f"размер кода максимум {MAX_CODE_SIZE_KB}кб\n"
            "код можно загружать один\n"
            f"одновременно выполняется до {MAX_CONCURRENT_EXECUTIONS} кодов\n"
            f"таймаут выполнения {CODE_TIMEOUT_SEC} секунд\n"
            f"повторный запуск через {USER_COOLDOWN_SEC} секунд\n"
            "бот отключится если 3 дня не было входов\n"
            "все остальное без лимитов"
        )
        await query.edit_message_text(text)

    elif query.data == "stop_code":
        proc = user_processes.get(user_id)
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait()
                await query.edit_message_text("код остановлен")
            except Exception as e:
                await query.edit_message_text(f"не удалось остановить: {e}")
            finally:
                if user_id in user_processes:
                    del user_processes[user_id]
        else:
            await query.edit_message_text("код не запущен или уже завершился")

    elif query.data == "docs":
        text = (
            "документация uxt\n"
            "uxt помощник для программистов на python\n"
            "загружаешь код через запустить код максимум 0.45кб\n"
            "вводишь названия пакетов через пробел или точка если не надо\n"
            "бот устанавливает пакеты и запускает код\n"
            "получаешь результат выполнения\n"
            "профиль показывает когда последний вход\n"
            "лимиты показывает все ограничения\n"
            "остановить код останавливает выполнение если зависло\n"
            "бот работает 30 дней и отключится если 3 дня не будет входов"
        )
        await query.edit_message_text(text)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    document = update.message.document

    if not document.file_name.endswith('.py'):
        await update.message.reply_text("отправь .py файл")
        return

    # Проверяем, не выполняется ли код прямо сейчас
    proc = user_processes.get(user_id)
    if proc and proc.poll() is None:
        await update.message.reply_text("сначала дождитесь завершения текущего кода")
        return

    file = await context.bot.get_file(document.file_id)
    file_bytes = await file.download_as_bytearray()

    if not check_file_size(file_bytes):
        await update.message.reply_text(f"максимум {MAX_CODE_SIZE_KB}кб")
        return

    user_data = get_user_data(user_id)
    user_data["code"] = file_bytes.decode('utf-8')
    context.user_data.setdefault(user_id, {})["waiting_for"] = "packages"

    await update.message.reply_text("нужны пакеты? напиши названия через пробел или точка если нет")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.message.from_user.id
    user_text = update.message.text.strip()
    context.user_data.setdefault(user_id, {})
    waiting_for = context.user_data[user_id].get("waiting_for")

    if waiting_for == "packages":
        user_data = get_user_data(user_id)
        context.user_data[user_id]["waiting_for"] = None

        # Уже запускал раньше?
        if user_data.get("has_executed"):
            await update.message.reply_text("вы уже запускали код, больше нельзя")
            return

        # Выполняется ли сейчас?
        if user_id in user_processes and user_processes[user_id].poll() is None:
            await update.message.reply_text("у вас уже выполняется код, дождитесь завершения или остановите")
            return

        now = time.time()
        last = user_last_run.get(user_id, 0)
        if now - last < USER_COOLDOWN_SEC:
            await update.message.reply_text(f"слишком частые запуски, подожди {USER_COOLDOWN_SEC} секунд")
            return

        if user_text != ".":
            packages = user_text.split()
            if len(packages) > MAX_PACKAGES:
                await update.message.reply_text(f"можно установить не больше {MAX_PACKAGES} пакетов за раз")
                return
            await update.message.reply_text(f"устанавливаю {len(packages)} пакетов...")
            for package in packages:
                try:
                    subprocess.run(
                        ["pip", "install", package],
                        capture_output=True,
                        timeout=PACKAGE_INSTALL_TIMEOUT
                    )
                except subprocess.TimeoutExpired:
                    await update.message.reply_text(f"установка пакета {package} зависла, пропускаю")

        await update.message.reply_text("запускаю код... (ожидание очереди, если нужно)")

        async with execution_semaphore:
            # Повторная проверка на активный процесс (вдруг появился)
            if user_id in user_processes and user_processes[user_id].poll() is None:
                await update.message.reply_text("у вас уже выполняется код, дождитесь завершения")
                return

            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(None, run_code_sync, user_data["code"], user_id)

            user_last_run[user_id] = time.time()
            user_data["has_executed"] = True  # запоминаем, что запускал

            if output:
                await update.message.reply_text(f"результат\n{output[:500]}")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

if __name__ == "__main__":
    main()
