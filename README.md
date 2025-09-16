# chat with nahida~

一个基于 Flask 和 SiliconFlow API 构建的多模态AI聊天应用。你只需要有一个硅基流动的apikey，就可以与扮纳西妲进行实时的、带有个性化语音和场景图片生成的连续对话。

## ✨ 功能特性

- **实时语音对话**: 集成文本生成（LLM）和语音合成（TTS），实现流畅的语音交流。
- **智能场景绘画**: AI会根据对话内容，智能生成符合情境的图片，丰富对话体验。
- **角色扮演** : 通过精心设计的系统提示词，让AI的行为和语言风格高度符合“纳西妲”的角色设定。
- **多线程并行处理**: 后端采用多线程技术，并行处理语音和图片生成，有效降低响应延迟。
- **历史会话管理**: 所有对话都保存在浏览器本地，支持随时加载、删除和开始新对话。
- **美观的Web界面**: 仿照主流AI对话应用设计的现代化、响应式聊天界面。

## 🖼️ 界面预览

![应用主界面](screenshots/1.png)
*<p align="center">同时也会听到纳西妲的声音哦~</p>*

## 🛠️ 技术栈

- **后端**: Python, Flask
- **AI模型 API**: 硅基流动 (SiliconFlow)
  - 对话: `moonshotai/Kimi-K2-Instruct-0905`, `deepseek-ai/DeepSeek-V3.1`
  - 绘画: `Qwen/Qwen-Image`
  - 语音: `FunAudioLLM/CosyVoice2-0.5B`
- **前端**: HTML, CSS, JavaScript 
- **核心库**: `openai`, `python-dotenv`

## 🚀 安装与运行

1. **克隆仓库**

   ```bash
   git clone https://github.com/Oceannn233/chat-with-nahida.git
   cd  x\your_path\chat-with-nahida-main
   ```

2. **安装依赖**

   ```bash
   pip install -r requirements.txt
   ```

3. **配置API Key**

   - 在 `app.py` 文件中填入您从 SiliconFlow 获取的 API Key：

     ```
     SILICONFLOW_API_KEY="sk-xxxxxxxxxx"
     ```

4. **准备静态资源**（纳西妲的已经放好，如果你想要修改为其他角色可用）

   - 将您的语音克隆参考音频放入项目根目录 (例如 `Ref_audio.mp3`)。
   - 将UI所需的图片 (`nahi_icon.jpeg`, `nahi_background.png`, `user_icon.png`) 放入 `static` 文件夹。

5. **运行应用**

   ```bash
   python app.py
   ```

   然后在浏览器中打开 `http://127.0.0.1:1027`。

   

> *“迷宫的更深处到底有什么，我也很好奇呢。嗯，我知道，继续深入的话肯定会遇到更棘手的怪物，甚至还会遭遇挫败。但经历了雨水的捶打后，林间的树苗反而会变得更茁壮一些。为了看到树冠以上的天空，我们也加油吧？”*
>
> ​                                                                                                                                                                                                                                                   *——纳西妲*
