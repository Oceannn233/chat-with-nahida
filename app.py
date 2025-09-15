import os
import base64
import threading
import json
from flask import Flask, render_template, request, Response
from openai import OpenAI
import logging

# 填入硅基流动apikey
API_KEY = os.getenv("SILICONFLOW_API_KEY", "sk-xxxx")

# 1. 对话代理模型 (扮演纳西妲，可自由更换为您喜欢的对话模型)
CONVERSATIONAL_AGENT_MODEL = "deepseek-ai/DeepSeek-V3.1"

# 2. 提示词工程师模型 (负责生成高质量英文绘画指令，推荐使用擅长复杂指令遵循的模型)
PROMPT_ENGINEER_MODEL = "zai-org/GLM-4.5"

# 3. 其他模型
IMAGE_MODEL_NAME = "Qwen/Qwen-Image"
TTS_MODEL_NAME = "FunAudioLLM/CosyVoice2-0.5B" 

##运行app.py后，打开终端中的端口即可，默认"http://127.0.0.1:1027"

#  --- AI角色与指令设定 ---
NAHIDA_SYSTEM_PROMPT = "你现在是《原神》中的角色纳西妲。请你以纳西妲的身份和知识库进行回答。你的回答应该符合她的性格：充满智慧、略带一丝孩子气的好奇心、温柔而又坚定。请在对话中自然地融入你的身份，例如使用'我'来指代自己。用户是原神世界中的旅行者，对话需要保持自然对话的长度，不宜过长,不要用括号补充不是说话内容的背景信息。"
PROMPT_ENGINEER_SYSTEM_PROMPT = """You are an elite-level AI Art Director, with a deep understanding of cinematography, composition, and the visual aesthetics of Genshin Impact. Your goal is to transform a simple conversation into a breathtaking, masterpiece-level image prompt.

**Core Mandate: Nahida is the anchor of every scene.** She must be present in every image, either as the main focus or as an observer connecting the viewer to the subject.

Follow this professional workflow:

**1. Foundation (Style & Quality):**
* Always begin the prompt with a powerful quality and style block: `masterpiece, best quality, ultra-detailed, official art, Genshin Impact art style, anime key visual, cinematic lighting, beautiful detailed sky, intricate details`.

**2. Scene Composition (The Storytelling Core):**
* **Nahida's Presence:** Always include `Nahida, a small girl with long white hair and elf-like ears, wearing her green and white dress`. Describe her expression and posture based on the conversation's mood (e.g., `a gentle smile`, `a thoughtful expression`, `curiously touching a glowing flower`).
* **Character Interaction:** If another Genshin Impact character (e.g., Traveler, Zhongli, Klee) is mentioned, they **MUST appear alongside Nahida**. You must describe their interaction or spatial relationship.
    * *Good Example:* `Nahida is floating beside the tall and stoic Zhongli, listening intently as he points towards Guyun Stone Forest.`
    * *Bad Example:* `Zhongli stands in Liyue.`
* **Scene-Focused Shots:** If the conversation is about a location or object, compose the shot with Nahida interacting with or observing that element.
    * *Good Example:* `Nahida is gently touching the glowing Irminsul tree in a vast, mystical library.`
    * *Bad Example:* `A picture of a tree.`

**3. The Director's Toolkit (Mandatory Artistic Elements):**
* To ensure each image is unique and dynamic, you **MUST** incorporate specific directorial choices into the prompt. Combine these elements naturally.
* **Camera & Shot:** Choose a suitable shot type and angle. Examples: `(wide shot:1.2)`, `(full body shot)`, `cowboy shot`, `(medium shot)`, `close-up`, `from above`, `from below`, `dramatic angle`.
* **Lighting:** Describe the lighting to create a mood. Examples: `golden hour lighting`, `volumetric god rays filtering through leaves`, `soft rim lighting`, `moonlight`.
* **Atmosphere & Details:** Add dynamic and magical elements. Examples: `glowing particles`, `floating petals`, `dynamic motion blur on the background`, `beautifully detailed environment`, `depth of field`.

**4. Final Output Format (Strict):**
* Your output **MUST** be a single, cohesive paragraph of English text.
* **DO NOT** use bullet points, labels, or any explanations. Combine all chosen elements into one powerful prompt.
""" 
REFERENCE_AUDIO_PATH = "Ref_audio.mp3"
TEXT_IN_REFERENCE_AUDIO = "初次见面，我已经关注你很久了。我叫纳西妲，别看我像个孩子，我比任何一位大人都了解这个世界。所以，我可以用我的知识，换取你路上的见闻吗？" # (内容不变，为节省空间省略)
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
        
        # 提示词工程师模型
        prompt_response = client.chat.completions.create(
            model=PROMPT_ENGINEER_MODEL, 
            messages=messages_for_prompt, 
            max_tokens=200, 
            temperature=0.5
        )
        image_prompt = prompt_response.choices[0].message.content.strip()
        app.logger.info(f"🎨 Generated Image Prompt: {image_prompt}")

        if not image_prompt:
            result_container['image_url'] = None
            return
            
        image_response = client.images.generate(model=IMAGE_MODEL_NAME, prompt=image_prompt, n=1, extra_body={"image_size": "928x1664"})
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

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message')
    conversation_history = data.get('history', [])

    def event_stream():
        try:
            sanitized_history = [msg for msg in conversation_history if isinstance(msg.get('content'), str)]
            messages_for_nahida = [{"role": "system", "content": NAHIDA_SYSTEM_PROMPT}] + sanitized_history
            messages_for_nahida.append({"role": "user", "content": user_message})
            
            app.logger.info("--- [DEBUG] Preparing to call CHAT model (Nahida) ---")
            app.logger.info(f"Model: {CONVERSATIONAL_AGENT_MODEL}")
            
            # 对话代理模型
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
    app.logger.info(f"请在浏览器中打开 http://127.0.0.1:1027") # nahida's birthday~
    app.run(host='0.0.0.0', port=1027, debug=False)