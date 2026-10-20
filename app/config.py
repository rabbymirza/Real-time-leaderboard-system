from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./leaderboard.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60


settings = Settings( admin_token="rOUAFtFZE-pa-OEd2YqVhOYe35f_k-DvSQTgEtO5J0U")


