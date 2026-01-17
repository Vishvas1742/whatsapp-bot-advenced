import os
from dotenv import load_dotenv
from fastapi import FastAPI
from pywa import WhatsApp
from pywa.types import Message
from pywa.filters import text as text_filter, media as media_filter
import google.generativeai as genai
import requests
from typing import Dict, List
import tempfile

# पर्यावरण चर लोड करें
load_dotenv()

# आवश्यक कॉन्फ़िगरेशन (सभी जरूरी चर यहाँ से आएंगे)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WEBHOOK_VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
APP_ID = os.getenv("APP_ID")
APP_SECRET = os.getenv("APP_SECRET")
OWNER_WHATSAPP_NUMBER = os.getenv("OWNER_WHATSAPP_NUMBER")  # मालिक का WhatsApp नंबर (रिपोर्ट के लिए)

# चेक करें कि जरूरी चर मौजूद हैं
required_vars = ["GEMINI_API_KEY", "WHATSAPP_PHONE_ID", "WHATSAPP_TOKEN", "VERIFY_TOKEN"]
missing = [var for var in required_vars if not os.getenv(var)]
if missing:
    raise ValueError(f"Missing environment variables: {', '.join(missing)}")

# Gemini सेटअप (नवीनतम उपलब्ध मॉडल)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')  # आगे बदलाव के लिए आसान

# सिस्टम प्रॉम्प्ट (बाद में कस्टमाइजेशन के लिए अलग फाइल में ले जा सकते हैं)
SYSTEM_PROMPT = """
आप ReturnBot हैं - एक उच्च स्तरीय, अत्यंत विनम्र और प्रोफेशनल AI कस्टमर सर्विस एजेंट।
सभी जवाब हिंदी में दें।
टोन: सहानुभूतिपूर्ण, स्पष्ट, धैर्यवान और सम्मानजनक।

प्रक्रिया:
1. स्वागत करें और पुष्टि करें कि वे रिटर्न/रिफंड/एक्सचेंज के लिए आए हैं।
2. ऑर्डर डिटेल्स वेरिफाई करें।
3. समस्या समझें और प्रूफ मांगें।
4. समाधान सुझाएं।
5. पूरी जानकारी मिलने पर स्टोर मालिक को रिपोर्ट भेजें।
"""

# कन्वर्सेशन स्टेट (प्रति यूजर इतिहास)
conversations: Dict[str, List[Dict[str, str]]] = {}

app = FastAPI()

wa = WhatsApp(
    phone_id=WHATSAPP_PHONE_ID,
    token=WHATSAPP_TOKEN,
    server=app,
    verify_token=VERIFY_TOKEN,
    app_id=APP_ID,
    app_secret=APP_SECRET
)

def get_gemini_reply(user_wa_id: str, user_message: str, image_path: str = None) -> str:
    """Gemini से जवाब जनरेट करें (इमेज सपोर्ट के साथ)"""
    if user_wa_id not in conversations:
        conversations[user_wa_id] = [
            {"role": "user", "parts": [SYSTEM_PROMPT]},
            {"role": "model", "parts": ["समझ गया। मैं तैयार हूँ।"]}
        ]

    parts = [user_message]
    if image_path:
        image = genai.upload_file(image_path)
        parts.append(image)

    conversations[user_wa_id].append({"role": "user", "parts": parts})
    chat = model.start_chat(history=conversations[user_wa_id])
    response = chat.send_message(parts if image_path else user_message)
    bot_reply = response.text.strip()
    conversations[user_wa_id].append({"role": "model", "parts": [bot_reply]})
    return bot_reply

@wa.on_message(text_filter.Text)
async def handle_text_message(client: WhatsApp, msg: Message):
    """टेक्स्ट मैसेज हैंडलर"""
    user_wa_id = msg.from_user.wa_id
    user_text = msg.text.strip()

    print(f"Received text from {user_wa_id}: {user_text}")

    # Gemini से जवाब जनरेट
    bot_response = get_gemini_reply(user_wa_id, user_text)
    await msg.reply_text(bot_response)

    # रिपोर्ट भेजने की शर्त (यहाँ आप आगे बेहतर कंडीशन बना सकते हैं)
    if "हाँ" in user_text or "confirm" in user_text.lower() or "भेज दो" in user_text:
        report = (
            f"नया रिटर्न अनुरोध:\n"
            f"ग्राहक नंबर: {user_wa_id}\n"
            f"समस्या/जवाब: {user_text}\n"
            f"सुझाव: जांच के बाद अप्रूव या रिजेक्ट करें"
        )

        if OWNER_WHATSAPP_NUMBER:
            await client.send_message(to=OWNER_WHATSAPP_NUMBER, text=report)
            await msg.reply_text("आपका अनुरोध स्टोर मालिक को भेज दिया गया है। जल्द अपडेट मिलेगा।")
        else:
            print("OWNER_WHATSAPP_NUMBER environment variable नहीं मिला")

@wa.on_message(media_filter.Media)
async def handle_media_message(client: WhatsApp, msg: Message):
    """फोटो/मीडिया हैंडलर"""
    if not msg.media.image:
        await msg.reply_text("क्षमा करें, मैं अभी केवल तस्वीरें हैंडल कर सकता हूँ।")
        return

    user_wa_id = msg.from_user.wa_id
    print(f"Received image from {user_wa_id}")

    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
        response = requests.get(msg.media.url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
        tmp_file.write(response.content)
        image_path = tmp_file.name

    analysis_message = "ग्राहक ने समस्या की तस्वीर भेजी है। कृपया एनालाइज करें और रिस्पॉन्स दें।"
    bot_response = get_gemini_reply(user_wa_id, analysis_message, image_path)
    os.unlink(image_path)

    await msg.reply_text(bot_response)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
