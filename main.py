# main.py
from flask import Flask, request, send_from_directory, jsonify
import os, base64, uuid
try:
    import telebot
except Exception:
    telebot = None

TOKEN = os.getenv('TELEGRAM_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # например: https://your-service.onrender.com
bot = telebot.TeleBot(TOKEN) if (telebot and TOKEN) else None

app = Flask(__name__, static_folder='static')

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/upload', methods=['POST'])
def upload():
    """Ожидает JSON: { "image": "data:image/png;base64,....", "chat_id": "12345" (optional) }"""
    data = request.get_json(force=True)
    if not data or 'image' not in data:
        return jsonify({'error': 'no image'}), 400

    img_b64 = data['image']
    header, b64 = img_b64.split(',', 1) if ',' in img_b64 else ('', img_b64)
    img_data = base64.b64decode(b64)
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
    """Telegram will POST updates here"""
    if not bot:
        return 'no bot token', 400
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '', 200

if __name__ == '__main__':
    # при локальном запуске (для тестов) можно не задавать WEBHOOK_URL
    if bot and WEBHOOK_URL:
        bot.remove_webhook()
        bot.set_webhook(WEBHOOK_URL + '/webhook')
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
