"""Исключения слоя инференса."""


class ModelAsleepError(Exception):
    """Локальная модель недоступна: сервер не запущен или не отвечает."""

    user_message = "Сейчас не получается ответить. Напиши ещё раз, когда будет минутка 🤍"

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(self.user_message)


class LlmResponseError(Exception):
    """Модель ответила, но ответ нельзя разобрать как ожидаемую структуру."""

    user_message = "Не получилось аккуратно разобрать ответ. Попробуй ещё раз чуть позже."

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(self.user_message)


class EmptyArchiveError(Exception):
    """Идеи и сводки без текстов автора — это угадайка, не редакция."""

    user_message = (
        "Я ещё не читала твои тексты — без них это будет угадайка. "
        "Вставь несколько своих постов, и я сразу подхвачу голос 🤍"
    )

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(self.user_message)
