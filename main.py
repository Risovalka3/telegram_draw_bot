# main.py
import os, base64, uuid, traceback
from flask import Flask, request, send_from_directory, jsonify

try:
    import telebot
    from telebot import types
except Exception:
    telebot = None
    types = None

TOKEN = os.getenv('TELEGRAM_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # e.g. https://your-service.onrender.com
app = Flask(__name__, static_folder='static')
bot = telebot.TeleBot(TOKEN) if (telebot and TOKEN) else None

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/upload', methods=['POST'])
def upload():
    data = request.get_json(force=True)
    if not data or 'image' not in data:
        return jsonify({'error': 'no image'}), 400

    img_b64 = data['image']
    header, b64 = img_b64.split(',', 1) if ',' in img_b64 else ('', img_b64)
    try:
        img_data = base64.b64decode(b64)
    except Exception as e:
        return jsonify({'error': 'bad base64', 'detail': str(e)}), 400

    os.makedirs(os.path.join('static', 'uploads'), exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    filepath = os.path.join('static', 'uploads', filename)
    with open(filepath, 'wb') as f:
        f.write(img_data)

    chat_id = data.get('chat_id')
    if bot and chat_id:
        try:
            with open(filepath, 'rb') as p:
                bot.send_photo(chat_id, p)
            return jsonify({'status': 'sent', 'file': f'/static/uploads/{filename}'}), 201
        except Exception as e:
            return jsonify({'status': 'error_sending', 'detail': str(e)}), 500

    return jsonify({'status': 'saved', 'file': f'/static/uploads/{filename}'}), 201

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram POSTs updates here. We must pass the raw JSON string into de_json."""
    if not bot:
        return 'no bot token configured', 400
    try:
        raw = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(raw)
        bot.process_new_updates([update])
        return '', 200
    except Exception:
        traceback.print_exc()
        return 'error', 500

# ---- Telegram handlers ----
if bot:
    @bot.message_handler(commands=['start'])
    def handle_start(message):
        chat_id = message.chat.id
        # базовый URL приложения — сначала берем WEBHOOK_URL, потом WEBAPP_URL, потом fallback
        base = WEBHOOK_URL or os.getenv('WEBAPP_URL') or ''
        if not base:
            base = 'https://telegram-draw-bot-wxuc.onrender.com'  # заменяй если нужно
        url = base.rstrip('/') + f'/?chat_id={chat_id}'

        kb = types.InlineKeyboardMarkup()
        # Используем WebAppInfo, чтобы Telegram открыл Web App внутри клиента (если поддерживается)
        try:
            webapp = types.WebAppInfo(url)
            kb.add(types.InlineKeyboardButton(text="🎨 Рисовать", web_app=webapp))
        except Exception:
            # запасная кнопка с обычной ссылкой
            kb.add(types.InlineKeyboardButton("🎨 Рисовать", url=url))
        try:
            bot.send_message(chat_id, "Нажми кнопку, чтобы открыть рисовалку:", reply_markup=kb)
        except Exception:
            traceback.print_exc()

# ---- start app ----
if __name__ == '__main__':
    # Устанавливаем webhook, если задали WEBHOOK_URL
    if bot and WEBHOOK_URL:
        try:
            bot.remove_webhook()
            bot.set_webhook(WEBHOOK_URL.rstrip('/') + '/webhook')
            print("Webhook set to:", WEBHOOK_URL.rstrip('/') + '/webhook')
        except Exception:
            traceback.print_exc()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
