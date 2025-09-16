import os
import base64
import threading
import json
from flask import Flask, render_template, request, Response
from openai import OpenAI
import logging

# ------------------- 1. 统一配置区 -------------------
# 填入硅基流动apikey
API_KEY = os.getenv("SILICONFLOW_API_KEY", "sk-xxxxx")

# 1. 对话代理模型 (扮演纳西妲，可自由更换为您喜欢的对话模型)
CONVERSATIONAL_AGENT_MODEL = "deepseek-ai/DeepSeek-V3.1"

# 2. 提示词工程师模型 (负责生成高质量英文绘画指令，推荐使用擅长复杂指令遵循的模型)
PROMPT_ENGINEER_MODEL = "moonshotai/Kimi-K2-Instruct-0905" # 强烈推荐Kimi，它对复杂指令的遵循效果经过验证

# 3. 其他模型
IMAGE_MODEL_NAME = "Qwen/Qwen-Image"
TTS_MODEL_NAME = "FunAudioLLM/CosyVoice2-0.5B"

#注意额度消耗，硅基的qwen image是0.3元一张图，但由于其赠费机制实际成本远低于此

# --- AI角色与指令设定 ---
NAHIDA_SYSTEM_PROMPT = "你现在是《原神》中的角色纳西妲。请你以纳西妲的身份和知识库进行回答。你的回答应该符合她的性格：充满智慧、略带一丝孩子气的好奇心、温柔而又坚定。请在对话中自然地融入你的身份，例如使用'我'来指代自己。用户是原神世界中的旅行者，对话需要保持自然对话的长度，不宜过长,不要用括号补充不是说话内容的背景信息。"

# System prompt for the secondary LLM agent, tasked with engineering image prompts.
PROMPT_ENGINEER_SYSTEM_PROMPT = """You are an AI Prompt Virtuoso, an expert director for Genshin Impact art. Your goal is to create a perfectly structured prompt pair (POSITIVE and NEGATIVE) that ensures flawless, multi-character composition.

**Your Professional Workflow:**

**Step 1: Analyze the Conversation** to identify mood, setting, key objects, and all **explicitly named Genshin Impact characters.**

**Step 2: Construct the POSITIVE Prompt.**
* **A. Foundation (Style & Quality):** Always start with: `masterpiece, best quality, ultra-detailed, official art, genshin impact, anime key visual, cinematic lighting`.
* **B. Dynamic Character Composition (THE ULTIMATE RULE):**
    * **If only Nahida is present:** Use the 'Identity Block' `1girl, solo, nahida (genshin impact), long white hair, green eyes, elf-like ears`.
    * **If another character IS mentioned (e.g., Furina):**
        1.  You **MUST** use a compositional tag like `2girls` and **REMOVE** the `solo` tag.
        2.  You **MUST** describe each character in a separate block, divided by the `BREAK` keyword.
        3.  Describe their relative positions (e.g., foreground, background).
        4.  For EACH character, use their full 'Identity Block' (trigger word + physical features).
    * **Your Knowledge Base:**
        * **Nahida:** `nahida (genshin impact), long white hair, green eyes, elf-like ears`
        * **Furina:** `furina (genshin impact), heterochromia, blue eye, grey eye, long white hair with blue accents, signature blue and white dress and hat`
        * **Zhongli:** `zhongli (genshin impact), amber eyes, long dark brown hair with amber tips, formal liyue attire`
* **C. Director's Toolkit:** Add specific choices for camera (`wide shot`, etc.), lighting (`golden hour`, etc.), and atmosphere (`glowing particles`, etc.).

**Step 3: Construct the NEGATIVE Prompt (CRITICAL for Accuracy).**
* **A. Universal Quality Negatives:** Always start with: `(worst quality, low quality:1.4), blurry, ugly, jpeg artifacts, signature, watermark, text, username, error`.
* **B. Dynamic Character Feature Correction:**
    * For **EVERY** character present, add negatives to prevent feature blending.
    * **If Nahida is present, add:** `dark hair, black hair, brown hair, blonde hair, yellow hair, horns, old, lumine (genshin impact)`.
    * **If Furina is present, add:** `uniform eye color, green eyes, single-colored hair`.
    * **IMPORTANT:** Do not add a negative tag if it's a required feature for another character in the same image (e.g., if Nahida and Lumine are together, don't add `blonde hair` to the negative prompt).

**Step 4: Final Output Format (EXTREMELY STRICT).**
* Your output **MUST** be in two parts, separated by `[NEGATIVE]`.

**Example of a Perfect MULTI-CHARACTER Output:**
masterpiece, best quality, official art, genshin impact, anime key visual, cinematic lighting, 2girls, nahida (genshin impact), long white hair, green eyes, elf-like ears, sitting on a picnic blanket in the foreground, smiling and holding a leaf, (wide shot:1.2)
BREAK
furina (genshin impact), long white hair with blue accents, heterochromia, standing gracefully in the background, dancing with a gentle expression, surrounded by glowing water droplets
[NEGATIVE]
(worst quality, low quality:1.4), blurry, ugly, jpeg artifacts, signature, watermark, text, username, error, dark hair, black hair, brown hair, blonde hair, yellow hair, horns, old, uniform eye color
"""
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REFERENCE_AUDIO_PATH = os.path.join(BASE_DIR, "Ref_audio.mp3") 
TEXT_IN_REFERENCE_AUDIO = "初次见面，我已经关注你很久了。我叫纳西妲，别看我像个孩子，我比任何一位大人都了解这个世界。所以，我可以用我的知识，换取你路上的见闻吗？" 
MAX_TOKENS = 2048
TEMPERATURE = 0.7
# ------------------- 2. Flask 应用实现 -------------------
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
client = OpenAI(api_key=API_KEY, base_url="https://api.siliconflow.cn/v1")

def encode_audio_to_base64(file_path):
    try:
        with open(file_path, "rb") as f: return f"data:audio/mpeg;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    except Exception as e:
        app.logger.error(f"Error encoding audio: {e}")
        return None

REFERENCE_AUDIO_BASE_64 = encode_audio_to_base64(REFERENCE_AUDIO_PATH)
if not REFERENCE_AUDIO_BASE_64: exit("致命错误: 无法加载参考音频")

@app.route('/')
def index(): return render_template('index.html')

def task_generate_image_and_prompt(user_message, nahida_reply, result_container):
    try:
        prompt_engineer_input = f"User: \"{user_message}\"\nNahida: \"{nahida_reply}\""
        messages_for_prompt = [{"role": "system", "content": PROMPT_ENGINEER_SYSTEM_PROMPT}, {"role": "user", "content": prompt_engineer_input}]
        
        prompt_response = client.chat.completions.create(
            model=PROMPT_ENGINEER_MODEL, messages=messages_for_prompt, max_tokens=300, temperature=0.5)
        
        full_prompt_string = prompt_response.choices[0].message.content.strip()

        positive_prompt = full_prompt_string
        negative_prompt = ""
        if "[NEGATIVE]" in full_prompt_string:
            parts = full_prompt_string.split("[NEGATIVE]", 1)
            positive_prompt = parts[0].strip()
            negative_prompt = parts[1].strip()

        app.logger.info(f"🎨 Positive Prompt: {positive_prompt}")
        app.logger.info(f"🚫 Negative Prompt: {negative_prompt}")

        if not positive_prompt:
            result_container['image_url'] = None
            return

        image_response = client.images.generate(
            model=IMAGE_MODEL_NAME, 
            prompt=positive_prompt, 
            n=1, 
            extra_body={
                "image_size": "928x1664",
                "negative_prompt": negative_prompt
            }
        )
        result_container['image_url'] = image_response.data[0].url if image_response.data else None
    except Exception as e:
        app.logger.error(f"Error in image generation thread: {e}")
        result_container['image_url'] = None

def task_generate_speech(nahida_reply, result_container):
    try:
        if not nahida_reply:
            result_container['audio_base64'] = None
            return
        speech_response = client.audio.speech.create(
            model=TTS_MODEL_NAME, input=nahida_reply, voice="", response_format="mp3",
            extra_body={"references": [{"audio": REFERENCE_AUDIO_BASE_64, "text": TEXT_IN_REFERENCE_AUDIO}]})
        audio_content = speech_response.content
        result_container['audio_base64'] = base64.b64encode(audio_content).decode('utf-8')
    except Exception as e:
        app.logger.error(f"Error in speech generation thread: {e}")
        result_container['audio_base64'] = None

def sanitize_history_for_api(history):
    sanitized_history = []
    for message in history:
        role = message.get('role')
        content = message.get('content')
        text_content = ""
        
        if role == 'user' and isinstance(content, str):
            text_content = content
        elif role == 'assistant' and isinstance(content, dict):
            text_content = content.get('text', '')
            
        if text_content:
            sanitized_history.append({'role': role, 'content': text_content})
    return sanitized_history

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message')
    conversation_history = data.get('history', [])

    def event_stream():
        try:
            sanitized_history = sanitize_history_for_api(conversation_history)
            
            messages_for_nahida = [{"role": "system", "content": NAHIDA_SYSTEM_PROMPT}] + sanitized_history
            messages_for_nahida.append({"role": "user", "content": user_message})
            
            chat_response = client.chat.completions.create(
                model=CONVERSATIONAL_AGENT_MODEL, 
                messages=messages_for_nahida, 
                max_tokens=MAX_TOKENS, 
                temperature=TEMPERATURE
            )
            nahida_full_reply = chat_response.choices[0].message.content.strip()

            if not nahida_full_reply:
                raise ValueError("The chat model returned an empty response.")

            results = {}
            speech_thread = threading.Thread(target=task_generate_speech, args=(nahida_full_reply, results))
            image_thread = threading.Thread(target=task_generate_image_and_prompt, args=(user_message, nahida_full_reply, results))
            speech_thread.start()
            image_thread.start()
            
            speech_thread.join()
            yield f"data: {json.dumps({'type': 'content_start', 'text': nahida_full_reply, 'audio': results.get('audio_base64')})}\n\n"

            image_thread.join()
            if results.get('image_url'):
                yield f"data: {json.dumps({'type': 'image', 'payload': results.get('image_url')})}\n\n"
            
            yield f"data: {json.dumps({'type': 'done', 'full_response': nahida_full_reply})}\n\n"
            
        except Exception as e:
            app.logger.error(f"An error occurred in the event stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            
    return Response(event_stream(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.logger.info("应用启动中...")
    app.logger.info(f"请在浏览器中打开 http://127.0.0.1:1027") # 10.27 is nahida's birthday~
    app.run(host='0.0.0.0', port=1027, debug=False)
