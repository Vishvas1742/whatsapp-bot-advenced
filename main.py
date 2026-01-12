

import os
from pywa.types import Message
from pywa import WhatsApp
from pywa import filters
from dotenv import load_dotenv
from fastapi import FastAPI
from pywa import filters
import google.generativeai as genai
import requests
from typing import Dict, List
import tempfile

# Load environment variables
load_dotenv()

# Required configurations
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN")


def validate_env():
    if not all([
        GEMINI_API_KEY,
        WHATSAPP_PHONE_ID,
        WHATSAPP_TOKEN,
        WEBHOOK_VERIFY_TOKEN
    ]):
        raise ValueError("Missing required environment variables!")

# Gemini setup (using multimodal model for image analysis)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')  # Multimodal-capable model

# Advanced system prompt for professional return handling
SYSTEM_PROMPT = """
आप ReturnBot हैं - एक उच्च स्तरीय, अत्यंत विनम्र, प्रोफेशनल और समझदार AI कस्टमर सर्विस एजेंट।
सभी जवाब हिंदी में दें (जब तक यूजर अंग्रेजी में स्पष्ट रूप से न मांगे)।
टोन हमेशा: सहानुभूतिपूर्ण, स्पष्ट, धैर्यवान और सम्मानजनक। कभी भी अनौपचारिक या जल्दबाजी न करें।

रिटर्न/रिफंड/एक्सचेंज प्रक्रिया का क्रम (हर बार सोच-समझकर फॉलो करें, ग्राहक की बातों को ध्यान से सुनें):
1. स्वागत करें और पुष्टि करें कि वे रिटर्न/रिफंड/एक्सचेंज के लिए संपर्क कर रहे हैं।
2. ऑर्डर डिटेल्स वेरिफाई करें: ऑर्डर आईडी, नाम, खरीदारी की तारीख, मोबाइल नंबर पूछें। (सिमुलेटेड वैरिफिकेशन: मान लें वैध है यदि प्रदान किया गया।)
3. समस्या समझें: प्रोडक्ट में ठीक क्या कमी/खराबी है, कब से है, कैसे पता चला। ग्राहक की हर बात ध्यान से सुनें और सहानुभूति दिखाएं।
4. प्रूफ मांगें: "कृपया समस्या की 2-3 स्पष्ट तस्वीरें भेजें (खराब हिस्से की क्लोज-अप, पैकेजिंग आदि)"। यदि तस्वीरें भेजी गईं, तो उन्हें एनालाइज करें (जैसे: क्या वाकई खराब है? क्या मैच करता है?) और फीडबैक दें।
5. समाधान सुझाएं आधारित समस्या पर:
   - यदि रिफंड मांगा: कारण सुनें, पुष्टि करें, और प्रोसेस सिमुलेट करें (जैसे: "रिफंड 3-5 दिनों में आपके अकाउंट में क्रेडिट होगा")।
   - यदि एक्सचेंज/रिप्लेसमेंट: उपलब्ध विकल्प बताएं (जैसे: नया साइज/कलर), पुष्टि लें, और निर्देश दें (जैसे: "पुराना प्रोडक्ट कूरियर से भेजें")।
   - अन्य: यदि समस्या छोटी है, तो फिक्सिंग टिप्स दें।
6. अंतिम पुष्टि लें, अगले कदम बताएं (जैसे: रिटर्न लेबल, ट्रैकिंग)।
7. धन्यवाद देकर बात समाप्त करें, और यदि जरूरी तो ह्यूमन सपोर्ट सुझाएं।

पिछले संदेश याद रखें। दोहराव न करें। अस्पष्ट होने पर विनम्रता से स्पष्ट करें। तस्वीर एनालिसिस: यदि इमेज हो, तो डिफेक्ट चेक करें और रिस्पॉन्स में शामिल करें।
"""

# Conversation state (user WA ID → history)
conversations: Dict[str, List[Dict[str, str]]] = {}

# FastAPI app
app = FastAPI()

# PyWa client
wa = WhatsApp(
    phone_id=WHATSAPP_PHONE_ID,
    token=WHATSAPP_TOKEN,
    server=app,              # 🔥 YE LINE SAB FIX KAREGI
    verify_token=WEBHOOK_VERIFY_TOKEN
)

def get_gemini_reply(user_wa_id: str, user_message: str, image_path: str = None) -> str:
    """Generate smart, context-aware reply using Gemini, with optional image analysis"""
    if user_wa_id not in conversations:
        conversations[user_wa_id] = [
            {"role": "user", "parts": [SYSTEM_PROMPT]},
            {"role": "model", "parts": ["समझ गया। मैं तैयार हूँ और आपकी सहायता करने के लिए उत्सुक हूँ।"]}
        ]

    # Add user message
    parts = [user_message]
    if image_path:
        # Upload and analyze image with Gemini
        image = genai.upload_file(image_path)
        parts.append(image)  # Multimodal input

    conversations[user_wa_id].append({"role": "user", "parts": parts})

    # Start chat with history
    chat = model.start_chat(history=conversations[user_wa_id])
    response = chat.send_message(parts if image_path else user_message)
    bot_reply = response.text.strip()

    # Add bot reply to history
    conversations[user_wa_id].append({"role": "model", "parts": [bot_reply]})

    return bot_reply

# Handler for text messages
@wa.on_message(filters.text)
def handle_text_message(client: WhatsApp, msg: Message):
    user_wa_id = msg.from_user.wa_id
    user_text = msg.text

    print(f"Received text from {user_wa_id}: {user_text}")

    bot_response = get_gemini_reply(user_wa_id, user_text)
    msg.reply_text(bot_response)

    print(f"Sent to {user_wa_id}: {bot_response[:70]}...")

# Handler for media messages (e.g., photos for proof)
@wa.on_message(filters.image)
def handle_media_message(client: WhatsApp, msg: MediaMessage):

    if not msg.media.image:
        msg.reply_text("माफ़ करें, मैं अभी केवल तस्वीरें ही स्वीकार कर सकता हूँ।")
        return

    user_wa_id = msg.from_user.wa_id
    print(f"Received image from {user_wa_id}")

    # Download image
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
        response = requests.get(
            msg.media.url,
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        )
        tmp_file.write(response.content)
        image_path = tmp_file.name

    analysis_message = "ग्राहक ने यह तस्वीर भेजी है, कृपया जांच करें और उचित उत्तर दें।"
    bot_response = get_gemini_reply(user_wa_id, analysis_message, image_path)

    os.unlink(image_path)

    msg.reply_text(bot_response)
    print(f"Sent analysis to {user_wa_id}")

# Server startup
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
