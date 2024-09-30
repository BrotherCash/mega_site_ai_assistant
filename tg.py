import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
from datetime import timezone
import urllib.parse
import re
import time

# Импортируем необходимые модули из нашего проекта
from modules.database_manager import SQLiteDB
from modules.data_indexer import DataIndexer
from modules.logger_config import setup_logging
from llama_index.llms.openai import OpenAI
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.llms import ChatMessage, MessageRole

# Загрузка переменных окружения
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
DATABASE = 'bot.db'

# Настройка логгера
logger = setup_logging()

logger.info("Telegram bot script is starting...")


# Инициализация индекса
def initialize_index():
    with SQLiteDB(DATABASE) as db:
        indexer_settings = db.select_from_table('data_indexer_settings', 'index_persist_dir', 'id = 1')[0]
    data_indexer = DataIndexer(persist_dir=indexer_settings['index_persist_dir'], force_indexing=False)
    return data_indexer.index_data()


global_index = initialize_index()

user_chat_engines = {}


def get_operator_keyboard(last_question):
    encoded_message = urllib.parse.quote(f"Требуется помощь с вопросом: {last_question}")
    url = f"https://t.me/Megagroup_support_bot?start={encoded_message}"
    keyboard = [[InlineKeyboardButton("Связаться с оператором", url=url)]]
    return InlineKeyboardMarkup(keyboard)


def format_message(text):
    # Заменяем текст между двойными звездочками на жирный шрифт
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)

    # Заменяем ссылки формата [текст](url) на HTML-ссылки
    text = re.sub(r'\[(.*?)\]\((https?://\S+)\)', r'<a href="\2">\1</a>', text)

    # Добавляем перенос строки перед нумерованными списками
    text = re.sub(r'(?<!\n)(\d+\.\s)', r'\n\1', text)

    return text


def cleanup_inactive_chat_engines():
    global user_chat_engines
    current_time = time.time()
    inactive_threshold = 3600  # 1 час

    for session_id in list(user_chat_engines.keys()):
        if current_time - user_chat_engines[session_id]['last_used'] > inactive_threshold:
            del user_chat_engines[session_id]


def get_reset_keyboard():
    keyboard = [[KeyboardButton("Сбросить сессию")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def reset_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    session_id = f"tg_{user_id}"

    if session_id in user_chat_engines:
        user_chat_engines[session_id]['engine'].reset()
        del user_chat_engines[session_id]

    await update.message.reply_text(
        "Ваша сессия сброшена. Вы можете начать новый диалог.",
        reply_markup=get_reset_keyboard()
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = get_reset_keyboard()
    await update.message.reply_text(
        'Привет! Я бот-помощник. Задайте мне вопрос, и я постараюсь на него ответить. '
        'Если хотите начать диалог заново, нажмите "Сбросить сессию".',
        reply_markup=keyboard
    )


def save_chat_history(db, session_id, message):
    from datetime import datetime
    current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    db.insert_into_table('chat_history', (None, session_id, current_time, message['role'], message['content']))


async def simulate_typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int, duration: float):
    """
    Имитирует набор текста ботом в течение указанного времени.

    :param context: Контекст бота
    :param chat_id: ID чата
    :param duration: Продолжительность "набора" в секундах
    """
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    await asyncio.sleep(duration)

# test
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cleanup_inactive_chat_engines()

    if update.message.text == "Сбросить сессию":
        await reset_session(update, context)
        return

    user_id = update.effective_user.id
    session_id = f"tg_{user_id}"
    question = update.message.text

    # Проверяем, есть ли в вопросе пользователя запрос на связь с оператором
    user_requests_operator = any(phrase in question.lower() for phrase in ["с оператором", "с человеком"])

    with SQLiteDB(DATABASE) as db:
        # Сохраняем вопрос пользователя
        save_chat_history(db, session_id, {"role": "user", "content": question})

        # Получаем ответ от индекса
        response = ask_question({"initial_question": question}, db, global_index, session_id)

        # Сохраняем ответ бота
        save_chat_history(db, session_id, {"role": "assistant", "content": response})

        # Форматируем ответ
        formatted_response = format_message(response)

        # Имитируем набор ответа
        typing_duration = min(len(formatted_response) * 0.05, 10.0)  # Максимум 10 секунд
        await simulate_typing(context, chat_id, typing_duration)


        # Проверяем условия для отображения кнопки связи с оператором
        show_operator_button = (
                "свяжитесь с оператором" in response.lower() or
                user_requests_operator
        )

        if show_operator_button:
            keyboard = get_operator_keyboard(question)
            await update.message.reply_text(
                formatted_response,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                formatted_response,
                parse_mode='HTML',
                reply_markup=get_reset_keyboard()
            )

def ask_question(form, db, loaded_index, session_id):
    global user_chat_engines
    current_time = time.time()

    if session_id not in user_chat_engines:
        chat_history = get_chat_history(db, session_id)

        memory = ChatMemoryBuffer.from_defaults(
            chat_history=[
                ChatMessage(role=convert_role(msg['role']), content=msg['content'])
                for msg in chat_history
            ],
            token_limit=5000
        )

        llm = OpenAI(model="gpt-4o", temperature=0)

        chat_engine = loaded_index.as_chat_engine(
            chat_mode="condense_plus_context",
            memory=memory,
            llm=llm,
            system_prompt=(
                "You are a helpdesk chatbot, able to have normal interactions, always answering in Russian. "
                "Give detailed answers. Use numbered lists (1., 2., etc.) for step-by-step instructions. "
                "Always provide article URL from index. "
                "Provide article video URL if available."
                "If you don't have answer or information - say 'Я не могу вам ответить на этот вопрос, свяжитесь с оператором'"
            ),
            verbose=False
        )

        user_chat_engines[session_id] = {
            'engine': chat_engine,
            'last_used': current_time
        }
    else:
        user_chat_engines[session_id]['last_used'] = current_time
        chat_engine = user_chat_engines[session_id]['engine']

    response = chat_engine.chat(form['initial_question'])
    return response.response


def get_chat_history(db, session_id):
    rows = db.select_from_table('chat_history', 'role, content', f"session_id = '{session_id}'")
    return [{"role": row['role'], "content": row['content']} for row in rows]


def convert_role(role: str) -> MessageRole:
    role_mapping = {
        "user": MessageRole.USER,
        "assistant": MessageRole.ASSISTANT,
        "system": MessageRole.SYSTEM,
        "function": MessageRole.FUNCTION,
        "tool": MessageRole.TOOL,
        "chatbot": MessageRole.CHATBOT,
        "model": MessageRole.MODEL
    }
    return role_mapping.get(role.lower(), MessageRole.USER)


async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    # Здесь можно добавить дополнительную логику обработки нажатий кнопок, если потребуется в будущем


def main() -> None:
    try:
        logger.info("Initializing Telegram bot...")
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Добавляем обработчик для кнопок
        application.add_handler(CallbackQueryHandler(button_click))

        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)


if __name__ == '__main__':
    main()
