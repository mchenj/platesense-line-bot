from datetime import datetime, date

from sqlalchemy import create_engine, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.config import settings


engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


class FoodLog(Base):
    __tablename__ = "food_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    line_user_id: Mapped[str] = mapped_column(String(128), index=True)
    dish_name: Mapped[str] = mapped_column(String(255))
    calories_mid: Mapped[int] = mapped_column(Integer)
    calories_low: Mapped[int] = mapped_column(Integer)
    calories_high: Mapped[int] = mapped_column(Integer)
    protein_g: Mapped[float] = mapped_column(Float)
    carbs_g: Mapped[float] = mapped_column(Float)
    fat_g: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    raw_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


def init_db() -> None:
    Base.metadata.create_all(engine)


def save_food_log(
    line_user_id: str,
    dish_name: str,
    calories_mid: int,
    calories_low: int,
    calories_high: int,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    confidence: float,
    raw_json: str,
) -> FoodLog:
    with Session(engine) as session:
        log = FoodLog(
            line_user_id=line_user_id,
            dish_name=dish_name,
            calories_mid=calories_mid,
            calories_low=calories_low,
            calories_high=calories_high,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
            confidence=confidence,
            raw_json=raw_json,
        )
        session.add(log)
        session.commit()
        session.refresh(log)
        return log


def get_today_logs(line_user_id: str) -> list[FoodLog]:
    today = date.today()
    start = datetime.combine(today, datetime.min.time())
    end = datetime.combine(today, datetime.max.time())

    with Session(engine) as session:
        return list(
            session.query(FoodLog)
            .filter(FoodLog.line_user_id == line_user_id)
            .filter(FoodLog.created_at >= start)
            .filter(FoodLog.created_at <= end)
            .order_by(FoodLog.created_at.asc())
            .all()
        )


def delete_latest_log(line_user_id: str) -> bool:
    with Session(engine) as session:
        log = (
            session.query(FoodLog)
            .filter(FoodLog.line_user_id == line_user_id)
            .order_by(FoodLog.created_at.desc())
            .first()
        )
        if not log:
            return False
        session.delete(log)
        session.commit()
        return True


def update_latest_calories(line_user_id: str, calories_mid: int) -> bool:
    with Session(engine) as session:
        log = (
            session.query(FoodLog)
            .filter(FoodLog.line_user_id == line_user_id)
            .order_by(FoodLog.created_at.desc())
            .first()
        )
        if not log:
            return False

        ratio = calories_mid / max(log.calories_mid, 1)
        log.calories_mid = calories_mid
        log.calories_low = int(calories_mid * 0.9)
        log.calories_high = int(calories_mid * 1.1)
        log.protein_g = log.protein_g * ratio
        log.carbs_g = log.carbs_g * ratio
        log.fat_g = log.fat_g * ratio

        session.commit()
        return True
