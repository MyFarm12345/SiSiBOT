import logging
from telegram import Update, ChatMember
from telegram.ext import Application, CommandHandler, ContextTypes, ChatMemberHandler
import random
from datetime import datetime, timedelta, timezone  # <--- ИМПОРТИРОВАЛИ timezone
import os
from aiohttp import web
import asyncio
from supabase import create_client, Client

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Supabase настройки
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    logging.critical("Не найдены переменные SUPABASE_URL или SUPABASE_KEY. Бот не может подключиться к БД.")
    exit()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ID Администраторов
ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '123456789')
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(',')]


def get_user_data(user_id: str):
    """Получить данные пользователя из Supabase"""
    try:
        response = supabase.table('users').select('*').eq('user_id', user_id).limit(1).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        # Логгируем ошибку, но не валимся
        logging.error(f"Ошибка получения данных пользователя {user_id}: {e}", exc_info=True)
        return None


def create_or_update_user(user_id: str, nickname: str, size: float = None, last_use: str = None):
    """Создать или обновить данные пользователя (UPSERT)"""
    try:
        # Готовим данные для вставки или обновления
        user_data = {
            'user_id': user_id,
            'nickname': nickname,
        }
        if size is not None:
            user_data['size'] = size
        if last_use is not None:
            user_data['last_use'] = last_use

        # Используем 'upsert' для атомарного создания или обновления
        # 'on_conflict' указывает, что делать, если 'user_id' уже существует
        response = supabase.table('users').upsert(
            user_data,
            on_conflict='user_id'
        ).execute()

        if response.data and len(response.data) > 0:
            return response.data[0]
        else:
            # Если upsert не вернул данные, запросим их
            return get_user_data(user_id)

    except Exception as e:
        logging.error(f"Ошибка создания/обновления пользователя {user_id}: {e}", exc_info=True)
        return None


def get_all_users_sorted():
    """Получить всех пользователей, отсортированных по размеру"""
    try:
        # Убедимся, что size не null, чтобы сортировка работала корректно
        response = supabase.table('users').select('*').not_.is_('size', 'is', None).order('size', desc=True).execute()
        return response.data if response.data else []
    except Exception as e:
        logging.error(f"Ошибка получения списка пользователей: {e}", exc_info=True)
        return []


def delete_user(user_id: str):
    """Удалить пользователя из базы данных"""
    try:
        response = supabase.table('users').delete().eq('user_id', user_id).execute()
        return True
    except Exception as e:
        logging.error(f"Ошибка удаления пользователя {user_id}: {e}", exc_info=True)
        return False


async def sisi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        logging.warning("Не удалось получить effective_user в sisi_command")
        return

    user_id = str(user.id)
    nickname = user.first_name or user.username or "Unknown"
    # --- ИЗМЕНЕНИЕ: Используем UTC для корректной работы на сервере ---
    current_time = datetime.now(timezone.utc)

    # Получаем данные пользователя из базы
    user_data = get_user_data(user_id)

    if not user_data:
        # Создаем нового пользователя
        logging.info(f"Создаем нового пользователя: {user_id} ({nickname})")
        user_data = create_or_update_user(user_id, nickname, 0.0, None)
        if not user_data:
            await update.message.reply_text("❌ Ошибка доступа к базе данных. Попробуйте позже.")
            return

    # Если у пользователя нет размера (старая запись), установим 0
    if user_data.get('size') is None:
        user_data['size'] = 0.0

    # Проверяем кулдаун
    if user_data.get('last_use'):
        try:
            # --- ИЗМЕНЕНИЕ: last_use_time будет 'aware' (с часовым поясом) ---
            last_use_time = datetime.fromisoformat(user_data['last_use'])

            # Убедимся, что last_use_time имеет часовой пояс для сравнения
            if last_use_time.tzinfo is None:
                last_use_time = last_use_time.replace(tzinfo=timezone.utc)

            time_passed = current_time - last_use_time
            cooldown = timedelta(hours=1)

            if time_passed < cooldown:
                time_left = cooldown - time_passed
                minutes = int(time_left.total_seconds() // 60)
                seconds = int(time_left.total_seconds() % 60)
                await update.message.reply_text(
                    f"<i>{nickname}, повтори через {minutes} мин. {seconds} сек. </i>"
                    f"<i>Текущий размер - {user_data['size']:.2f} см.</i>"
                )
                return
        except ValueError:
            logging.error(f"Неверный формат даты в 'last_use' для пользователя {user_id}: {user_data['last_use']}")

            pass
        except TypeError as e:
            logging.error(f"Ошибка сравнения времени для {user_id}: {e}", exc_info=True)
            pass


    growth = round(random.uniform(0.5, 4.0), 2)
    new_size = user_data['size'] + growth


    updated_user = create_or_update_user(
        user_id,
        nickname,
        new_size,
        current_time.isoformat()
    )

    if updated_user:
        await update.message.reply_text(
            f"<i>{nickname}, твоя грудь выросла на {growth:.2f} см!</i> "
            f"<i>Текущий размер - {new_size:.2f} см.🍈</i>"
        )
    else:
        await update.message.reply_text("❌ Ошибка обновления данных. Попробуйте позже.")


async def give_size_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    if user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав для использования этой команды.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
        )
        return

    try:
        target_user_id = str(context.args[0])
        size_to_give = float(context.args[1])

        user_data = get_user_data(target_user_id)
        current_size = 0.0
        nickname = 'Unknown'
        last_use = None

        if user_data:
            current_size = user_data.get('size', 0.0)
            nickname = user_data.get('nickname', 'Unknown')
            last_use = user_data.get('last_use')

        new_size = current_size + size_to_give
        updated_user = create_or_update_user(target_user_id, nickname, new_size, last_use)

        if updated_user:
            await update.message.reply_text(
                f"✅ Выдано {size_to_give:.2f} см пользователю {target_user_id}\n"
                f"Новый размер: {updated_user.get('size', new_size):.2f} см"
            )
        else:
            await update.message.reply_text("❌ Ошибка обновления данных")
    except ValueError:
        await update.message.reply_text("")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def set_size_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    if user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав для использования этой команды.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
        )
        return

    try:
        target_user_id = str(context.args[0])
        new_size = float(context.args[1])

        user_data = get_user_data(target_user_id)
        nickname = user_data.get('nickname', 'Unknown') if user_data else 'Unknown'
        last_use = user_data.get('last_use') if user_data else None

        updated_user = create_or_update_user(target_user_id, nickname, new_size, last_use)

        if updated_user:
            await update.message.reply_text(
                f"✅ Установлен размер {new_size:.2f} см для пользователя {target_user_id}"
            )
        else:
            await update.message.reply_text("❌ Ошибка обновления данных")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. ID и размер должны быть числами.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def delete_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить статистику пользователя по ID"""
    user = update.effective_user
    if not user:
        return

    if user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав для использования этой команды.")
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "Использование: /deleteuser <user_id>\n"
            "Пример: /deleteuser 123456789"
        )
        return

    try:
        target_user_id = str(context.args[0])

        # Проверяем существование пользователя
        user_data = get_user_data(target_user_id)

        if not user_data:
            await update.message.reply_text(f"❌ Пользователь {target_user_id} не найден в базе данных")
            return

        # Удаляем пользователя
        if delete_user(target_user_id):
            await update.message.reply_text(
                f"✅ Статистика пользователя {target_user_id} ({user_data.get('nickname', 'N/A')}) полностью удалена\n"
                f"Удален размер: {user_data.get('size', 0.0):.2f} см"
            )
        else:
            await update.message.reply_text("❌ Ошибка удаления пользователя")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users_sorted()

    if not users:
        await update.message.reply_text("📊 Статистика пуста. Никто еще не использовал /sisi")
        return

    message = "📊 <b>Топ размеров:</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for index, user_data in enumerate(users[:10], 1):
        nickname = user_data.get('nickname', 'Unknown')
        size = user_data.get('size', 0.0)

        if index <= 3:
            medal = medals[index - 1]
            message += f"{medal} <b>{index}.</b> {nickname} — {size:.2f} см\n"
        else:
            message += f"<b>{index}.</b> {nickname} — {size:.2f} см\n"

    if len(users) > 10:
        message += f"\n<i>И еще {len(users) - 10} участников...</i>"

    await update.message.reply_text(message, parse_mode='HTML')


async def my_size_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    user_id = str(user.id)
    nickname = user.first_name or user.username or "Unknown"

    user_data = get_user_data(user_id)

    if not user_data or user_data.get('size') is None:
        await update.message.reply_text(
            f"{nickname}, ты еще не использовал /sisi\n"
            f"Текущий размер - 0.00 см"
        )
        return

    size = user_data['size']
    await update.message.reply_text(
        f"{nickname}, твой текущий размер - {size:.2f} см"
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 🎀\n\n"
        "Доступные команды:\n"
        "/sisi - увеличить размер (раз в час)\n"
        "/mysize - проверить свой размер\n"
        "/stats - посмотреть топ участников\n\n"
    )


# --- УЛУЧШЕННЫЙ ОБРАБОТЧИК ---
async def track_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отслеживание изменений в участниках чата (входы, выходы, бот)"""
    try:
        # update.chat_member срабатывает, когда участник (не бот) меняет статус
        # update.my_chat_member срабатывает, когда БОТ меняет статус
        result = update.chat_member or update.my_chat_member

        if not result:
            logging.warning("track_chat_member сработал без chat_member или my_chat_member")
            return

        chat = result.chat
        user = result.new_chat_member.user
        new_status = result.new_chat_member.status
        old_status = result.old_chat_member.status

        log_message = (
            f"Chat member update in chat '{chat.title}' (ID: {chat.id}). "
            f"User: '{user.first_name}' (ID: {user.id}). "
            f"Status change: {old_status} -> {new_status}"
        )

        if update.my_chat_member:
            log_message = f"[BOT STATUS] {log_message}"
            if new_status == 'kicked' or new_status == 'left':
                logging.info(f"Бота удалили из чата: {chat.title} ({chat.id})")
            else:
                logging.info(f"Статус бота изменен в чате: {chat.title} ({chat.id}) -> {new_status}")
        else:
            log_message = f"[USER STATUS] {log_message}"
            logging.info(log_message)

    except Exception as e:
        # Логгируем ошибку, но не валимся
        logging.error(f"Ошибка в track_chat_member: {e}", exc_info=True)
        if update:
            logging.error(f"Полный объект update, вызвавший ошибку: {update.to_json()}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Логгирование ошибок"""
    logging.error(f"Update {update} caused error {context.error}", exc_info=context.error)


async def health_check(request):
    """Endpoint для UptimeBot/Render health check"""
    logging.info("Health check / OK")
    return web.Response(text='OK', status=200)


async def start_web_server():
    """Запуск веб-сервера aiohttp для health check"""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)

    port = int(os.getenv('PORT', 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)

    try:
        await site.start()
        logging.info(f"Веб-сервер запущен на порту {port}")
        # Держим сервер живым
        await asyncio.Event().wait()
    except Exception as e:
        logging.error(f"Ошибка веб-сервера: {e}", exc_info=True)
    finally:
        await runner.cleanup()


async def run_bot():
    """Запуск основного процесса бота (polling)"""
    TOKEN = os.getenv('BOT_TOKEN')

    if not TOKEN or TOKEN == 'YOUR_BOT_TOKEN':
        logging.critical("Не установлен токен бота! Установите переменную окружения BOT_TOKEN")
        return

    application = Application.builder().token(TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("sisi", sisi_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("mysize", my_size_command))
    application.add_handler(CommandHandler("givesize", give_size_command))
    application.add_handler(CommandHandler("setsize", set_size_command))
    application.add_handler(CommandHandler("deleteuser", delete_user_command))

    # Добавляем обработчик для отслеживания участников
    application.add_handler(ChatMemberHandler(track_chat_member, ChatMemberHandler.ANY_CHAT_MEMBER))

    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)

    logging.info("Бот запускается (polling)...")
    try:
        await application.run_polling(
            allowed_updates=Update.ALL_TYPES,  # <--- Упрощено для надежности
            drop_pending_updates=True
        )
    except Exception as e:
        logging.critical(f"Критическая ошибка при запуске polling: {e}", exc_info=True)


async def main():
    """Главная функция для запуска веб-сервера и бота параллельно"""
    logging.info("Запуск main()...")

    # Запускаем обе задачи параллельно
    # gather дождется завершения обеих (хотя в идеале они не должны завершаться)
    try:
        await asyncio.gather(
            start_web_server(),
            run_bot()
        )
    except Exception as e:
        logging.critical(f"Критическая ошибка в main() gather: {e}", exc_info=True)


if __name__ == '__main__':
    asyncio.run(main())
