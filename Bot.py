import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import random
from datetime import datetime, timedelta
import json
import os


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


DATA_FILE = 'users_data.json'


ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '123456789')
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(',')]


def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logging.error("Ошибка чтения файла данных, создаём новый")
            return {}
    return {}


def save_data(data):

    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка сохранения данных: {e}")



users_data = load_data()


async def sisi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    user_id = str(user.id)
    nickname = user.first_name

    current_time = datetime.now()


    if user_id not in users_data:
        users_data[user_id] = {
            'size': 0.0,
            'last_use': None,
            'nickname': nickname
        }


    users_data[user_id]['nickname'] = nickname

    user_info = users_data[user_id]


    if user_info['last_use']:
        last_use_time = datetime.fromisoformat(user_info['last_use'])
        time_passed = current_time - last_use_time
        cooldown = timedelta(hours=1)

        if time_passed < cooldown:
            time_left = cooldown - time_passed
            minutes = int(time_left.total_seconds() // 60)
            seconds = int(time_left.total_seconds() % 60)

            await update.message.reply_text(
                f"{nickname}, повтори через {minutes} мин. {seconds} сек. "
                f"Текущий размер - {user_info['size']:.2f} см."
            )
            return


    growth = round(random.uniform(0.5, 4.0), 2)
    user_info['size'] += growth
    user_info['last_use'] = current_time.isoformat()


    save_data(users_data)

    await update.message.reply_text(
        f"{nickname}, твоя грудь выросла на {growth:.2f} см! "
        f"Текущий размер - {user_info['size']:.2f} см."
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
        target_user_id = str(context.args[0])
        size_to_give = float(context.args[1])


        if target_user_id not in users_data:
            users_data[target_user_id] = {
                'size': 0.0,
                'last_use': None,
                'nickname': 'Unknown'
            }


        users_data[target_user_id]['size'] += size_to_give
        save_data(users_data)

        await update.message.reply_text(
            f"✅ Выдано {size_to_give:.2f} см пользователю {target_user_id}\n"
            f"Новый размер: {users_data[target_user_id]['size']:.2f} см"
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
        target_user_id = str(context.args[0])
        new_size = float(context.args[1])


        if target_user_id not in users_data:
            users_data[target_user_id] = {
                'size': 0.0,
                'last_use': None,
                'nickname': 'Unknown'
            }


        users_data[target_user_id]['size'] = new_size
        save_data(users_data)

        await update.message.reply_text(
            f"✅ Установлен размер {new_size:.2f} см для пользователя {target_user_id}"
        )
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Размер должен быть числом.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not users_data:
        await update.message.reply_text("📊 Статистика пуста. Никто еще не использовал /sisi")
        return


    sorted_users = sorted(users_data.items(), key=lambda x: x[1]['size'], reverse=True)


    message = "📊 <b>Топ размеров:</b>\n\n"

    medals = ["🥇", "🥈", "🥉"]

    for index, (user_id, user_info) in enumerate(sorted_users[:10], 1):  # Топ 10
        nickname = user_info.get('nickname', 'Unknown')
        size = user_info['size']


        if index <= 3:
            medal = medals[index - 1]
            message += f"{medal} <b>{index}.</b> {nickname} — {size:.2f} см\n"
        else:
            message += f"<b>{index}.</b> {nickname} — {size:.2f} см\n"

    if len(sorted_users) > 10:
        message += f"\n<i>И еще {len(sorted_users) - 10} участников...</i>"

    await update.message.reply_text(message, parse_mode='HTML')


async def my_size_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    user_id = str(user.id)
    nickname = user.first_name

    if user_id not in users_data:
        await update.message.reply_text(
            f"{nickname}, ты еще не использовал /sisi\n"
            f"Текущий размер - 0.00 см"
        )
        return

    size = users_data[user_id]['size']
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


def main():

    TOKEN = os.getenv('BOT_TOKEN')

    if not TOKEN or TOKEN == 'YOUR_BOT_TOKEN':
        logging.error("Не установлен токен бота! Установите переменную окружения BOT_TOKEN")
        return


    application = Application.builder().token(TOKEN).build()


    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("sisi", sisi_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("mysize", my_size_command))
    application.add_handler(CommandHandler("givesize", give_size_command))
    application.add_handler(CommandHandler("setsize", set_size_command))


    application.add_error_handler(error_handler)


    logging.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == '__main__':
    main()