import streamlit as st
import requests
import os

st.set_page_config(page_title="ElevenLabs Transcription Test", page_icon="🎙️")

st.title("🎙️ ElevenLabs 转写测试")
st.markdown("""
这个应用将测试 `litellm-bridge` 的转写效果，验证是否已成功过滤背景声标记 `(clap)` 和语气词。
""")

# 配置参数
API_BASE = "http://docker.home:8046/v1/audio/transcriptions"
API_KEY = "local-noauth"
MODEL = "elevenlabs-transcription"

# 音频输入方式：录音或上传
st.subheader("1. 录制或上传音频")
audio_file = st.audio_input("点击下方麦克风开始录音")

# 如果没有录音，提供上传选项
if not audio_file:
    uploaded_file = st.file_uploader("或者上传音频文件", type=["mp3", "wav", "m4a"])
    if uploaded_file:
        audio_file = uploaded_file

if audio_file:
    st.audio(audio_file)

    if st.button("🚀 开始转写", type="primary"):
        with st.spinner("正在转写并进行文本清洗..."):
            try:
                # 准备音频数据
                if not hasattr(audio_file, "name") or not audio_file.name:
                    filename = "test_audio.wav"
                else:
                    filename = audio_file.name

                # Use raw requests to avoid OpenAI SDK adding unsupported params
                headers = {"Authorization": f"Bearer {API_KEY}"}
                files = {
                    'file': (filename, audio_file.getvalue(), 'audio/wav'),
                }
                data = {
                    'model': MODEL,
                }

                response = requests.post(API_BASE, headers=headers, files=files, data=data)

                if response.status_code == 200:
                    st.success("转写完成！")
                    result = response.json()
                    st.subheader("2. 识别结果")
                    st.info(result.get("text", ""))

                    # 提示用户检查
                    st.warning("💡 请检查文本中是否还包含 '(clap)', '(laugh)' 或 '嗯', '啊' 等语气词。")
                else:
                    st.error(f"转写失败: {response.status_code} - {response.text}")

            except Exception as e:
                st.error(f"请求发生异常: {str(e)}")

st.sidebar.markdown("### 配置信息")
st.sidebar.text(f"Endpoint: {API_BASE}")
st.sidebar.text(f"Model: {MODEL}")
