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
        self.blocklist: dict[str, list[str]] = {url : [] for url in urls}
        self.refresh()

    def refresh(self) -> None:
        """Pull updated blocklists from the list of blocklist urls."""
        logger.info(f"Refreshing {len(self.blocklist)} online blocklists")

        for url in self.blocklist.keys():
            try:
                self.blocklist[url] = _parse_block_list_from_url(url)
            except Exception:
                logger.warning(f"Failed to refresh online blocklist {url}")

    def __contains__(self, item: str) -> bool:
        """Check if an username is in the blocklist."""
        return any(item in blocklist for blocklist in self.blocklist)
