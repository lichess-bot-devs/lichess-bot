"""Tests for the blocklist module."""
from unittest.mock import Mock, patch

import pytest
from urllib3.exceptions import HTTPError

from lib.blocklist import BlocklistData, _parse_block_list_from_url, OnlineBlocklist


def test_parse_block_list_from_url_success() -> None:
    """Test parsing blocklist from URL with successful response."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "user1\nuser2\nuser3"
    mock_response.headers = {"ETag": "test-etag-123"}
    mock_response.raise_for_status = Mock()

    old_data = BlocklistData([], None)

    with patch("lib.blocklist.requests.get", return_value=mock_response):
        result = _parse_block_list_from_url("http://example.com/blocklist", old_data)

    assert result.users == ["user1", "user2", "user3"]
    assert result.etag == "test-etag-123"


def test_parse_block_list_from_url__several_line_breaks() -> None:
    """Test parsing blocklist from URL with several line-breaks."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {"ETag": "test-etag-123"}
    mock_response.raise_for_status = Mock()

    old_data = BlocklistData([], None)

    texts = [
        "user1\nuser2\nuser3",
        "user1\r\nuser2\r\n\r\nuser3",
        "user1\ruser2\r\ruser3",
        "user1\nuser2\nuser3",
    ]
    for text in texts:
        mock_response.text = text

        with patch("lib.blocklist.requests.get", return_value=mock_response):
            result = _parse_block_list_from_url("http://example.com/blocklist", old_data)

        assert result.users == ["user1", "user2", "user3"]
        assert result.etag == "test-etag-123"


def test_parse_block_list_from_url_not_modified() -> None:
    """Test parsing blocklist returns cached data when not modified (304)."""
    mock_response = Mock()
    mock_response.status_code = 304
    mock_response.raise_for_status = Mock()

    old_data = BlocklistData(["cached_user1", "cached_user2"], "old-etag")

    with patch("lib.blocklist.requests.get", return_value=mock_response):
        result = _parse_block_list_from_url("http://example.com/blocklist", old_data)

    assert result.users == ["cached_user1", "cached_user2"]
    assert result.etag == "old-etag"


def test_parse_block_list_from_url_with_etag_header() -> None:
    """Test that ETag is sent in request headers when available."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "user1"
    mock_response.headers = {}
    mock_response.raise_for_status = Mock()

    old_data = BlocklistData([], "existing-etag")

    with patch("lib.blocklist.requests.get", return_value=mock_response) as mock_get:
        _parse_block_list_from_url("http://example.com/blocklist", old_data)
        mock_get.assert_called_once_with(
            "http://example.com/blocklist",
            headers={"If-None-Match": "existing-etag"},
            timeout=15,
        )


def test_parse_block_list_from_url_without_etag_header() -> None:
    """Test that no ETag header is sent when old_data has no ETag."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "user1"
    mock_response.headers = {}
    mock_response.raise_for_status = Mock()

    old_data = BlocklistData([], None)

    with patch("lib.blocklist.requests.get", return_value=mock_response) as mock_get:
        _parse_block_list_from_url("http://example.com/blocklist", old_data)
        mock_get.assert_called_once_with(
            "http://example.com/blocklist",
            headers={},
            timeout=15
        )


def test_parse_block_list_from_url_strips_whitespace() -> None:
    """Test that usernames are stripped of leading/trailing whitespace."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "  user1  \n  user2\t\nuser3  "
    mock_response.headers = {}
    mock_response.raise_for_status = Mock()

    old_data = BlocklistData([], None)

    with patch("lib.blocklist.requests.get", return_value=mock_response):
        result = _parse_block_list_from_url("http://example.com/blocklist", old_data)

    assert result.users == ["user1", "user2", "user3"]


def test_parse_block_list_from_url_empty_response() -> None:
    """Test parsing blocklist with empty response."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = ""
    mock_response.headers = {}
    mock_response.raise_for_status = Mock()

    old_data = BlocklistData([], None)

    with patch("lib.blocklist.requests.get", return_value=mock_response):
        result = _parse_block_list_from_url("http://example.com/blocklist", old_data)

    assert result.users == []


def test_parse_block_list_from_url_no_etag_in_response() -> None:
    """Test parsing blocklist when response has no ETag header."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "user1\nuser2"
    mock_response.headers = {}
    mock_response.raise_for_status = Mock()

    old_data = BlocklistData([], None)

    with patch("lib.blocklist.requests.get", return_value=mock_response):
        result = _parse_block_list_from_url("http://example.com/blocklist", old_data)

    assert result.users == ["user1", "user2"]
    assert result.etag is None


def test_parse_block_list_from_url_multiline_with_blanks() -> None:
    """Test parsing blocklist that contains blank lines."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "user1\n\nuser2\n\n\nuser3"
    mock_response.headers = {}
    mock_response.raise_for_status = Mock()

    old_data = BlocklistData([], None)

    with patch("lib.blocklist.requests.get", return_value=mock_response):
        result = _parse_block_list_from_url("http://example.com/blocklist", old_data)

    assert result.users == ["user1", "user2", "user3"]


def test_parse_block_list_from_url__exception() -> None:
    """Test parsing blocklist from URL with exception."""
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = HTTPError("500 Internal Server Error")

    old_data = BlocklistData([], None)

    with patch("lib.blocklist.requests.get", return_value=mock_response), pytest.raises(HTTPError):
        _parse_block_list_from_url("http://example.com/blocklist", old_data)


def test_online_blocklist_refresh_success() -> None:
    """Test successful refresh of all blocklists."""
    mock_response1 = Mock()
    mock_response1.status_code = 200
    mock_response1.text = "user1\nuser2"
    mock_response1.headers = {"ETag": "etag1"}
    mock_response1.raise_for_status = Mock()

    mock_response2 = Mock()
    mock_response2.status_code = 200
    mock_response2.text = "user3\nuser4\nuser5"
    mock_response2.headers = {"ETag": "etag2"}
    mock_response2.raise_for_status = Mock()

    with patch("lib.blocklist.requests.get") as mock_get:
        mock_get.side_effect = [mock_response1, mock_response2]
        blocklist = OnlineBlocklist(["http://example.com/list1", "http://example.com/list2"])

    assert blocklist.blocklist["http://example.com/list1"].users == ["user1", "user2"]
    assert blocklist.blocklist["http://example.com/list1"].etag == "etag1"
    assert blocklist.blocklist["http://example.com/list2"].users == ["user3", "user4", "user5"]
    assert blocklist.blocklist["http://example.com/list2"].etag == "etag2"


def test_online_blocklist_refresh_partial_failure() -> None:
    """Test refresh when some blocklists fail to load."""
    mock_response_success = Mock()
    mock_response_success.status_code = 200
    mock_response_success.text = "user1\nuser2"
    mock_response_success.headers = {"ETag": "etag1"}
    mock_response_success.raise_for_status = Mock()

    mock_response_fail = Mock()
    mock_response_fail.raise_for_status.side_effect = HTTPError("500 Server Error")

    with patch("lib.blocklist.requests.get") as mock_get:
        # First call succeeds, second call fails
        mock_get.side_effect = [mock_response_success, mock_response_fail]
        blocklist = OnlineBlocklist(["http://example.com/list1", "http://example.com/list2"])

    # First blocklist should be loaded
    assert blocklist.blocklist["http://example.com/list1"].users == ["user1", "user2"]

    # Second blocklist should remain empty (failed to load)
    assert blocklist.blocklist["http://example.com/list2"].users == []
    assert blocklist.blocklist["http://example.com/list2"].etag is None
