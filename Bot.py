import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import random
from datetime import datetime, timedelta
import os
from aiohttp import web
import asyncio
from supabase import create_client, Client

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Supabase настройки
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '123456789')
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(',')]


def get_user_data(user_id: str):
    """Получить данные пользователя из Supabase"""
    try:
        response = supabase.table('users').select('*').eq('user_id', user_id).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        logging.error(f"Ошибка получения данных пользователя: {e}")
        return None


def create_or_update_user(user_id: str, nickname: str, size: float = None, last_use: str = None):
    """Создать или обновить данные пользователя"""
    try:
        existing_user = get_user_data(user_id)
        
        if existing_user:
            # Обновляем существующего пользователя
            update_data = {'nickname': nickname}
            if size is not None:
                update_data['size'] = size
            if last_use is not None:
                update_data['last_use'] = last_use
            
            response = supabase.table('users').update(update_data).eq('user_id', user_id).execute()
            return response.data[0] if response.data else None
        else:
            # Создаем нового пользователя
            new_user = {
                'user_id': user_id,
                'nickname': nickname,
                'size': size if size is not None else 0.0,
                'last_use': last_use
            }
            response = supabase.table('users').insert(new_user).execute()
            return response.data[0] if response.data else None
    except Exception as e:
        logging.error(f"Ошибка создания/обновления пользователя: {e}")
        return None


def get_all_users_sorted():
    """Получить всех пользователей, отсортированных по размеру"""
    try:
        response = supabase.table('users').select('*').order('size', desc=True).execute()
        return response.data if response.data else []
    except Exception as e:
        logging.error(f"Ошибка получения списка пользователей: {e}")
        return []


def delete_user(user_id: str):
    """Удалить пользователя из базы данных"""
    try:
        response = supabase.table('users').delete().eq('user_id', user_id).execute()
        return True
    except Exception as e:
        logging.error(f"Ошибка удаления пользователя: {e}")
        return False


async def sisi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    nickname = user.first_name or user.username or "Unknown"
    current_time = datetime.now()

    # Получаем данные пользователя из базы
    user_data = get_user_data(user_id)

    if not user_data:
        # Создаем нового пользователя
        user_data = create_or_update_user(user_id, nickname, 0.0, None)
        if not user_data:
            await update.message.reply_text("❌ Ошибка доступа к базе данных")
            return

    # Проверяем кулдаун
    if user_data['last_use']:
        last_use_time = datetime.fromisoformat(user_data['last_use'])
        time_passed = current_time - last_use_time
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
    
    # Обновляем в базе данных
    updated_user = create_or_update_user(
        user_id, 
        nickname, 
        new_size, 
        current_time.isoformat()
    )

    if updated_user:
        await update.message.reply_text(
            f"{nickname}, твоя грудь выросла на {growth:.2f} см! "
            f"Текущий размер - {new_size:.2f} см."
        )
    else:
        await update.message.reply_text("❌ Ошибка обновления данных")


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
        target_user_id = str(context.args[0])
        size_to_give = float(context.args[1])

        user_data = get_user_data(target_user_id)
        
        if not user_data:
            user_data = create_or_update_user(target_user_id, 'Unknown', size_to_give, None)
        else:
            new_size = user_data['size'] + size_to_give
            user_data = create_or_update_user(target_user_id, user_data['nickname'], new_size, user_data['last_use'])

        if user_data:
            await update.message.reply_text(
                f"✅ Выдано {size_to_give:.2f} см пользователю {target_user_id}\n"
                f"Новый размер: {user_data['size']:.2f} см"
            )
        else:
            await update.message.reply_text("❌ Ошибка обновления данных")
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
        target_user_id = str(context.args[0])
        new_size = float(context.args[1])

        user_data = get_user_data(target_user_id)
        nickname = user_data['nickname'] if user_data else 'Unknown'
        last_use = user_data['last_use'] if user_data else None
        
        updated_user = create_or_update_user(target_user_id, nickname, new_size, last_use)

        if updated_user:
            await update.message.reply_text(
                f"✅ Установлен размер {new_size:.2f} см для пользователя {target_user_id}"
            )
        else:
            await update.message.reply_text("❌ Ошибка обновления данных")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Размер должен быть числом.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def delete_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить статистику пользователя по ID"""
    user = update.effective_user

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
                f"✅ Статистика пользователя {target_user_id} ({user_data['nickname']}) полностью удалена\n"
                f"Удален размер: {user_data['size']:.2f} см"
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
    user_id = str(user.id)
    nickname = user.first_name or user.username or "Unknown"

    user_data = get_user_data(user_id)

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
        "Команды для администраторов:\n"
        "/givesize <user_id> <размер> - добавить размер\n"
        "/setsize <user_id> <размер> - установить размер\n"
        "/deleteuser <user_id> - удалить статистику\n\n"
        "В группах используй: /sisi@your_bot_username"
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

    if not SUPABASE_URL or not SUPABASE_KEY:
        logging.error("Не установлены данные Supabase! Установите SUPABASE_URL и SUPABASE_KEY")
        return

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("sisi", sisi_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("mysize", my_size_command))
    application.add_handler(CommandHandler("givesize", give_size_command))
    application.add_handler(CommandHandler("setsize", set_size_command))
    application.add_handler(CommandHandler("deleteuser", delete_user_command))

    application.add_error_handler(error_handler)

    logging.info("Бот запущен...")
    await application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


async def main():
    await asyncio.gather(
        start_web_server(),
        run_bot()
    )


if __name__ == '__main__':
    asyncio.run(main())
