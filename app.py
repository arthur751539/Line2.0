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

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if not all([CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, OPENAI_API_KEY]):
    raise ValueError("請確保 CHANNEL_ACCESS_TOKEN、CHANNEL_SECRET 和 OPENAI_API_KEY 已設定")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
openai.api_key = OPENAI_API_KEY

# 全域變數：儲存所有與 Bot 聯繫過的用戶 ID
user_ids = set()

def GPT_response(text):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "請使用繁體中文回答。"},
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
    if event.source.user_id:
        user_ids.add(event.source.user_id)
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
    if event.joined.members and event.joined.members[0].user_id:
        user_ids.add(event.joined.members[0].user_id)
    try:
        profile = line_bot_api.get_group_member_profile(
            event.source.group_id, event.joined.members[0].user_id)
        line_bot_api.reply_message(
            event.reply_token, TextSendMessage(text=f'{profile.display_name}，歡迎加入！'))
    except Exception:
        logging.error(f"無法取得新成員資訊: {traceback.format_exc()}")

def send_topic():
    topic = GPT_response("請給我一個新的聊天話題。")
    logging.info(f"自動發起的話題: {topic}")
    for uid in list(user_ids):
        try:
            line_bot_api.push_message(uid, TextSendMessage(text=f"📝 新話題：\n{topic}"))
            logging.info(f"推送訊息成功給 {uid}")
        except Exception:
            logging.error(f"推送話題失敗給 {uid}: {traceback.format_exc()}")

scheduler = BackgroundScheduler()
scheduler.add_job(send_topic, 'interval', minutes=1)
scheduler.start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
