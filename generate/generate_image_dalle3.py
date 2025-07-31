import httpx
from openai import OpenAI
import requests
import os

api_key = os.environ.get("OPENAI_API_KEY")
# api_key = "your_api_key_here"

class CustomHTTPClient(httpx.Client):
    def __init__(self, *args, **kwargs):
        kwargs.pop("proxies", None)  # Remove the 'proxies' argument if present
        super().__init__(*args, **kwargs)

client = OpenAI(api_key=api_key, http_client=CustomHTTPClient())

result = client.images.generate(
    model="dall-e-3",
    prompt="a white siamese cat",
    size="1024x1024"
)

# 이미지 결과 확인 및 저장
if result.data and result.data[0].url:
    image_url = result.data[0].url
    print("Revised prompt:", result.data[0].revised_prompt)
    print("Image URL:", image_url)

    response = requests.get(image_url)
    if response.status_code == 200:
        with open("white_siamese_cat.png", "wb") as f:
            f.write(response.content)
        print("이미지를 'white_siamese_cat.png'로 저장했습니다.")
    else:
        print("이미지 다운로드 실패:", response.status_code)
else:
    print("이미지 URL이 없습니다.")