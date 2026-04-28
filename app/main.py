import base64
import hashlib
import hmac
import json
import re
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

from app.config import settings
from app.database import (
    init_db,
    save_food_log,
    get_today_logs,
    delete_latest_log,
    update_latest_calories,
)
from app.line_client import get_message_content, reply_text, push_text
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

        if not reply_token:
            continue

        if message_type == "image":
            await handle_image_message(reply_token, user_id, message)

        elif message_type == "text":
            text = (message.get("text") or "").strip()
            response = handle_text_command(user_id, text)
            await reply_text(reply_token, response)

    return {"status": "ok"}


async def handle_image_message(reply_token: str, user_id: str, message: dict[str, Any]) -> None:
    """
    ตอบรับรูปทันทีด้วย reply token แล้วค่อย push ผลวิเคราะห์กลับไป
    เพราะการวิเคราะห์รูปอาจใช้เวลานาน และ reply token ใช้ได้ครั้งเดียว
    """
    await reply_text(reply_token, "ได้รับรูปแล้วครับ กำลังวิเคราะห์อาหารให้สักครู่ 🍽️")

    try:
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

        await push_text(user_id, format_food_reply(result))

    except Exception as exc:
        print(f"[ERROR] image analysis failed: {exc}")
        await push_text(
            user_id,
            "ขออภัยครับ วิเคราะห์รูปนี้ไม่สำเร็จ 😅\n"
            "ลองส่งรูปใหม่ที่เห็นอาหารชัดขึ้น หรือถ่ายจากมุมบนอีกครั้งได้ครับ"
        )


def handle_text_command(user_id: str, text: str) -> str:
    normalized = text.strip()

    if normalized == "/today":
        return format_today_summary(user_id)

    if normalized == "ลบล่าสุด":
        ok = delete_latest_log(user_id)
        return "ลบรายการล่าสุดให้แล้วครับ" if ok else "ยังไม่มีรายการให้ลบครับ"

    # รองรับ "แก้ล่าสุด 800"
    if normalized.startswith("แก้ล่าสุด"):
        new_cal = extract_first_number(normalized)
        if new_cal is not None:
            ok = update_latest_calories(user_id, new_cal)
            return (
                f"แก้แคลรายการล่าสุดเป็น {new_cal} kcal แล้วครับ"
                if ok
                else "ยังไม่มีรายการให้แก้ครับ"
            )
        return "พิมพ์แบบนี้ครับ: แก้ล่าสุด 800"

    # รองรับการพิมพ์ตัวเลขล้วน เช่น "800"
    if re.fullmatch(r"\d{2,5}", normalized):
        new_cal = int(normalized)
        ok = update_latest_calories(user_id, new_cal)
        return (
            f"รับทราบครับ แก้รายการล่าสุดเป็น {new_cal} kcal แล้ว"
            if ok
            else "ยังไม่มีรายการให้แก้ครับ ส่งรูปอาหารมาก่อน แล้วค่อยพิมพ์ตัวเลขแคลได้ครับ"
        )

    return (
        "ส่งรูปอาหารมาได้เลยครับ 🍽️\n"
        "คำสั่งที่ใช้ได้:\n"
        "/today\n"
        "แก้ล่าสุด 800 หรือพิมพ์ 800 เฉย ๆ\n"
        "ลบล่าสุด"
    )


def extract_first_number(text: str) -> int | None:
    match = re.search(r"\d{2,5}", text)
    if not match:
        return None
    return int(match.group(0))


def format_today_summary(user_id: str) -> str:
    logs = get_today_logs(user_id)
    if not logs:
        return "วันนี้ยังไม่มีรายการอาหารครับ\nส่งรูปอาหารมาได้เลย 🍽️"

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


def guess_unit(component_name: str) -> str:
    name = component_name.lower()

    if "ไข่" in name:
        return "ฟอง"
    if (
        "น้ำอัดลม" in name
        or "เครื่องดื่ม" in name
        or "ชานม" in name
        or "กาแฟ" in name
        or "น้ำหวาน" in name
        or "โค้ก" in name
        or "โคล่า" in name
    ):
        return "แก้ว"
    if "เฟรนช์ฟรายส์" in name or "ไก่ป๊อป" in name or "นักเก็ต" in name:
        return "กล่อง"
    if "ซูชิ" in name:
        return "คำ"
    if "ชีส" in name:
        return "แผ่น"
    if "เบอร์เกอร์" in name:
        return "ชิ้น"
    if (
        "เกี๊ยว" in name
        or "ลูกชิ้น" in name
        or "กุ้ง" in name
        or "ไก่ทอด" in name
        or "หมูแดง" in name
        or "หมูสไลซ์" in name
        or "หมูกรอบ" in name
        or "ไก่ย่าง" in name
        or "หมูปิ้ง" in name
    ):
        return "ชิ้น"
    if (
        "ข้าว" in name
        or "เส้น" in name
        or "บะหมี่" in name
        or "น้ำมัน" in name
        or "ซอส" in name
        or "ผัก" in name
        or "ต้นหอม" in name
        or "น้ำซุป" in name
    ):
        return ""

    return "ชิ้น"


def should_show_count(component_name: str, count: Any) -> bool:
    if not isinstance(count, (int, float)):
        return False
    if count <= 0:
        return False

    name = component_name.lower()

    # อย่าแสดง count กับของที่เป็นมวลรวม/น้ำหนักรวม ไม่ใช่ของนับชิ้น
    no_count_keywords = [
        "ข้าว",
        "เส้น",
        "บะหมี่",
        "น้ำมัน",
        "ซอส",
        "ผัก",
        "ต้นหอม",
        "กระเทียม",
        "น้ำซุป",
        "ครีม",
        "น้ำตาล",
        "หมูสับ",
        "เนื้อบด",
        "ไก่สับ",
    ]

    if any(k in name for k in no_count_keywords):
        return False

    return True


def format_count_and_weight(c: dict[str, Any]) -> str:
    name = c.get("thai_name") or c.get("name") or ""
    count = c.get("count")
    weight = c.get("estimated_weight_g")
    parts: list[str] = []

    if should_show_count(name, count):
        unit = guess_unit(name)

        # กรณีไข่ต้ม/ไข่ยางมะตูม 1 ฟองผ่าครึ่ง
        if "ไข่" in name and "ผ่าครึ่ง" in name:
            parts.append("1 ฟองผ่าครึ่ง")
        elif unit:
            parts.append(f"{count:g} {unit}")

    if isinstance(weight, (int, float)) and weight > 0:
        parts.append(f"{weight:g}g")

    if not parts:
        return ""

    return ", ".join(parts) + ", "


def format_food_reply(result: dict[str, Any]) -> str:
    total = result["total"]
    components = result.get("components", [])

    lines = [
        f"ผมเห็นเป็น: {result.get('dish_name', 'อาหารจานนี้')} 🍽️",
        "",
        "แยกส่วนประกอบที่เห็น:",
    ]

    for c in components[:8]:
        name = c.get("thai_name") or c.get("name") or "ส่วนประกอบ"
        cal = c.get("calories", 0)
        prefix = format_count_and_weight(c)
        lines.append(f"- {name}: {prefix}≈ {float(cal):.0f} kcal")

    lines.extend([
        "",
        f"รวมประมาณ: {int(total['calories_low'])}-{int(total['calories_high'])} kcal",
        f"ค่ากลางที่บันทึก: {int(total['calories_mid'])} kcal",
        f"Macro: P {total.get('protein_g', 0):.0f}g / C {total.get('carbs_g', 0):.0f}g / F {total.get('fat_g', 0):.0f}g",
        f"ความมั่นใจ: {int(total.get('confidence', 0) * 100)}%",
        "",
        "ถ้าผิด พิมพ์แก้ได้ เช่น: แก้ล่าสุด 800 หรือพิมพ์ 800 เฉย ๆ",
    ])

    questions = result.get("correction_questions") or []
    if questions:
        lines.append("")
        lines.append(f"คำถามเดียวที่ช่วยให้แม่นขึ้น: {questions[0]}")

    return "\n".join(lines)
