from google import genai
from google.genai import types
from PIL import Image
from io import BytesIO
import base64
import os

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

contents = ('Hi, can you create a 3d rendered image of a pig '
            'with wings and a top hat flying over a happy '
            'futuristic scifi city with lots of greenery?')

response = client.models.generate_content(
    model="gemini-2.0-flash-preview-image-generation",
    contents=contents,
    config=types.GenerateContentConfig(
      response_modalities=['TEXT', 'IMAGE']
    )
)

for part in response.candidates[0].content.parts:
  if part.text is not None:
    print(part.text)
  elif part.inline_data is not None:
    image_bytes = base64.b64decode(part.inline_data.data)
    image = Image.open(BytesIO(image_bytes))
    image.save('generate/gemini-native-image.png')
    image.show()