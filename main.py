# main.py
"""
Flask server for the Telegram drawing mini-app.
- Serves `static/index.html` (static folder sits next to this file)
- POST /upload accepts JSON { image: "data:image/png;base64,...", chat_id?: "123" }
  saves image to static/uploads and (if TELEGRAM_TOKEN set and chat_id provided) sends photo to Telegram chat
- POST /webhook receives Telegram updates (if TELEGRAM_TOKEN provided and webhook set)

Designed for deployment to Render (uses PORT env var). Use .env for TELEGRAM_TOKEN and WEBHOOK_URL locally.
"""

import os
import base64
import uuid
from flask import Flask, request, jsonify
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
UPLOADS_DIR = os.path.join(STATIC_DIR, 'uploads')
Path(UPLOADS_DIR).mkdir(parents=True, exist_ok=True)

# Serve static files at the root (so /index.html -> static/index.html and /uploads/... works)
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='')

bot = None
if telebot and TELEGRAM_TOKEN:
    bot = telebot.TeleBot(TELEGRAM_TOKEN)


@app.route('/')
def index():
    # send index.html from the static folder
    return app.send_static_file('index.html')


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

    # build public-ish path relative to app root
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
