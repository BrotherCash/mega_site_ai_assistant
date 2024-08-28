# загрузка flask
from flask import Flask, render_template, request, redirect, jsonify, session, Response, stream_with_context, url_for, send_file
from flask_session import Session

# Загрузка системных библиотек
import asyncio
import sys
from dotenv import load_dotenv
import os
# import re
import time
import uuid
from datetime import datetime, timezone
from math import ceil
import csv
from io import StringIO, BytesIO

# загрузка модулей
from modules.database_manager import SQLiteDB
from modules.html_parser import ContentDownloader, FolderCleaner
from modules.data_indexer import DataIndexer
from modules.logger_config import setup_logging

# Загрузка Llama Index
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.extractors import (
    SummaryExtractor,
    QuestionsAnsweredExtractor,
    TitleExtractor,
    KeywordExtractor,
)

from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.llms.openai import OpenAI
from llama_index.core.memory import ChatMemoryBuffer

app = Flask(__name__)
app.secret_key = 'beta_julia_ai_bot'

# Настройка Flask-Session для хранения сессий на файловой системе
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = os.path.join(app.root_path, 'flask_session')
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'session:'

Session(app)

DATABASE = 'bot.db'
global_index = None

# Настройка логгера и переменных окружения
logger = setup_logging()
dotenv_path = '.env'
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def load_index(db):
    indexer_settings = db.select_from_table('data_indexer_settings', 'index_persist_dir', 'id = 1')[0]
    data_indexer = DataIndexer(persist_dir=indexer_settings['index_persist_dir'], force_indexing=False)
    return data_indexer.index_data()


def initialize_index():
    global global_index
    with SQLiteDB(DATABASE) as db:
        global_index = load_index(db)
    if global_index is None:
        logger.error("Failed to initialize global_index")


# Вызываем функцию инициализации при старте приложения
initialize_index()


# ==================================================
def get_or_create_session_id():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']


def get_chat_history(db, session_id):
    query = "SELECT role, content FROM chat_history WHERE session_id = ? ORDER BY timestamp"
    rows = db.select_from_table('chat_history', 'role, content', f"session_id = '{session_id}'")
    return [{"role": row['role'], "content": row['content']} for row in rows]


def save_chat_history(db, session_id, message):
    current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    db.insert_into_table('chat_history', (None, session_id, current_time, message['role'], message['content']))


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
# ==================================================


# def format_response_with_linebreaks(text):
#     # Добавляем перенос строки перед числами с точкой (например, "1.", "2.")
#     text = re.sub(r'(\s)(\d+\.)', r'\1\n\2', text)
#
#     # Добавляем перенос строки перед "шаг" с числом
#     text = re.sub(r'(\s)(шаг \d+)', r'\1\n\2', text, flags=re.IGNORECASE)
#
#     # Заменяем двойные звездочки на HTML-теги для жирного текста
#     text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
#
#     # Заменяем одинарные переносы строк на <br>, а двойные на <p>
#     text = re.sub(r'\n\n+', '</p><p>', text)
#     text = re.sub(r'\n', '<br>', text)
#
#     # Оборачиваем весь текст в <p> теги
#     text = f'<p>{text}</p>'
#
#     return text
#
#
# def make_links_active(text):
#     # Паттерн для поиска URL
#     url_pattern = r'(https?://\S+?)(\.)?(\s|$|[)\]])'
#     first_result = re.sub(url_pattern, lambda x: f'<a href="{x.group(1)}" target="_blank">{x.group(1)}</a>{x.group(3)}', text)
#
#     # Паттерн для поиска Markdown ссылок
#     pattern = r'\[(.*?)\]\((https?://\S+?)(\.)?\)'
#     second_result = re.sub(pattern, lambda x: f'<a href="{x.group(2)}" target="_blank">{x.group(1)}</a>{"" if x.group(3) is None else x.group(3)}', first_result)
#
#     return second_result
#
#
# def shorten_links(text):
#     link_regex = r'\[([^\]]+)\]\(<a href="([^"]+)" target="_blank">([^<]+)</a>\)'
#
#     def replace_link(match):
#         text = match.group(1)
#         url = match.group(2)
#         return f'<a href="{url}" target="_blank">{text}</a>'
#
#     transformed_text = re.sub(link_regex, replace_link, text)
#
#     return transformed_text


def ask_question(form, db, loaded_index, reset_session=False):
    if loaded_index is None:
        logger.error("Index is not initialized")
        yield "Извините, система не готова. Пожалуйста, попробуйте позже."
        return

    session_id = get_or_create_session_id()
    chat_history = get_chat_history(db, session_id)

    llm = OpenAI(model="gpt-4o", temperature=0)

    memory = ChatMemoryBuffer.from_defaults(
        chat_history=[
            ChatMessage(role=convert_role(msg['role']), content=msg['content'])
            for msg in chat_history
        ],
        token_limit=5000
    )

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

    if reset_session:
        chat_engine.reset()
        yield "Сессия сброшена. Начат новый диалог."
        return

    question = form.get('initial_question', '')
    if not question:
        logger.info('Вопрос - пустая строка')
        yield ""
        return

    response = chat_engine.stream_chat(question)

    # Сохраняем вопрос пользователя
    save_chat_history(db, session_id, {"role": "user", "content": question})

    # Собираем полный ответ ассистента
    full_response = ""
    for token in response.response_gen:
        full_response += token
        yield token

    # Сохраняем полный ответ ассистента
    save_chat_history(db, session_id, {"role": "assistant", "content": full_response})


def reindex_data(db):
    downloader_settings = db.select_from_table('data_downloader_settings', 'folder', 'id = 1')[0]
    data_folder = downloader_settings['folder']
    indexer_settings = db.select_from_table('data_indexer_settings',
                                            'title_extractor_nodes, questions_answered_extractor_questions, keyword_extractor_keywords, index_persist_dir, chunk_size, chunk_overlap, llm_temperature, llm_model, add_to_index',
                                            'id = 1')[0]

    if indexer_settings['add_to_index'] == 1:
        add_to_index = True
    else:
        add_to_index = False

    data_indexer = DataIndexer(folder=data_folder, persist_dir=indexer_settings['index_persist_dir'], force_indexing=True, add_to_index=add_to_index)

    transformations = [
        SentenceSplitter(),
        TitleExtractor(nodes=indexer_settings['title_extractor_nodes']),
        QuestionsAnsweredExtractor(questions=indexer_settings['questions_answered_extractor_questions']),
        SummaryExtractor(summaries=["prev", "self"]),
        KeywordExtractor(keywords=indexer_settings['keyword_extractor_keywords']),
    ]

    data_indexer.index_data(transformations=transformations, chunk_size=indexer_settings['chunk_size'], chunk_overlap=indexer_settings['chunk_overlap'], temperature=indexer_settings['llm_temperature'], model=indexer_settings['llm_model'])


def download_content(urls, db):
    logger.info(f"Будет обработано ссылок - {len(urls)}")
    counter = 1
    # Загрузка и обработка контента
    downloader_settings = db.select_from_table('data_downloader_settings', 'folder, content_formatter', 'id = 1')[0]
    folder_cleaner = FolderCleaner()
    folder_cleaner.clear_folder(downloader_settings['folder'])

    content_downloader = ContentDownloader(downloader_settings['folder'], downloader_settings['content_formatter'])
    for url in urls:
        percent = round((counter/len(urls) * 100), 2)
        content_downloader.save_content(url, percent)

        time.sleep(5)  # Задержка в 10 секунд

        counter = counter + 1
    logger.info(f"Сохранено документов - {counter}")


def save_request_settings(form, db):
    print(int(form['top_k']))
    db.update_table('request_settings', {
        'top_k_value': int(form['top_k']),
        'question_extra_data': form['extra_data']
    }, 'id = 1')


def save_downloader_settings(form, db):
    db.update_table('data_downloader_settings', {
        'folder': form['folder'],
        'content_formatter': form['content_formatter']
    }, 'id = 1')


def save_indexer_settings(form, db):
    db.update_table('data_indexer_settings', {
        'title_extractor_nodes': int(form['title_extractor_nodes']),
        'questions_answered_extractor_questions': int(form['questions_answered_extractor_questions']),
        'keyword_extractor_keywords': int(form['keyword_extractor_keywords']),
        'index_persist_dir': form['index_persist_dir'],
        'chunk_size': int(form['chunk_size']),
        'chunk_overlap': int(form['chunk_overlap']),
        'add_to_index': 1 if 'add_to_index' in form else 0,
        'llm_temperature': float(form['llm_temperature']),
        'llm_model': form['llm_model']
    }, 'id = 1')


def save_urls(form, db):
    urls = form['urls'].split('\n')
    counter = 1
    db.delete_from_table('urls')  # Удаляем все существующие URL-адреса
    logger.info(f"Будет сохранено ссылок  - {len(urls)}")
    for url in urls:
        if url.strip():  # Добавляем URL, если он не пустой
            logger.info(f"Сохраняется {counter} ссылка  - {url}")
            db.insert_into_table('urls', (None, 1, url.strip()))
            counter = counter + 1
    logger.info(f"Cохранено ссылок  - {counter-1}")


# Обработчик главной страницы
@app.route('/', methods=['GET', 'POST'])
def index():
    # global global_index
    # if request.method == 'POST':
    #     with SQLiteDB(DATABASE) as db:
    #         if 'ask_question' in request.form and request.form['initial_question'] != "":
    #             response = ask_question(request.form, db, global_index)
    #             transformed_response = shorten_links(response)
    #             return render_template('index.html',
    #                                    question=request.form['initial_question'],
    #                                    response=transformed_response)
    #     return redirect('/')
    # else:
    #     return render_template('index.html')
    return render_template('index.html')


@app.route('/api/ask_question', methods=['POST'])
def api_ask_question():
    global global_index
    data = request.json
    if data and 'initial_question' in data and data['initial_question'] != "":
        def generate():
            try:
                with SQLiteDB(DATABASE) as db:
                    for chunk in ask_question(data, db, global_index):
                        yield f"data: {chunk}\n\n"
            except ValueError as e:
                if "Initial token count exceeds token limit" in str(e):
                    yield "data: Превышен лимит токенов. Пожалуйста, начните новую сессию.\n\n"
                else:
                    yield f"data: Произошла ошибка: {str(e)}\n\n"
            except Exception as e:
                yield f"data: Произошла непредвиденная ошибка: {str(e)}\n\n"
            finally:
                yield "data: [DONE]\n\n"

        return Response(stream_with_context(generate()), content_type='text/event-stream')
    return jsonify({'error': 'Invalid request'}), 400


# Обработчик страницы с настройками
@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        with SQLiteDB(DATABASE) as db:
            if 'save_downloader_settings' in request.form:
                save_downloader_settings(request.form, db)
            elif 'save_indexer_settings' in request.form:
                # Параметры для обновления настроек индексатора данных
                save_indexer_settings(request.form, db)
            elif 'save_urls' in request.form:
                save_urls(request.form, db)
            elif 'save_request_settings' in request.form:
                save_request_settings(request.form, db)
            elif 'download_content' in request.form:
                url_records = db.select_from_table('urls', 'url')
                urls_to_crawl = set(url[0] for url in url_records)
                download_content(urls_to_crawl, db)
            elif 'index_content' in request.form:
                reindex_data(db)
            return redirect('/settings')
    else:
        with SQLiteDB(DATABASE) as db:

            downloader_settings = db.select_from_table('data_downloader_settings', 'folder, content_formatter', 'id = 1')[0]

            indexer_settings = db.select_from_table('data_indexer_settings',
                                                    'title_extractor_nodes, questions_answered_extractor_questions, keyword_extractor_keywords, index_persist_dir, chunk_size, chunk_overlap, llm_temperature, llm_model, add_to_index',
                                                    'id = 1')[0]

            request_settings = db.select_from_table('request_settings', 'top_k_value, question_extra_data', 'id = 1')[0]

            url_records = db.select_from_table('urls', 'url')

        urls = '\n'.join(url['url'] for url in url_records)

        # Преобразуем результаты в словари для удобства работы в шаблоне, рендерим шаблон с данными
        return render_template('settings.html',
                               downloader_settings=dict(downloader_settings),
                               indexer_settings=dict(indexer_settings),
                               request_settings=dict(request_settings),
                               urls=urls
                               )


@app.route('/delete_history', methods=['POST'])
def delete_history():
    selected_ids = request.form.getlist('selected_ids')
    if selected_ids:
        with SQLiteDB(DATABASE) as db:
            id_list = ','.join(selected_ids)
            db.delete_from_table('chat_history', f'id IN ({id_list})')
    return redirect(url_for('history'))


@app.route('/history')
def history():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    with SQLiteDB(DATABASE) as db:
        total_messages = db.select_from_table('chat_history', 'COUNT(*) as count')[0]['count']
        total_pages = ceil(total_messages / per_page)

        offset = (page - 1) * per_page
        messages = db.select_from_table('chat_history',
                                        'id, session_id, timestamp, role, content',
                                        order_by='timestamp DESC',
                                        limit=f'{per_page} OFFSET {offset}')

    return render_template('history.html',
                           messages=messages,
                           page=page,
                           per_page=per_page,
                           total_pages=total_pages)


@app.route('/download_history_csv')
def download_history_csv():
    with SQLiteDB(DATABASE) as db:
        rows = db.select_from_table('chat_history',
                                    'session_id, timestamp, role, content',
                                    order_by='timestamp ASC')

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Session ID', 'Timestamp', 'Role', 'Content'])  # Write header
    cw.writerows(rows)

    output = si.getvalue().encode('utf-8')  # Encode the string to bytes
    si.close()

    bio = BytesIO(output)  # Create a BytesIO object
    bio.seek(0)

    return send_file(bio,
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name='chat_history.csv')


@app.route('/api/reset_session', methods=['POST'])
def reset_session():
    global global_index

    def generate():
        with SQLiteDB(DATABASE) as db:
            for chunk in ask_question({'initial_question': ''}, db, global_index, reset_session=True):
                yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"
    return Response(stream_with_context(generate()), content_type='text/event-stream')


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
    # app.run(host='127.0.0.1', port=5000)
