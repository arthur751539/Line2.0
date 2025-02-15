# -*- coding: utf-8 -*-
from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, PostbackEvent, MemberJoinedEvent
import openai
import os
import traceback
import logging
import json

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# 從環境變數取得 LINE 與 OpenAI 的金鑰
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if not all([CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, OPENAI_API_KEY]):
    raise ValueError("請確保 CHANNEL_ACCESS_TOKEN、CHANNEL_SECRET 和 OPENAI_API_KEY 已設定")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
openai.api_key = OPENAI_API_KEY

def load_config():
    """
    從 config.json 載入設定內容，若讀取失敗則使用預設設定。
    """
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        logging.error(f"讀取設定檔失敗: {traceback.format_exc()}")
        return {"language": "繁體中文", "tone": "正常"}

def GPT_response(text):
    """
    呼叫 OpenAI ChatCompletion API，並根據 config.json 中的設定模擬指定語氣。
    """
    config = load_config()
    system_message = f"你是一個聊天機器人，請使用 {config.get('language', '繁體中文')} 回答，且以 {config.get('tone', '正常')} 的語氣回應。"
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",  # 請確保使用正確且有權限的模型名稱
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": text}
            ],
            temperature=0.5,
            max_tokens=500
        )
        return response['choices'][0]['message']['content'].strip()
    except Exception:
        logging.error(f"OpenAI API 呼叫失敗: {traceback.format_exc()}")
        return "發生錯誤，請稍後再試。"

@app.route("/callback", methods=['POST'])
def callback():
    # 驗證 LINE 傳來的簽名
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
    """
    處理用戶傳來的文字訊息，並回應 GPT 的回答。
    """
    user_message = event.message.text
    try:
        bot_reply = GPT_response(user_message)
        logging.info(f"用戶: {user_message} -> GPT 回應: {bot_reply}")
    except Exception:
        logging.error(f"回應用戶時發生錯誤: {traceback.format_exc()}")
        bot_reply = "發生錯誤，請稍後再試。"
    
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=bot_reply))

@handler.add(PostbackEvent)
def handle_postback(event):
    logging.info(f"收到 Postback 事件: {event.postback.data}")

@handler.add(MemberJoinedEvent)
def welcome(event):
    try:
        profile = line_bot_api.get_group_member_profile(
            event.source.group_id, event.joined.members[0].user_id)
        line_bot_api.reply_message(
            event.reply_token, TextSendMessage(text=f'{profile.display_name}，歡迎加入！'))
    except Exception:
        logging.error(f"無法取得新成員資訊: {traceback.format_exc()}")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
