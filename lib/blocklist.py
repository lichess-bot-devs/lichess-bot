"""Code related to blocklists."""
from dataclasses import dataclass
import requests
import logging

logger = logging.getLogger(__name__)


@dataclass
class BlocklistData:
    users: list[str]
    etag: str | None


def _parse_block_list_from_url(url: str, old_data: BlocklistData) -> BlocklistData:
    headers =  {"If-None-Match": old_data.etag} if old_data.etag else {}
    response = requests.get(url, headers=headers)

    response.raise_for_status()

    if response.status_code == 304:
        return old_data

    block_list = [username.strip() for username in response.text.strip().split("\n")]

    return BlocklistData(block_list, response.headers.get("ETag"))


class OnlineBlocklist:
    """Manage online blocklists."""

    def __init__(self, urls: list[str]) -> None:
        """Initialize the OnlineBlockList class."""
        self.blocklist: dict[str, BlocklistData] = {url : BlocklistData([], None) for url in urls}
        for _ in range(5):
            self.refresh()

    def refresh(self) -> None:
        """Pull updated blocklists from the list of blocklist urls."""
        logger.info(f"Refreshing {len(self.blocklist)} online blocklists")

        for url, data in self.blocklist.items():
            try:
                self.blocklist[url] = _parse_block_list_from_url(url, data)
            except Exception:
                logger.warning(f"Failed to refresh online blocklist {url}")

    def __contains__(self, item: str) -> bool:
        """Check if an username is in the blocklist."""
        return any(item in blocklist.users for blocklist in self.blocklist.values())
