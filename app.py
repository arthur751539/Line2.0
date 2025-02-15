# -*- coding: utf-8 -*-
from flask import Flask, request, abort, jsonify, make_response
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import openai
import os
import traceback
import logging

# 設置日誌記錄
logging.basicConfig(level=logging.INFO)

# 初始化 Flask
app = Flask(__name__)

# 設置靜態目錄，確保資料夾存在
static_tmp_path = os.path.join(os.path.dirname(__file__), 'static', 'tmp')
os.makedirs(static_tmp_path, exist_ok=True)

# 讀取環境變數
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# 檢查環境變數是否設置
if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET or not OPENAI_API_KEY:
    raise ValueError("請確保 CHANNEL_ACCESS_TOKEN、CHANNEL_SECRET 和 OPENAI_API_KEY 已設定")

# 初始化 LINE Bot
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
openai.api_key = OPENAI_API_KEY

def GPT_response(text):
    """
    透過 OpenAI API 取得 GPT 回應，並確保返回的是繁體中文
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "請使用繁體中文回答。"},
                {"role": "user", "content": text}
            ],
            temperature=0.5,
            max_tokens=500
        )
        answer = response['choices'][0]['message']['content'].strip()
        return answer.encode('utf-8').decode('utf-8')  # 確保編碼正確
    except Exception as e:
        logging.error(f"OpenAI API 呼叫失敗: {traceback.format_exc()}")
        return "發生錯誤，請稍後再試。"

@app.route("/callback", methods=['POST'])
def callback():
    """
    接收 LINE Webhook 回調，確保 JSON 回應為 UTF-8
    """
    signature = request.headers.get('X-Line-Signature')
    if not signature:
        abort(400, "缺少 X-Line-Signature")

    body = request.get_data(as_text=True)
    logging.info(f"收到請求: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400, "無效的簽名")

    # 明確設定 Content-Type 為 UTF-8
    response = make_response(jsonify({"status": "OK"}), 200)
    response.headers["Content-Type"] = "application/json; charset=UTF-8"
    return response

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    """
    處理來自 LINE 的文字訊息，確保回應內容為 UTF-8
    """
    user_message = event.message.text
    try:
        bot_reply = GPT_response(user_message)
        logging.info(f"用戶: {user_message} -> GPT 回應: {bot_reply}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=str(bot_reply))  # 確保為字串格式
        )
    except Exception as e:
        logging.error(f"回應用戶時發生錯誤: {traceback.format_exc()}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="發生錯誤，請稍後再試。")
        )

@handler.add(PostbackEvent)
def handle_postback(event):
    """
    處理 Postback 事件
    """
    logging.info(f"收到 Postback 事件: {event.postback.data}")

@handler.add(MemberJoinedEvent)
def welcome(event):
    """
    處理新成員加入群組
    """
    try:
        uid = event.joined.members[0].user_id
        gid = event.source.group_id
        profile = line_bot_api.get_group_member_profile(gid, uid)
        name = profile.display_name
        welcome_message = TextSendMessage(text=f'{name}，歡迎加入！')
        line_bot_api.reply_message(event.reply_token, welcome_message)
    except Exception as e:
        logging.error(f"無法取得新成員資訊: {traceback.format_exc()}")

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
