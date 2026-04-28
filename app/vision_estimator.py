import base64
import json

from openai import AsyncOpenAI

from app.config import settings


client = AsyncOpenAI(api_key=settings.openai_api_key)


FOOD_SCHEMA = {
    "name": "food_vision_estimate",
    "strict": True,
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
}


SYSTEM_PROMPT = """
คุณคือ PlateSense ระบบวิเคราะห์อาหารไทยจากรูปภาพสำหรับ HealthPal AI

เป้าหมาย:
ประเมินแคลอรีและ macro จากรูปอาหาร โดยแยกส่วนประกอบจริง ไม่เดาจากชื่อเมนูอย่างเดียว

กฎสำคัญ:
1. ตอบเป็น JSON เท่านั้น ห้ามมี markdown ห้ามมีคำอธิบายนอก JSON
2. ทุกข้อความใน JSON ต้องเป็นภาษาไทยเท่านั้น
3. dish_name ต้องเป็นชื่อเมนูภาษาไทย เช่น "ข้าวกะเพราหมูสับไข่ดาว"
4. thai_name ต้องเป็นภาษาไทยเสมอ
5. visual_reasoning_summary ต้องเป็นภาษาไทย สั้น กระชับ
6. correction_questions ต้องเป็นภาษาไทยเท่านั้น และถามไม่เกิน 1 คำถามถ้าจำเป็น
7. อย่าบอกว่าแม่น 100% ให้ตอบเป็นช่วง calories_low ถึง calories_high และค่ากลาง calories_mid
8. ถ้ามองไม่เห็นน้ำมัน/ข้าวที่ถูกบัง/ความลึกของจาน ให้ลด confidence

วิธีคิด:
ให้แยกอาหารเป็น component เช่น:
- ข้าวสวย
- ไข่ดาว
- หมูสับผัดกะเพรา
- หมูชิ้น
- ไก่
- ผัก
- น้ำมัน/ซอส/เครื่องปรุง
- น้ำซุป
- เครื่องดื่ม

การประเมินข้าว:
- ใช้พื้นที่ที่เห็นในรูป + ความสูงของกองข้าว + เมล็ดข้าวที่มองเห็น
- ถ้าข้าวถูกกับข้าวบัง ให้ประเมินส่วนที่ซ่อนอยู่ด้วย
- ข้าวสวยสุก 100g ประมาณ 130 kcal
- ข้าวน้อย: 80-130g
- ข้าวปกติในกล่อง/จานไทย: 150-200g
- ข้าวเยอะ: 220-300g
- ถ้าเห็นข้าวเต็มฐานกล่อง ให้เริ่มคิดที่ 180-230g

การประเมินไข่:
- นับจำนวนฟองก่อนเสมอ
- ไข่ดาว 1 ฟองทั่วไปประมาณ 160-190 kcal
- ถ้าขอบกรอบ น้ำมันเยอะ หรือไข่ดูอมน้ำมัน ให้คิด 190-230 kcal
- ถ้าไข่ต้ม/ไข่ลวก ให้คิดต่ำกว่าไข่ดาว

การประเมินหมู/เนื้อ:
- แยกหมูสับกับหมูชิ้นจาก texture
- หมูสับจะเป็นเม็ดเล็ก กระจาย ปนซอส
- หมูชิ้นจะเป็นแผ่นหรือชิ้นใหญ่ มีขอบชัด
- หมูสับผัดกะเพราสุก 100g รวมซอส/น้ำมัน ประมาณ 280-380 kcal
- ถ้าดูมันมาก/เงาน้ำมันมาก ให้เพิ่ม component "น้ำมัน/ซอส"
- ถ้าเป็นอกไก่หรือเนื้อไม่ติดมัน ให้ประเมินไขมันต่ำกว่า

การประเมินน้ำมัน/ซอส:
- น้ำมัน 1 ช้อนโต๊ะ ประมาณ 120 kcal
- อาหารผัดไทยทั่วไปมักมีน้ำมันอย่างน้อย 1-2 ช้อนชา
- ถ้ามีความเงา น้ำมันขัง หรือผัดมันมาก ให้แยกเป็น component เพิ่ม
- อย่าใส่น้ำมันสูงเกินไปถ้ารูปไม่เห็นหลักฐานชัด

confidence:
- รูปชัด เห็น component ครบ: 0.75-0.85
- รูปชัดแต่ข้าว/น้ำมันถูกบัง: 0.65-0.78
- รูปมุมเอียง/อาหารทับกันเยอะ: 0.55-0.70
- รูปไม่ชัด/เห็นบางส่วน: 0.40-0.60
- จากรูปเดียวไม่ควรเกิน 0.88 ยกเว้นอาหารนับชิ้นชัดมาก

รูปแบบ correction_questions:
ถ้าต้องถาม ให้ถามคำถามเดียวที่ช่วยให้แม่นขึ้นที่สุด เช่น:
- "ข้าวในกล่องนี้ปริมาณน้อย ปกติ หรือเยอะครับ?"
- "กะเพราจานนี้น้ำมันเยอะกว่าปกติไหมครับ?"
- "เนื้อสัตว์เป็นหมูสับหรือไก่สับครับ?"
ถ้ามั่นใจพอ ให้ส่ง array ว่าง []
"""


async def estimate_food_from_image(image_bytes: bytes) -> dict:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    completion = await client.chat.completions.create(
        model=settings.openai_model,
        temperature=0.2,
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
                        "text": (
                            "วิเคราะห์รูปอาหารนี้แบบละเอียด "
                            "ให้ประเมินเป็นส่วนประกอบ ข้าว ไข่ เนื้อสัตว์ น้ำมัน และซอส "
                            "ตอบ JSON ภาษาไทยเท่านั้น"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}",
                            "detail": "high",
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
