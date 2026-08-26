"""Конфигурация приложения из переменных окружения."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Настройки «Тихой редакции». Все секреты живут в .env, не в интерфейсе."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_host: str = "127.0.0.1"
    app_port: int = 8080
    app_title: str = "Тихая редакция"

    brain_base_url: str = "http://127.0.0.1:8000/v1"
    brain_model: str = "qwen-27b"
    brain_gguf_path: Path = Path(r"C:\models\qwen3.8-27b-q4_k_m.gguf")
    llama_server_path: Path = Path(r"C:\llama.cpp\llama-server.exe")

    eyes_base_url: str = "http://127.0.0.1:8001/v1"
    eyes_model: str = "gemma-12b"
    eyes_gguf_path: Path = Path(r"C:\models\gemma4-12b-q5_k_m.gguf")
    eyes_mmproj_path: Path = Path(r"C:\models\gemma4-12b-mmproj.gguf")

    vk_token: str = ""
    vk_owner_id: str = ""
    # Пользовательский ключ админа: wall.get / комментарии / загрузка фото на стену.
    # Ключ сообщества (vk_token) умеет ЛС, но не читает стену.
    vk_wall_token: str = ""

    telegram_bot_token: str = ""

    database_path: Path = Field(default=Path("data/app.db"))
    chroma_path: Path = Field(default=Path("data/chroma"))
    uploads_path: Path = Field(default=Path("data/uploads"))

    llm_timeout: float = 900.0
    vision_timeout: float = 900.0

    @property
    def database_url(self) -> str:
        """Асинхронный URL SQLite."""
        db_path = self.resolve_path(self.database_path)
        return f"sqlite+aiosqlite:///{db_path.as_posix()}"

    def resolve_path(self, path: Path) -> Path:
        """Превращает относительный путь в абсолютный от корня проекта."""
        if path.is_absolute():
            return path
        return (ROOT_DIR / path).resolve()

    def ensure_directories(self) -> None:
        """Создаёт каталоги данных и логов, если их ещё нет."""
        for path in (
            self.resolve_path(self.database_path).parent,
            self.resolve_path(self.chroma_path),
            self.resolve_path(self.uploads_path),
            ROOT_DIR / "logs",
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек."""
    settings = Settings()
    settings.ensure_directories()
    return settings
