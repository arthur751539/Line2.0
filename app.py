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
        return {}

def GPT_response(user_text):
    """
    呼叫 OpenAI ChatCompletion API，每次都直接進入角色扮演模式，
    使用 config.json 中的設定以【聖園未花】角色回應。
    """
    config = load_config()
    roleplay_config = config.get("roleplay", {})
    
    # 組合角色扮演的 system 提示詞
    system_prompt = (
        roleplay_config.get("instructions", "") + "\n\n" +
        roleplay_config.get("character_instructions", "") + "\n\n" +
        "【角色設定】\n" +
        "名稱：" + roleplay_config.get("character_profile", {}).get("name", "") + "\n" +
        "描述：" + roleplay_config.get("character_profile", {}).get("description", "") + "\n" +
        "背景：" + roleplay_config.get("character_profile", {}).get("background", "") + "\n" +
        "外觀：" + roleplay_config.get("character_profile", {}).get("appearance", "") + "\n\n" +
        "【劇情設定】\n" +
        "初次會面情境：" + roleplay_config.get("scenario", {}).get("meeting", "") + "\n" +
        "挑戰情境：" + roleplay_config.get("scenario", {}).get("challenge", "") + "\n\n" +
        "【參考語句】\n" +
        "；".join(roleplay_config.get("reference_phrases", []))
    )
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",  # 請確保使用正確且有權限的模型名稱
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
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
    處理用戶傳來的文字訊息，並以角色扮演模式回應（永遠以【聖園未花】身份應答）。
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
