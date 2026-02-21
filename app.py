"""
与纳西妲的AI语音对话 Web 应用
基于 Flask 和 SiliconFlow API 构建的多模态AI聊天应用
"""

import os
import base64
import threading
import json
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Generator
from pathlib import Path

from flask import Flask, render_template, request, Response
from openai import OpenAI
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ==================== 配置管理 ====================

@dataclass
class AppConfig:
    """应用配置类"""
    # API 配置
    api_key: str
    base_url: str = "https://api.siliconflow.cn/v1"
    
    # 模型配置
    chat_model: str = "deepseek-ai/DeepSeek-V3.1"
    prompt_engineer_model: str = "zai-org/GLM-4.5"
    image_model: str = "Qwen/Qwen-Image"
    tts_model: str = "IndexTeam/IndexTTS-2"
    
    # 生成参数
    max_tokens: int = 2048
    temperature: float = 0.7
    image_size: str = "928x1664"
    
    # 语音配置
    reference_audio_path: str = "Ref_audio.mp3"
    text_in_reference_audio: str = (
        "初次见面，我已经关注你很久了。我叫纳西妲，别看我像个孩子，"
        "我比任何一位大人都了解这个世界。所以，我可以用我的知识，换取你路上的见闻吗？"
    )
    
    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 1027
    debug: bool = False
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        """从环境变量加载配置"""
        api_key = os.getenv("SILICONFLOW_API_KEY")
        if not api_key:
            raise ValueError(
                "❌ 错误：未设置 SILICONFLOW_API_KEY 环境变量！\n"
                "请复制 .env.example 为 .env 并填入你的 API Key。\n"
                "获取地址: https://siliconflow.cn/"
            )
        
        return cls(
            api_key=api_key,
            base_url=os.getenv("SILICONFLOW_BASE_URL", cls.base_url),
            chat_model=os.getenv("CHAT_MODEL", cls.chat_model),
            prompt_engineer_model=os.getenv("PROMPT_ENGINEER_MODEL", cls.prompt_engineer_model),
            image_model=os.getenv("IMAGE_MODEL", cls.image_model),
            tts_model=os.getenv("TTS_MODEL", cls.tts_model),
            max_tokens=int(os.getenv("MAX_TOKENS", cls.max_tokens)),
            temperature=float(os.getenv("TEMPERATURE", cls.temperature)),
            reference_audio_path=os.getenv("REFERENCE_AUDIO_PATH", cls.reference_audio_path),
            text_in_reference_audio=os.getenv("TEXT_IN_REFERENCE_AUDIO", cls.text_in_reference_audio),
            host=os.getenv("HOST", cls.host),
            port=int(os.getenv("PORT", cls.port)),
            debug=os.getenv("DEBUG", "False").lower() == "true",
        )


# ==================== 系统提示词 ====================

NAHIDA_SYSTEM_PROMPT = """你现在是《原神》中的角色纳西妲。请你以纳西妲的身份和知识库进行回答。

角色特点：
- 充满智慧，对世界本质有深刻理解
- 略带一丝孩子气的好奇心
- 温柔而又坚定
- 使用"我"来指代自己
- 用户是原神世界中的旅行者

回答要求：
- 保持自然对话的长度，不宜过长
- 不要用括号补充不是说话内容的背景信息
- 语气要像朋友一样亲切自然"""

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


# ==================== 工具函数 ====================

def encode_audio_to_base64(file_path: str) -> Optional[str]:
    """将音频文件编码为 base64 数据 URI"""
    try:
        path = Path(file_path)
        if not path.exists():
            logging.error(f"❌ 参考音频文件不存在: {file_path}")
            return None
        
        with open(path, "rb") as f:
            ext = path.suffix.lower()
            mime_type = {
                ".mp3": "audio/mpeg",
                ".wav": "audio/wav",
                ".ogg": "audio/ogg",
            }.get(ext, "application/octet-stream")
            
            encoded = base64.b64encode(f.read()).decode("utf-8")
            return f"data:{mime_type};base64,{encoded}"
    except Exception as e:
        logging.error(f"❌ 编码音频文件时出错: {e}")
        return None


def create_sse_message(data: Dict[str, Any]) -> str:
    """创建 SSE 格式的消息"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ==================== AI 服务类 ====================

class AIService:
    """AI 服务管理类"""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.client = OpenAI(api_key=config.api_key, base_url=config.base_url)
        self.reference_audio_base64 = self._load_reference_audio()
    
    def _load_reference_audio(self) -> Optional[str]:
        """加载参考音频"""
        audio_base64 = encode_audio_to_base64(self.config.reference_audio_path)
        if audio_base64:
            logging.info("✅ 参考音频加载成功")
        return audio_base64
    
    def generate_chat_response(
        self, 
        user_message: str, 
        history: List[Dict[str, str]]
    ) -> str:
        """生成对话回复"""
        messages = [
            {"role": "system", "content": NAHIDA_SYSTEM_PROMPT}
        ] + [
            msg for msg in history if isinstance(msg.get("content"), str)
        ] + [
            {"role": "user", "content": user_message}
        ]
        
        logging.info(f"🤖 调用对话模型: {self.config.chat_model}")
        
        response = self.client.chat.completions.create(
            model=self.config.chat_model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        
        content = response.choices[0].message.content.strip()
        if not content:
            raise ValueError("对话模型返回了空回复")
        
        return content
    
    def generate_image_prompt(self, user_message: str, nahida_reply: str) -> Optional[str]:
        """生成图像提示词"""
        try:
            prompt_input = f'User: "{user_message}"\nNahida: "{nahida_reply}"'
            messages = [
                {"role": "system", "content": PROMPT_ENGINEER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt_input}
            ]
            
            response = self.client.chat.completions.create(
                model=self.config.prompt_engineer_model,
                messages=messages,
                max_tokens=200,
                temperature=0.5,
            )
            
            prompt = response.choices[0].message.content.strip()
            logging.info(f"🎨 生成的图像提示词: {prompt[:100]}...")
            return prompt
        except Exception as e:
            logging.error(f"❌ 生成图像提示词失败: {e}")
            return None
    
    def generate_image(self, prompt: str) -> Optional[str]:
        """生成图像"""
        try:
            response = self.client.images.generate(
                model=self.config.image_model,
                prompt=prompt,
                n=1,
                extra_body={"image_size": self.config.image_size}
            )
            return response.data[0].url if response.data else None
        except Exception as e:
            logging.error(f"❌ 生成图像失败: {e}")
            return None
    
    def generate_speech(self, text: str) -> Optional[str]:
        """生成语音"""
        try:
            if not self.reference_audio_base64:
                logging.warning("⚠️ 参考音频未加载，跳过语音生成")
                return None
            
            response = self.client.audio.speech.create(
                model=self.config.tts_model,
                input=text,
                voice="",
                response_format="mp3",
                extra_body={
                    "references": [{
                        "audio": self.reference_audio_base64,
                        "text": self.config.text_in_reference_audio
                    }]
                }
            )
            
            return base64.b64encode(response.content).decode("utf-8")
        except Exception as e:
            logging.error(f"❌ 生成语音失败: {e}")
            return None


# ==================== Flask 应用 ====================

def create_app() -> Flask:
    """创建 Flask 应用"""
    app = Flask(__name__)
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    # 加载配置
    config = AppConfig.from_env()
    ai_service = AIService(config)
    
    @app.route("/")
    def index():
        return render_template("index.html")
    
    @app.route("/chat", methods=["POST"])
    def chat():
        data = request.json
        user_message = data.get("message", "").strip()
        history = data.get("history", [])
        
        if not user_message:
            return Response(
                create_sse_message({"type": "error", "content": "消息不能为空"}),
                mimetype="text/event-stream"
            )
        
        def event_stream() -> Generator[str, None, None]:
            try:
                # 1. 生成对话回复
                nahida_reply = ai_service.generate_chat_response(user_message, history)
                
                # 2. 并行生成语音和图像
                results: Dict[str, Any] = {}
                
                def generate_speech_task():
                    results["audio_base64"] = ai_service.generate_speech(nahida_reply)
                
                def generate_image_task():
                    prompt = ai_service.generate_image_prompt(user_message, nahida_reply)
                    if prompt:
                        results["image_url"] = ai_service.generate_image(prompt)
                    else:
                        results["image_url"] = None
                
                speech_thread = threading.Thread(target=generate_speech_task)
                image_thread = threading.Thread(target=generate_image_task)
                
                speech_thread.start()
                image_thread.start()
                
                # 等待语音完成并发送
                speech_thread.join()
                yield create_sse_message({
                    "type": "content_start",
                    "text": nahida_reply,
                    "audio": results.get("audio_base64")
                })
                
                # 等待图像完成并发送
                image_thread.join()
                if results.get("image_url"):
                    yield create_sse_message({
                        "type": "image",
                        "payload": results["image_url"]
                    })
                
                # 完成
                yield create_sse_message({
                    "type": "done",
                    "full_response": nahida_reply
                })
                
            except Exception as e:
                logging.error(f"❌ 处理请求时出错: {e}")
                yield create_sse_message({
                    "type": "error",
                    "content": str(e)
                })
        
        return Response(event_stream(), mimetype="text/event-stream")
    
    return app, config


# ==================== 主入口 ====================

if __name__ == "__main__":
    app, config = create_app()
    
    logging.info("=" * 50)
    logging.info("🌱 纳西妲 AI 对话应用启动中...")
    logging.info(f"🌐 请访问: http://127.0.0.1:{config.port}")
    logging.info("=" * 50)
    
    app.run(host=config.host, port=config.port, debug=config.debug)
