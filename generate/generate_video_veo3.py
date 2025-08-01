import time
from google import genai
from google.genai import types
import os

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

prompt = """A close up of two people staring at a cryptic drawing on a wall, torchlight flickering.
A man murmurs, 'This must be it. That's the secret code.' The woman looks at him and whispering excitedly, 'What did you find?'"""

operation = client.models.generate_videos(
    model="veo-3.0-generate-preview",
    prompt=prompt,
)

# Poll the operation status until the video is ready
while not operation.done:
    print("Waiting for video generation to complete...")
    time.sleep(10)
    operation = client.operations.get(operation)

# Download the generated video
generated_video = operation.response.generated_videos[0]
client.files.download(file=generated_video.video)
generated_video.video.save("generate/dialogue_example.mp4")
print("Generated video saved to dialogue_example.mp4")