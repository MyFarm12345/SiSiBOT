import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import random
from datetime import datetime, timedelta
import os
from aiohttp import web
import asyncio
import asyncpg

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '123456789')
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(',')]

# Глобальное подключение к БД
db_pool = None


async def init_db():
    """Инициализация подключения к базе данных"""
    global db_pool
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logging.error("DATABASE_URL не установлен!")
        return None
    
    try:
        db_pool = await asyncpg.create_pool(database_url, min_size=1, max_size=10)
        logging.info("Подключение к базе данных успешно")
        
        # Создаём таблицу если её нет
        async with db_pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    nickname TEXT NOT NULL,
                    size REAL DEFAULT 0.0,
                    last_use TIMESTAMP
                )
            ''')
        logging.info("Таблица users готова")
        return db_pool
    except Exception as e:
        logging.error(f"Ошибка подключения к БД: {e}")
        return None


async def get_user_data(user_id: int):
    """Получить данные пользователя"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT user_id, nickname, size, last_use FROM users WHERE user_id = $1',
            user_id
        )
        if row:
            return {
                'user_id': row['user_id'],
                'nickname': row['nickname'],
                'size': float(row['size']),
                'last_use': row['last_use']
            }
        return None


async def save_user_data(user_id: int, nickname: str, size: float, last_use: datetime = None):
    """Сохранить данные пользователя"""
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (user_id, nickname, size, last_use)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) 
            DO UPDATE SET nickname = $2, size = $3, last_use = $4
        ''', user_id, nickname, size, last_use)


async def get_all_users():
    """Получить всех пользователей"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            'SELECT user_id, nickname, size, last_use FROM users ORDER BY size DESC'
        )
        return [{
            'user_id': row['user_id'],
            'nickname': row['nickname'],
            'size': float(row['size']),
            'last_use': row['last_use']
        } for row in rows]


async def sisi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    nickname = user.first_name
    current_time = datetime.now()

    # Получаем данные пользователя
    user_data = await get_user_data(user_id)
    
    if not user_data:
        # Новый пользователь
        user_data = {
            'user_id': user_id,
            'nickname': nickname,
            'size': 0.0,
            'last_use': None
        }

    # Проверяем кулдаун
    if user_data['last_use']:
        time_passed = current_time - user_data['last_use']
        cooldown = timedelta(hours=1)

        if time_passed < cooldown:
            time_left = cooldown - time_passed
            minutes = int(time_left.total_seconds() // 60)
            seconds = int(time_left.total_seconds() % 60)
            await update.message.reply_text(
                f"{nickname}, повтори через {minutes} мин. {seconds} сек. "
                f"Текущий размер - {user_data['size']:.2f} см."
            )
            return

    # Увеличиваем размер
    growth = round(random.uniform(0.5, 4.0), 2)
    new_size = user_data['size'] + growth
    
    # Сохраняем в БД
    await save_user_data(user_id, nickname, new_size, current_time)

    await update.message.reply_text(
        f"{nickname}, твоя грудь выросла на {growth:.2f} см! "
        f"Текущий размер - {new_size:.2f} см."
    )


async def give_size_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав для использования этой команды.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /givesize <user_id> <размер>\n"
            "Пример: /givesize 123456789 100.5"
        )
        return

    try:
        target_user_id = int(context.args[0])
        size_to_give = float(context.args[1])

        # Получаем данные пользователя
        user_data = await get_user_data(target_user_id)
        
        if not user_data:
            user_data = {
                'nickname': 'Unknown',
                'size': 0.0,
                'last_use': None
            }
        
        new_size = user_data['size'] + size_to_give
        await save_user_data(target_user_id, user_data['nickname'], new_size, user_data['last_use'])

        await update.message.reply_text(
            f"✅ Выдано {size_to_give:.2f} см пользователю {target_user_id}\n"
            f"Новый размер: {new_size:.2f} см"
        )
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Размер должен быть числом.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def set_size_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав для использования этой команды.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /setsize <user_id> <размер>\n"
            "Пример: /setsize 123456789 100.5"
        )
        return

    try:
        target_user_id = int(context.args[0])
        new_size = float(context.args[1])

        # Получаем данные пользователя
        user_data = await get_user_data(target_user_id)
        
        if not user_data:
            user_data = {
                'nickname': 'Unknown',
                'last_use': None
            }
        
        await save_user_data(target_user_id, user_data['nickname'], new_size, user_data.get('last_use'))

        await update.message.reply_text(
            f"✅ Установлен размер {new_size:.2f} см для пользователя {target_user_id}"
        )
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Размер должен быть числом.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await get_all_users()
    
    if not users:
        await update.message.reply_text("📊 Статистика пуста. Никто еще не использовал /sisi")
        return

    message = "📊 <b>Топ размеров:</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for index, user_data in enumerate(users[:10], 1):
        nickname = user_data['nickname']
        size = user_data['size']

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
    user_id = user.id
    nickname = user.first_name

    user_data = await get_user_data(user_id)
    
    if not user_data:
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
        "В группах используй: /sisi@sisiupbot"
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Update {update} caused error {context.error}")


async def health_check(request):
    return web.Response(text='OK', status=200)


async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)

    port = int(os.getenv('PORT', 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Веб-сервер запущен на порту {port}")


async def run_bot():
    TOKEN = os.getenv('BOT_TOKEN')

    if not TOKEN or TOKEN == 'YOUR_BOT_TOKEN':
        logging.error("Не установлен токен бота! Установите переменную окружения BOT_TOKEN")
        return

    application = Application.builder().token(TOKEN).job_queue(None).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("sisi", sisi_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("mysize", my_size_command))
    application.add_handler(CommandHandler("givesize", give_size_command))
    application.add_handler(CommandHandler("setsize", set_size_command))

    application.add_error_handler(error_handler)

    logging.info("Бот запущен...")
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
    
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logging.info("Остановка бота...")
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


async def main():
    # Инициализируем БД
    await init_db()
    
    if db_pool is None:
        logging.error("Не удалось подключиться к базе данных!")
        return
    
    # Запускаем веб-сервер и бота
    await asyncio.gather(
        start_web_server(),
        run_bot()
    )


if __name__ == '__main__':
    asyncio.run(main())
