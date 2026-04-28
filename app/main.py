import base64
import hashlib
import hmac
import json
from datetime import datetime, date
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

from app.config import settings
from app.database import init_db, save_food_log, get_today_logs, delete_latest_log, update_latest_calories
from app.line_client import get_message_content, reply_text
from app.vision_estimator import estimate_food_from_image


app = FastAPI(title="PlateSense LINE Bot")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "service": "platesense-line-bot"}


def verify_line_signature(body: bytes, signature: str | None) -> None:
    if not signature:
        raise HTTPException(status_code=400, detail="Missing LINE signature")

    digest = hmac.new(
        settings.line_channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid LINE signature")


@app.post("/line/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: str | None = Header(default=None),
) -> dict[str, str]:
    body = await request.body()
    verify_line_signature(body, x_line_signature)

    payload: dict[str, Any] = json.loads(body.decode("utf-8"))
    events = payload.get("events", [])

    for event in events:
        if event.get("type") != "message":
            continue

        reply_token = event.get("replyToken")
        user_id = event.get("source", {}).get("userId", "unknown")
        message = event.get("message", {})
        message_type = message.get("type")

        if message_type == "image":
            message_id = message["id"]
            image_bytes = await get_message_content(message_id)
            result = await estimate_food_from_image(image_bytes)

            save_food_log(
                line_user_id=user_id,
                dish_name=result.get("dish_name", "unknown"),
                calories_mid=int(result["total"]["calories_mid"]),
                calories_low=int(result["total"]["calories_low"]),
                calories_high=int(result["total"]["calories_high"]),
                protein_g=float(result["total"].get("protein_g", 0)),
                carbs_g=float(result["total"].get("carbs_g", 0)),
                fat_g=float(result["total"].get("fat_g", 0)),
                confidence=float(result["total"].get("confidence", 0)),
                raw_json=json.dumps(result, ensure_ascii=False),
            )

            await reply_text(reply_token, format_food_reply(result))

        elif message_type == "text":
            text = (message.get("text") or "").strip()
            response = handle_text_command(user_id, text)
            await reply_text(reply_token, response)

    return {"status": "ok"}


def handle_text_command(user_id: str, text: str) -> str:
    if text == "/today":
        logs = get_today_logs(user_id)
        if not logs:
            return "วันนี้ยังไม่มีรายการอาหารครับ ส่งรูปอาหารมาได้เลย 🍽️"

        total_cal = sum(log.calories_mid for log in logs)
        total_protein = sum(log.protein_g for log in logs)
        total_carbs = sum(log.carbs_g for log in logs)
        total_fat = sum(log.fat_g for log in logs)

        lines = [
            "สรุปวันนี้ครับ 📊",
            f"กินไปแล้ว: {total_cal:,} kcal",
            f"โปรตีน: {total_protein:.0f}g",
            f"คาร์บ: {total_carbs:.0f}g",
            f"ไขมัน: {total_fat:.0f}g",
            "",
            "รายการล่าสุด:",
        ]
        for log in logs[-5:]:
            lines.append(f"- {log.dish_name}: {log.calories_mid} kcal")

        return "\n".join(lines)

    if text == "ลบล่าสุด":
        ok = delete_latest_log(user_id)
        return "ลบรายการล่าสุดให้แล้วครับ" if ok else "ยังไม่มีรายการให้ลบครับ"

    if text.startswith("แก้ล่าสุด"):
        # Example: แก้ล่าสุด 750
        parts = text.split()
        if len(parts) >= 2 and parts[1].isdigit():
            new_cal = int(parts[1])
            ok = update_latest_calories(user_id, new_cal)
            return f"แก้แคลรายการล่าสุดเป็น {new_cal} kcal แล้วครับ" if ok else "ยังไม่มีรายการให้แก้ครับ"
        return "พิมพ์แบบนี้ครับ: แก้ล่าสุด 750"

    return (
        "ส่งรูปอาหารมาได้เลยครับ 🍽️\n"
        "คำสั่งที่ใช้ได้:\n"
        "/today\n"
        "ลบล่าสุด\n"
        "แก้ล่าสุด 750"
    )


def format_food_reply(result: dict[str, Any]) -> str:
    total = result["total"]
    components = result.get("components", [])

    lines = [
        f"ผมเห็นเป็น: {result.get('dish_name', 'อาหารจานนี้')} 🍽️",
        "",
        "แยกส่วนประกอบที่เห็น:",
    ]

    for c in components[:6]:
        name = c.get("thai_name") or c.get("name") or "ส่วนประกอบ"
        weight = c.get("estimated_weight_g")
        count = c.get("count")
        cal = c.get("calories")
        count_text = f"{count:g} ชิ้น/ฟอง, " if isinstance(count, (int, float)) and count > 0 else ""
        weight_text = f"{weight:g}g, " if isinstance(weight, (int, float)) and weight > 0 else ""
        lines.append(f"- {name}: {count_text}{weight_text}≈ {cal} kcal")

    lines.extend([
        "",
        f"รวมประมาณ: {int(total['calories_low'])}-{int(total['calories_high'])} kcal",
        f"ค่ากลางที่บันทึก: {int(total['calories_mid'])} kcal",
        f"Macro: P {total.get('protein_g', 0):.0f}g / C {total.get('carbs_g', 0):.0f}g / F {total.get('fat_g', 0):.0f}g",
        f"ความมั่นใจ: {int(total.get('confidence', 0) * 100)}%",
        "",
        "ถ้าผิด พิมพ์แก้ได้ เช่น: แก้ล่าสุด 750 หรือ ลบล่าสุด",
    ])

    questions = result.get("correction_questions") or []
    if questions:
        lines.append("")
        lines.append(f"คำถามเดียวที่ช่วยให้แม่นขึ้น: {questions[0]}")

    return "\n".join(lines)
