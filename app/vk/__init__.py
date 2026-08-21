"""VK-интеграция."""

from app.vk.client import (
    VkConfirmRequiredError,
    VkMessagesUnavailableError,
    VkNotConfiguredError,
    fetch_inbox,
    import_wall_posts,
    is_configured,
    refresh_stats,
    schedule_post,
)

__all__ = [
    "VkConfirmRequiredError",
    "VkMessagesUnavailableError",
    "VkNotConfiguredError",
    "fetch_inbox",
    "import_wall_posts",
    "is_configured",
    "refresh_stats",
    "schedule_post",
]
