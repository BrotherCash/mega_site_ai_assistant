from .logger_config import setup_logging
import requests
from bs4 import BeautifulSoup, Comment

from urllib.parse import urlparse, urljoin
import json
import os
import shutil


from bs4 import Comment
from urllib.parse import urljoin


class HelpMegagroupRuJson:
    @staticmethod
    def format_content(content, base_url):
        # Очистка текста от ненужных тегов и комментариев
        for tag in content(['script', 'style', 'sup', 'link']):
            tag.decompose()

        comments = content.find_all(string=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment.extract()

        # Извлечение значения chapter
        chapter = ""
        site_path = content.find('div', class_='site-path')
        if site_path:
            links = site_path.find_all('a')
            if len(links) > 1:
                chapter = links[1].find('span').get_text().strip()

        # Заполнение JSON-структуры
        data = {
            "chapter": chapter,
            "article_url": base_url,
            "article_title": content.find('h1').get_text().strip() if content.find('h1') else "",
            "article_subtitles": [h2.get_text().strip() for h2 in content.find_all('h2')],
            "article_text": "",
            "article_images": [],
            "article_video": []
        }

        for class_name in ['help_rating_form', 'site-path']:
            for tag in content.find_all(class_=class_name):
                tag.decompose()

        # Преобразование HTML в текст с сохранением ссылок и переносов строк
        for a in content.find_all("a", href=True):
            href = urljoin(base_url, a['href'])  # Преобразование относительной ссылки в абсолютную
            a.replace_with(f"{a.get_text()} {href}")

        # Сохранение ссылок на изображения
        images = []
        for img in content.find_all("img", src=True):
            src = urljoin(base_url, img['src'])  # Преобразование относительной ссылки в абсолютную
            images.append(src)
            img.replace_with(f"[Изображение: {src}]")

        data["article_images"] = images

        # Сохранение iframe с YouTube видео
        videos = []
        for iframe in content.find_all("iframe"):
            if 'youtube.com' in iframe['src']:
                video_src = iframe['src'].replace('embed/', 'watch?v=')
                videos.append(video_src)
                iframe.decompose()

        data["article_video"] = videos

        # Получение текста из контента
        data["article_text"] = content.get_text(separator="\n")

        return data


class HelpMegagroupRuPlainText:
    @staticmethod
    def format_content(content, base_url):
        # Исключить <script>, <style> и прочие теги
        for tag in content(['script', 'style', 'sup', 'link']):
            tag.decompose()

        # Найти и удалить все комментарии
        comments = content.find_all(string=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment.extract()

        url_info = f"[Ссылка на статью: {base_url}]\n"
        # Извлекаем текст заголовка h1, если он есть
        h1_text = content.find('h1')
        if h1_text:
            h1_info = f"[Заголовок статьи: {h1_text.get_text().strip()}]\n"
        else:
            h1_info = "\n"

        # Извлечение и форматирование текста всех подзаголовков h2
        h2_elements = content.find_all('h2')
        h2_texts = [h2.get_text().strip() for h2 in h2_elements]
        h2_info = "[Подзаголовки статьи: " + ", ".join(
            h2_texts) + "]\n" if h2_texts else "\n"

        # Исключить все теги с классами
        for class_name in ['help_rating_form', 'site-path']:
            for tag in content.find_all(class_=class_name):
                tag.decompose()

        # Преобразование HTML в текст с сохранением ссылок и переносов строк
        for a in content.find_all("a", href=True):
            href = urljoin(base_url, a['href'])  # Преобразование относительной ссылки в абсолютную
            a.replace_with(f"{a.get_text()} {href}")

        # Сохранение ссылок на изображения
        for img in content.find_all("img", src=True):
            src = urljoin(base_url, img['src'])  # Преобразование относительной ссылки в абсолютную
            img.replace_with(f"[Изображение: {src}]")

        # Получение текста из контента
        content_text = content.get_text(separator="\n")
        # Собираем полный текст, добавляя информацию о URL и заголовке в начало
        full_text = url_info + h1_info + h2_info + "\n" + content_text

        return full_text


class HelpMegagroupRuHtml:
    @staticmethod
    def format_content(content, base_url):

        # Исключить <script>, <style>, <sup>, <link> и прочие теги
        for tag in content(['script', 'style', 'sup', 'link']):
            tag.decompose()

        # Найти и удалить все комментарии
        comments = content.find_all(string=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment.extract()

        # Исключить все теги с классами
        for class_name in ['help_rating_form', 'site-path']:
            for tag in content.find_all(class_=class_name):
                tag.decompose()

        url_info = f"[Ссылка на статью: {base_url}]\n"

        # Преобразование HTML в текст с сохранением ссылок
        for a in content.find_all("a", href=True):
            href = urljoin(base_url, a['href'])  # Преобразование относительной ссылки в абсолютную
            a['href'] = href

        # Получение HTML контента
        content_html = content.prettify()

        # Получаем текст заголовка h1, если он есть
        h1_text = content.find('h1')
        if h1_text:
            h1_info = f"[Заголовок статьи: {h1_text.get_text().strip()}]\n"
        else:
            h1_info = "\n"

        # Сохранение iframe с YouTube видео
        videos = []
        for iframe in content.find_all("iframe"):
            if 'youtube.com' in iframe['src']:
                video_src = iframe['src'].replace('embed/', 'watch?v=')
                videos.append(video_src)
                iframe.decompose()
        video_link = f"[Видео: {videos}]\n"

        # # Извлечение и форматирование текста всех подзаголовков h2
        # h2_elements = content.find_all('h2')
        # h2_texts = [h2.get_text().strip() for h2 in h2_elements]
        # h2_info = "[Подзаголовки статьи: " + ", ".join(
        #     h2_texts) + "]\n" if h2_texts else "\n"

        # Создаем HTML с сохранением структуры исходного контента, за исключением удаленных тегов
        full_html = url_info + h1_info + video_link + content_html

        return full_html


class ContentDownloader:
    def __init__(self, folder_to_save, content_formatter_str):
        self.folder_to_save = folder_to_save
        self.logger = setup_logging()
        self.file_extension = ''

        # Определение класса форматирования контента
        if content_formatter_str == "HelpMegagroupRuPlainText":
            self.content_formatter = HelpMegagroupRuPlainText
            self.file_extension = '.txt'
        elif content_formatter_str == "HelpMegagroupRuHtml":
            self.content_formatter = HelpMegagroupRuHtml
            self.file_extension = '.html'
        elif content_formatter_str == "HelpMegagroupRuJson":
            self.content_formatter = HelpMegagroupRuJson
            self.file_extension = '.json'
        else:
            # Здесь можно задать класс форматирования контента по умолчанию или выдать ошибку
            self.content_formatter = None
            self.logger.error(f'Неизвестный форматтер контента: {content_formatter_str}')

    def save_content(self, url, percent):
        page = requests.get(url)
        if page.status_code != 200:
            print(f'Не удалось получить данные с {url}')
            return

        soup = BeautifulSoup(page.text, 'html.parser')
        content_block = soup.find(class_='content-inner')
        if content_block is not None:
            content = self.content_formatter.format_content(content_block, url)  # Передаем базовый URL в функцию
            filename = os.path.basename(urlparse(url).path).split('.')[0] + self.file_extension
            if not filename.strip():
                filename = 'index' + self.file_extension
            os.makedirs(self.folder_to_save, exist_ok=True)
            with open(os.path.join(self.folder_to_save, filename), 'w', encoding='utf-8') as file:
                if self.file_extension == '.json':
                    file.write(json.dumps(content, ensure_ascii=False, indent=4))
                else:
                    file.write(content)
            self.logger.info(f'{percent}% Содержимое {url} сохранено в {filename}')


class FolderCleaner:
    def __init__(self):
        self.logger = setup_logging()

    def clear_folder(self, folder_to_clear):
        path_to_help_folder = os.path.join(os.getcwd(), folder_to_clear)

        for filename in os.listdir(path_to_help_folder):
            file_path = os.path.join(path_to_help_folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                    self.logger.info(f"Удален файл {file_path}")
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                self.logger.warning(f'Не удалось удалить {file_path}. Причина: {e}')