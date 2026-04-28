import httpx
from app.config import settings


LINE_CONTENT_ENDPOINT = "https://api-data.line.me/v2/bot/message/{message_id}/content"
LINE_REPLY_ENDPOINT = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_ENDPOINT = "https://api.line.me/v2/bot/message/push"


async def get_message_content(message_id: str) -> bytes:
    url = LINE_CONTENT_ENDPOINT.format(message_id=message_id)
    headers = {"Authorization": f"Bearer {settings.line_channel_access_token}"}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.content


async def reply_text(reply_token: str, text: str) -> None:
    headers = {
        "Authorization": f"Bearer {settings.line_channel_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text[:4900]}],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(LINE_REPLY_ENDPOINT, headers=headers, json=payload)
        response.raise_for_status()


async def push_text(user_id: str, text: str) -> None:
    """
    ส่งข้อความแบบ push กลับไปหาผู้ใช้ หลังจาก reply token ถูกใช้ไปแล้ว
    ใช้สำหรับเคสวิเคราะห์รูปที่ใช้เวลานาน:
    1) reply_text แจ้งว่าได้รับรูปแล้ว
    2) วิเคราะห์รูป
    3) push_text ส่งผลวิเคราะห์กลับไป
    """
    headers = {
        "Authorization": f"Bearer {settings.line_channel_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text[:4900]}],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(LINE_PUSH_ENDPOINT, headers=headers, json=payload)
        response.raise_for_status()
