"""Исключения слоя инференса."""


class ModelAsleepError(Exception):
    """Локальная модель недоступна: сервер не запущен или не отвечает."""

    user_message = "Модель ещё просыпается, подожди минутку 🤍"

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(self.user_message)


class LlmResponseError(Exception):
    """Модель ответила, но ответ нельзя разобрать как ожидаемую структуру."""

    user_message = "Не получилось аккуратно разобрать ответ. Попробуй ещё раз чуть позже."

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(self.user_message)
