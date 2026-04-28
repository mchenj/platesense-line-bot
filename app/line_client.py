import httpx
from app.config import settings


LINE_CONTENT_ENDPOINT = "https://api-data.line.me/v2/bot/message/{message_id}/content"
LINE_REPLY_ENDPOINT = "https://api.line.me/v2/bot/message/reply"


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
