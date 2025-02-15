# -*- coding: utf-8 -*-
from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import openai
import os
import traceback
import logging
from apscheduler.schedulers.background import BackgroundScheduler
import json

# 設置日誌記錄
logging.basicConfig(level=logging.INFO)

# 初始化 Flask
app = Flask(__name__)

# 讀取環境變數
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# 確保環境變數已設置
if not all([CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, OPENAI_API_KEY]):
    raise ValueError("請確保 CHANNEL_ACCESS_TOKEN、CHANNEL_SECRET 和 OPENAI_API_KEY 已設定")

# 初始化 LINE Bot & OpenAI API
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
openai.api_key = OPENAI_API_KEY

# 記錄用戶 ID 的文件
USER_DATA_FILE = "users.json"

def load_users():
    """ 載入已記錄的用戶 ID """
    return json.load(open(USER_DATA_FILE, "r", encoding="utf-8")) if os.path.exists(USER_DATA_FILE) else []

def save_users(users):
    """ 儲存用戶 ID """
    with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=4)

def add_user(user_id):
    """ 記錄新用戶，避免重複 """
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        save_users(users)

def GPT_generate_topic():
    """ 透過 OpenAI 生成聊天話題（繁體中文） """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "請生成一個有趣的聊天話題，使用繁體中文。"},
                {"role": "user", "content": "請給我一個新的聊天話題。"}
            ],
            temperature=0.7,
            max_tokens=100
        )
        return response['choices'][0]['message']['content'].strip()
    except Exception:
        logging.error(f"生成話題時發生錯誤: {traceback.format_exc()}")
        return "今天的話題生成失敗了，請稍後再試！"

def send_scheduled_topic():
    """ 每 10 分鐘發送話題給所有聯繫過的用戶 """
    users = load_users()
    if not users:
        logging.info("沒有用戶可發送話題")
        return
    topic = GPT_generate_topic()
    for user_id in users:
        try:
            line_bot_api.push_message(user_id, TextSendMessage(text=f"📢 今日話題：\n{topic}"))
            logging.info(f"已發送話題給用戶 {user_id}: {topic}")
        except Exception:
            logging.error(f"無法發送話題給 {user_id}: {traceback.format_exc()}")

# 設定定時發送，每 10 分鐘執行一次
scheduler = BackgroundScheduler()
scheduler.add_job(send_scheduled_topic, 'interval', minutes=10)
scheduler.start()

@app.route("/callback", methods=['POST'])
def callback():
    """ 接收 LINE Webhook 回調 """
    signature = request.headers.get('X-Line-Signature')
    if not signature:
        abort(400, "缺少 X-Line-Signature")
    body = request.get_data(as_text=True)
    logging.info(f"收到請求: {body}")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400, "無效的簽名")
    return jsonify({"status": "OK"}), 200

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    """ 處理來自 LINE 的文字訊息 """
    user_id = event.source.user_id
    add_user(user_id)  # 記錄用戶 ID

    user_message = event.message.text.lower()
    try:
        if user_message in ["話題", "新話題", "給我一個話題"]:
            topic = GPT_generate_topic()
            reply_text = f"📝 新話題：\n{topic}"
        else:
            reply_text = "請輸入「話題」來獲取新的聊天話題！"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
    except Exception:
        logging.error(f"回應用戶時發生錯誤: {traceback.format_exc()}")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="發生錯誤，請稍後再試。"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
