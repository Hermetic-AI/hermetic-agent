"""network_check 模块单测."""

from __future__ import annotations

import pytest

from hermetic_agent.policy.network_check import is_url_allowed


def test_network_off_blocks_all() -> None:
    allowed, reason = is_url_allowed("https://api.openai.com", "off")
    assert allowed is False
    assert "off" in reason


def test_network_off_blocks_local_too() -> None:
    """off 档连 local 都不放过."""
    allowed, _ = is_url_allowed("http://127.0.0.1:8080", "off")
    assert allowed is False


def test_network_local_blocks_public_ip() -> None:
    allowed, reason = is_url_allowed("https://api.openai.com", "local")
    assert allowed is False
    assert "local" in reason or "private" in reason


def test_network_local_allows_10_8() -> None:
    allowed, _ = is_url_allowed("http://10.0.0.1:8080/api", "local")
    assert allowed is True


def test_network_local_allows_172_16() -> None:
    allowed, _ = is_url_allowed("http://172.16.0.1:8080", "local")
    assert allowed is True


def test_network_local_allows_192_168() -> None:
    allowed, _ = is_url_allowed("http://192.168.1.1:8080", "local")
    assert allowed is True


def test_network_local_allows_127() -> None:
    allowed, _ = is_url_allowed("http://127.0.0.1:3000", "local")
    assert allowed is True


def test_network_local_allows_localhost() -> None:
    allowed, _ = is_url_allowed("http://localhost:5000", "local")
    assert allowed is True


def test_network_local_allows_ipv6_loopback() -> None:
    allowed, _ = is_url_allowed("http://[::1]:8080", "local")
    assert allowed is True


def test_network_local_allows_ipv6_unique_local() -> None:
    allowed, _ = is_url_allowed("http://[fc00::1]:8080", "local")
    assert allowed is True


def test_network_local_allows_ipv6_link_local() -> None:
    allowed, _ = is_url_allowed("http://[fe80::1]:8080", "local")
    assert allowed is True


def test_network_any_allows_everything() -> None:
    allowed, _ = is_url_allowed("https://api.openai.com", "any")
    assert allowed is True
    allowed, _ = is_url_allowed("https://8.8.8.8", "any")
    assert allowed is True


def test_network_empty_url() -> None:
    allowed, _ = is_url_allowed("", "any")
    assert allowed is False


def test_network_invalid_url() -> None:
    allowed, _ = is_url_allowed("not-a-url", "any")
    assert allowed is False


def test_network_unknown_level() -> None:
    allowed, _ = is_url_allowed("https://example.com", "weird")
    assert allowed is False
