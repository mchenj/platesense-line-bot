from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    line_channel_secret: str = Field(alias="LINE_CHANNEL_SECRET")
    line_channel_access_token: str = Field(alias="LINE_CHANNEL_ACCESS_TOKEN")
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    database_url: str = Field(default="sqlite:///./platesense.db", alias="DATABASE_URL")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
