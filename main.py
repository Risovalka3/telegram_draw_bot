# main.py
"""
Flask server for the Telegram drawing mini-app.

Changes in this version:
- Added Telegram /start handler: when user sends /start the bot replies with an InlineKeyboardButton linking to the web app URL with the user's chat_id as a query parameter.
- Added a /check route that returns whether static/index.html exists (for debug on Render).
- Added a catch-all route so that unknown paths are served with static files if they exist or return index.html (works for single-page apps and avoids Not Found on Render).
- Keeps the /upload and /webhook endpoints.

Environment variables used:
- TELEGRAM_TOKEN - token for your bot (optional for serving static site without Telegram features)
- WEBHOOK_URL - (optional) URL where Telegram should post updates (used to set webhook on start)
- APP_URL - public URL of the web application (used to build the link sent by /start). If APP_URL is not set, the bot will try to use WEBHOOK_URL. If neither is set, /start will tell the user that the app URL is not configured.
"""

import os
import base64
import uuid
from flask import Flask, request, jsonify, send_from_directory
from pathlib import Path

# Optional: import telebot if available
try:
    import telebot
except Exception:
    telebot = None

# Load environment variables from .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # e.g. https://your-service.onrender.com
APP_URL = os.getenv('APP_URL')  # e.g. https://your-service.onrender.com - used for /start button link

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
UPLOADS_DIR = os.path.join(STATIC_DIR, 'uploads')
Path(UPLOADS_DIR).mkdir(parents=True, exist_ok=True)

# Serve static files at the root
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='')

bot = None
if telebot and TELEGRAM_TOKEN:
    bot = telebot.TeleBot(TELEGRAM_TOKEN)

    # register a handler for /start
    @bot.message_handler(commands=['start'])
    def handle_start(message):
        chat_id = message.chat.id
        # prefer APP_URL, fallback to WEBHOOK_URL
        base_url = (APP_URL or WEBHOOK_URL or '').rstrip('/')
        if not base_url:
            bot.send_message(chat_id, "Администратор не настроил APP_URL или WEBHOOK_URL — не могу открыть мини-рисовалку.")
            return

        # build link to app including chat_id so frontend can auto-fill
        url = f"{base_url}/?chat_id={chat_id}"
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton(text='Открыть мини-рисовалку', url=url))

        bot.send_message(chat_id, "Нажми кнопку ниже, чтобы открыть мини-рисовалку. Нарисуй картинку и нажми 'Отправить в чат' — она придёт сюда.", reply_markup=markup)


@app.route('/')
def index():
    # serve index.html from static
    return app.send_static_file('index.html')


@app.route('/check')
def check():
    # debug endpoint to see if static/index.html is present on the server
    exists = os.path.exists(os.path.join(STATIC_DIR, 'index.html'))
    return f"STATIC_DIR: {STATIC_DIR}<br>index.html exists: {exists}"


@app.route('/upload', methods=['POST'])
def upload():
    """
    Accepts JSON payload { image: "data:image/png;base64,...", chat_id?: "123" }
    Saves file to static/uploads and optionally sends to Telegram chat if bot available and chat_id provided.
    """
    data = None
    # try JSON
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({'error': 'Invalid JSON'}), 400

    if not data or 'image' not in data:
        return jsonify({'error': 'no image provided'}), 400

    img_b64 = data['image']
    # strip data URL header if present
    if ',' in img_b64:
        _, img_b64 = img_b64.split(',', 1)

    try:
        img_bytes = base64.b64decode(img_b64)
    except Exception as e:
        return jsonify({'error': 'invalid base64', 'detail': str(e)}), 400

    filename = f"{uuid.uuid4().hex}.png"
    filepath = os.path.join(UPLOADS_DIR, filename)
    with open(filepath, 'wb') as f:
        f.write(img_bytes)

    # static files are served at '/', so file will be available at /uploads/<filename>
    file_url = f"/uploads/{filename}"

    chat_id = data.get('chat_id')
    if bot and chat_id:
        try:
            with open(filepath, 'rb') as photo:
                bot.send_photo(chat_id, photo)
            return jsonify({'status': 'sent', 'file': file_url}), 201
        except Exception as e:
            return jsonify({'status': 'error_sending', 'detail': str(e), 'file': file_url}), 500

    return jsonify({'status': 'saved', 'file': file_url}), 201


@app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint for Telegram webhook updates. Telegram POSTs updates here as JSON."""
    if not bot:
        return 'Bot token not configured', 400

    try:
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return '', 200
    except Exception as e:
        return jsonify({'error': 'failed processing update', 'detail': str(e)}), 500


# Catch-all: if a file exists in static, serve it; otherwise serve index.html (helps SPA routing on Render)
@app.route('/<path:path>')
def catch_all(path):
    candidate = os.path.join(STATIC_DIR, path)
    if os.path.exists(candidate) and os.path.isfile(candidate):
        return send_from_directory(STATIC_DIR, path)
    # otherwise return index.html so client-side routing works
    return app.send_static_file('index.html')


if __name__ == '__main__':
    # If a webhook URL is provided, set it on start (useful for Render deployments)
    if bot and WEBHOOK_URL:
        try:
            bot.remove_webhook()
            bot.set_webhook(WEBHOOK_URL.rstrip('/') + '/webhook')
            print('Webhook set to:', WEBHOOK_URL.rstrip('/') + '/webhook')
        except Exception as e:
            print('Failed to set webhook:', e)

    port = int(os.environ.get('PORT', 5000))
    # In production Render will use gunicorn; this run is useful for local testing
    app.run(host='0.0.0.0', port=port)
