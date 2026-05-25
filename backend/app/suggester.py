from fastapi import APIRouter
from pydantic import BaseModel
import httpx
import re

router = APIRouter()

class SuggestRequest(BaseModel):
    text: str
    endpoint: str = "http://host.docker.internal:5001/v1"
    prompt_mode: str = "danbooru_tags"

class SuggestResponse(BaseModel):
    suggestions: list[str]
    source: str

# Robust deterministic tag suggestion library for offline and instant fallback
SUGGESTION_LIBRARY = {
    "girl": ["1girl", "beautiful eyes", "detailed face", "solo", "gorgeous", "cute"],
    "woman": ["1woman", "mature", "elegant", "solo", "gorgeous", "photorealistic"],
    "boy": ["1boy", "handsome", "detailed face", "solo", "cool", "athletic"],
    "man": ["1man", "mature", "rugged", "solo", "handsome", "bearded"],
    "cyberpunk": ["cyberpunk city", "neon lights", "volumetric lighting", "unreal engine 5", "futuristic", "cybernetic implants"],
    "cinematic": ["cinematic lighting", "moody atmosphere", "depth of field", "bokeh", "photorealistic", "dramatic shadows"],
    "anime": ["anime style", "key visual", "cel shaded", "vibrant colors", "digital art", "studio ghibli"],
    "photo": ["photorealistic", "raw photo", "hyperrealistic", "8k resolution", "sharp focus", "canon eos r5", "national geographic"],
    "portrait": ["portrait photography", "studio lighting", "close up", "shallow depth of field", "sharp focus", "detailed face"],
    "landscape": ["scenic landscape", "majestic mountains", "beautiful lighting", "volumetric clouds", "wide angle", "golden hour"],
    "fantasy": ["concept art", "mythical", "glowing runes", "unreal engine render", "ethereal", "vibrant color scheme"],
    "space": ["nebula", "stars", "sci-fi", "cosmic dust", "planets", "deep space photography"],
    "lighting": ["rim lighting", "volumetric lighting", "god rays", "soft studio lighting", "neon glow", "dramatic lighting"]
}

DEFAULT_SUGGESTIONS = [
    "masterpiece",
    "highly detailed",
    "sharp focus",
    "8k resolution",
    "artstation trending",
    "gorgeous composition"
]

@router.post("/suggest", response_model=SuggestResponse)
async def get_suggestions(req: SuggestRequest):
    text_clean = req.text.strip().lower()
    if not text_clean:
        return SuggestResponse(suggestions=DEFAULT_SUGGESTIONS[:5], source="default")

    # Extract last typed keyword to offer smart contextual autocomplete
    words = re.findall(r"\w+", text_clean)
    last_word = words[-1] if words else ""

    # Attempt Local LLM suggestion first if endpoint looks active
    try:
        # Build prompt asking local KoboldCpp or Ollama to suggest style continuation
        llm_prompt = (
            f"Given the Stable Diffusion prompt-in-progress: '{req.text}'. "
            f"Suggest exactly 5 highly suitable aesthetic style tags, descriptive tokens, or synonyms. "
            f"Output ONLY as a comma-separated list of those 5 tags, with absolutely no other text or explanation."
        )
        
        async with httpx.AsyncClient(timeout=1.5) as client:
            # We support standard OpenAI completion style or simple generation
            payload = {
                "prompt": llm_prompt,
                "max_tokens": 30,
                "temperature": 0.6,
                "stop": ["\n"]
            }
            # Try to post to completion endpoint
            response = await client.post(f"{req.endpoint}/completions", json=payload)
            if response.status_code == 200:
                data = response.json()
                text_out = data["choices"][0]["text"].strip()
                # Sanitize output commas
                tags = [t.strip() for t in text_out.split(",") if t.strip()]
                if len(tags) >= 3:
                    return SuggestResponse(suggestions=tags[:5], source="local_llm")
    except Exception:
        # LLM failed or timed out — proceed cleanly to dictionary fallback
        pass

    # Check contextual mapping library
    matched_tags = []
    for key, suggestions in SUGGESTION_LIBRARY.items():
        if key in text_clean or (last_word and key.startswith(last_word)):
            matched_tags.extend(suggestions)

    # De-duplicate matches while retaining order
    unique_matches = []
    for tag in matched_tags:
        if tag not in unique_matches and tag.lower() != last_word:
            unique_matches.append(tag)

    if len(unique_matches) >= 3:
        return SuggestResponse(suggestions=unique_matches[:5], source="fallback_library")

    # Final backup default suggestion set
    return SuggestResponse(suggestions=DEFAULT_SUGGESTIONS[:5], source="default")
