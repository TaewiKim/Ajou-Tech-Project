from pathlib import Path
from openai import OpenAI
import httpx
import os

api_key = os.environ.get("OPENAI_API_KEY")
# api_key = "your_api_key_here"

class CustomHTTPClient(httpx.Client):
    def __init__(self, *args, **kwargs):
        kwargs.pop("proxies", None)  # Remove the 'proxies' argument if present
        super().__init__(*args, **kwargs)

client = OpenAI(api_key=api_key, http_client=CustomHTTPClient())

speech_file_path = Path(__file__).parent / "speech.mp3"

with client.audio.speech.with_streaming_response.create(
    model="gpt-4o-mini-tts",
    voice="coral",
    input="우리… 로또 맞은 거 같아! 번호 다 맞아! 대박!! 우리 진짜 부자 되는 거야!",
) as response:
    response.stream_to_file(speech_file_path)