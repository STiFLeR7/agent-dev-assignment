import json
import base64
import requests
from typing import List, Dict, Any, Optional
from pathlib import Path

from ..config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_API_URL

class GeminiClient:
    
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or GEMINI_MODEL
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required. Set it in .env file or pass directly.")
        
        self.base_url = f"{GEMINI_API_URL}/{self.model}"
    
    def generate_content(
        self,
        prompt: str,
        images: Optional[List[str]] = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> str:
        
        url = f"{self.base_url}:generateContent?key={self.api_key}"
        
        parts = []
        
        if images:
            for img_base64 in images:
                parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": img_base64
                    }
                })
        
        parts.append({"text": prompt})
        
        payload = {
            "contents": [
                {
                    "parts": parts
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": 0.95,
                "topK": 40,
            },
            "safetySettings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_NONE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_NONE"
                }
            ]
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        
        if response.status_code != 200:
            error_detail = response.text
            raise Exception(f"Gemini API error ({response.status_code}): {error_detail}")
        
        result = response.json()
        
        try:
            candidates = result.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            
            if "promptFeedback" in result:
                feedback = result["promptFeedback"]
                if feedback.get("blockReason"):
                    raise Exception(f"Content blocked: {feedback.get('blockReason')}")
            
            raise Exception("No content in response")
            
        except (KeyError, IndexError) as e:
            raise Exception(f"Failed to parse Gemini response: {e}")
    
    def extract_invoice_data(
        self,
        images: List[str],
        extraction_prompt: str,
    ) -> Dict[str, Any]:
        
        response_text = self.generate_content(
            prompt=extraction_prompt,
            images=images,
            temperature=0.1,
            max_tokens=8192,
        )
        
        return self._extract_json(response_text)
    
    def _extract_json(self, content: str) -> Dict[str, Any]:
        
        content = content.strip()
        
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        
        if content.endswith("```"):
            content = content[:-3]
        
        content = content.strip()
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            
            if start_idx != -1 and end_idx != -1:
                json_str = content[start_idx:end_idx + 1]
                return json.loads(json_str)
            
            raise Exception(f"Failed to parse JSON from response: {e}")

def test_gemini_connection() -> bool:
    
    try:
        client = GeminiClient()
        response = client.generate_content("Say 'Hello' in one word.")
        return "hello" in response.lower()
    except Exception as e:
        print(f"Gemini connection test failed: {e}")
        return False
