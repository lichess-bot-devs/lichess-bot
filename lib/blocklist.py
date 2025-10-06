"""Code related to blocklists."""
import requests
import logging

logger = logging.getLogger(__name__)


def _parse_block_list_from_url(url: str) -> list[str]:
    block_list = requests.get(url).text.strip()
    return [username.strip() for username in block_list.split("\n")]


class OnlineBlocklist:
    """Manage online blocklists."""

    def __init__(self, urls: list[str]) -> None:
        """Initialize the OnlineBlockList class."""
        self.urls = urls
        self.blocklist: list[str] = []
        self.refresh()

    def refresh(self) -> None:
        """Pull updated blocklists from the list of blocklist urls."""
        if len(self.urls) == 0:
            self.blocklist = []
            return

        blocklist: list[str] = []
        logger.info(f"Refreshing {len(self.urls)} online blocklists")

        try:
            for url in self.urls:
                blocklist.extend(_parse_block_list_from_url(url))
        except Exception:
            logger.warning("Failed to refresh online blocklists")
            return

        self.blocklist = blocklist

    def __contains__(self, item: str) -> bool:
        """Check if an username is in the blocklist."""
        return item in self.blocklist
