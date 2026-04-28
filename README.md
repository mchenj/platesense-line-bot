# PlateSense LINE Bot — Sprint 0

MVP: ส่งรูปอาหารเข้า LINE → AI วิเคราะห์อาหารแบบแยกส่วนประกอบ → ตอบแคล/แมคโครกลับใน LINE

## 1) เตรียมค่าใน `.env`

คัดลอกจาก `.env.example` เป็น `.env`

```bash
cp .env.example .env
```

ใส่ค่า:
- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `OPENAI_API_KEY`

## 2) ติดตั้ง

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3) รัน local

```bash
uvicorn app.main:app --reload --port 8000
```

## 4) เปิด tunnel ให้ LINE ยิง webhook ได้

ใช้ ngrok หรือ Cloudflare Tunnel เช่น:

```bash
ngrok http 8000
```

เอา URL ไปตั้งใน LINE Developers Console:

```text
https://YOUR-DOMAIN/line/webhook
```

## 5) ทดสอบ

ส่งรูปอาหารเข้า LINE OA แล้ว bot จะตอบกลับโดยประมาณแบบนี้:

```text
ผมเห็นเป็น: ข้าวกะเพราหมูสับไข่ดาว

- ข้าวสวย: 170-200g ≈ 220-260 kcal
- ไข่ดาว: 1 ฟอง ≈ 170 kcal
- หมูสับผัดกะเพรา: 80-100g ≈ 280-360 kcal

รวมประมาณ: 720-850 kcal
ค่ากลางที่บันทึก: 785 kcal
```

## คำสั่ง Text ที่รองรับใน Sprint 0

```text
/today
ลบล่าสุด
แก้ล่าสุด 750
```

## หมายเหตุความแม่นยำ

เวอร์ชันนี้เป็น “AI food scale จากภาพ” ระดับ MVP:
- ตอบเป็นช่วง + ค่ากลาง
- แสดง reasoning แบบสั้น
- ยังไม่ใช่เครื่องมือแพทย์
- ความแม่นขึ้นได้จาก correction loop ใน sprint ถัดไป
