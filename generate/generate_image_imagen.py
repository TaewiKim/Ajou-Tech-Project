from google import genai
from google.genai import types
from PIL import Image
from io import BytesIO
import base64
import os

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

response = client.models.generate_images(
    model='imagen-4.0-generate-preview-06-06',
    prompt='Robot holding a red skateboard',
    config=types.GenerateImagesConfig(
        number_of_images= 1,
    )
)
print(response)
for generated_image in response.generated_images:
    raw_bytes = generated_image.image.image_bytes

    try:
        # Attempt base64 decoding in case it's not raw PNG
        decoded_bytes = base64.b64decode(raw_bytes)
        image = Image.open(BytesIO(decoded_bytes))
    except Exception as e:
        print("Base64 decoding failed, trying raw bytes:", e)
        image = Image.open(BytesIO(raw_bytes))

    image.save('generate/robot_skateboard.png')
    image.show()
    print("Generated image saved as 'robot_skateboard.png'")
