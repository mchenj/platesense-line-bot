import base64
import json

from openai import AsyncOpenAI

from app.config import settings


client = AsyncOpenAI(api_key=settings.openai_api_key)


FOOD_SCHEMA = {
    "name": "food_vision_estimate",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "dish_name": {"type": "string"},
            "visual_reasoning_summary": {"type": "string"},
            "components": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "thai_name": {"type": "string"},
                        "count": {"type": ["number", "null"]},
                        "area_percent": {"type": ["number", "null"]},
                        "height_estimate": {"type": ["string", "null"]},
                        "texture_clues": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "estimated_weight_g": {"type": "number"},
                        "calories": {"type": "number"},
                        "protein_g": {"type": "number"},
                        "carbs_g": {"type": "number"},
                        "fat_g": {"type": "number"},
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "name",
                        "thai_name",
                        "count",
                        "area_percent",
                        "height_estimate",
                        "texture_clues",
                        "estimated_weight_g",
                        "calories",
                        "protein_g",
                        "carbs_g",
                        "fat_g",
                        "confidence",
                    ],
                },
            },
            "total": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "calories_mid": {"type": "number"},
                    "calories_low": {"type": "number"},
                    "calories_high": {"type": "number"},
                    "protein_g": {"type": "number"},
                    "carbs_g": {"type": "number"},
                    "fat_g": {"type": "number"},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "calories_mid",
                    "calories_low",
                    "calories_high",
                    "protein_g",
                    "carbs_g",
                    "fat_g",
                    "confidence",
                ],
            },
            "correction_questions": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": [
            "dish_name",
            "visual_reasoning_summary",
            "components",
            "total",
            "correction_questions",
        ],
    },
    "strict": True,
}


SYSTEM_PROMPT = """
You are PlateSense, a Thai food vision estimator.

Goal:
Estimate calories and macros from a food photo by component, not by dish name alone.

Rules:
1. Think in components: rice, egg, meat, vegetables, oil, sauce, soup, snacks, drink.
2. Count countable items: fried eggs, boiled eggs, shrimp, meatballs, sausages, chicken wings, skewers.
3. For rice, estimate visible area, mound height, and grams. Use visual texture and rice grain scale when visible.
4. For meat, distinguish minced pork, sliced pork, chicken, crispy pork, fish, shrimp, tofu when possible.
5. Include hidden oil/sauce as a component when relevant.
6. Return a range and midpoint. Never pretend exact precision.
7. Confidence must be 0.0-1.0.
8. If the image is unclear, still make the best estimate and include one correction question.
9. Thai food defaults:
   - cooked white rice 100g is about 130 kcal
   - fried egg 1 egg is about 160-190 kcal depending on oil
   - stir-fried minced pork basil 100g cooked mixture is about 280-380 kcal depending on oil/fat
10. Output valid JSON only.
"""


async def estimate_food_from_image(image_bytes: bytes) -> dict:
    """Estimate Thai food nutrition from an image using Chat Completions vision.

    This version intentionally uses client.chat.completions.create()
    instead of client.responses.create() because the pinned OpenAI SDK
    in requirements.txt may not include the newer Responses API client.
    """
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    completion = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Analyze this food image and estimate nutrition by visible components.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        },
                    },
                ],
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": FOOD_SCHEMA,
        },
    )

    text = completion.choices[0].message.content
    return json.loads(text)
