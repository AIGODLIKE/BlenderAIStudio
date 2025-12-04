"""
Gemini（又称 Nano Banana 和 Nano Banana Pro）
https://ai.google.dev/gemini-api/docs/image-generation?hl=zh-cn
curl -s -X POST \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent" \
  -H "x-goog-api-key: $GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{
      "parts": [
        {"text": "Create a picture of a nano banana dish in a fancy restaurant with a Gemini theme"}
      ]
    }]
  }' \
  | grep -o '"data": "[^"]*"' \
  | cut -d'"' -f4 \
  | base64 --decode > gemini-native-icons.png
"""
import os

api_key = os.environ.get('GEMINI_API_KEY', '').strip()

if __name__ == "__main__":
    print("api_key", api_key)
