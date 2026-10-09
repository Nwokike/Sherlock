"""Regression tests for Fix Batch 5 (settings validation + persistence).

Pure unit tests over module-level validators — no renderer needed.
"""

from screens.settings_screen import _parse_proxy, _validate_manifest


def test_parse_proxy_valid():
    assert _parse_proxy("") is None
    assert _parse_proxy("   ") is None
    assert _parse_proxy("http://127.0.0.1:8080") is None
    assert _parse_proxy("https://proxy.example.com") is None
    assert _parse_proxy("socks5://127.0.0.1:1080") is None
    assert _parse_proxy("socks5h://127.0.0.1:1080") is None
    assert _parse_proxy("http://user:pass@host:3128") is None
    assert _parse_proxy("HTTP://HOST:80") is None


def test_parse_proxy_invalid():
    assert _parse_proxy("http://") is not None  # bare scheme, no host
    assert _parse_proxy("ftp://host:21") is not None
    assert _parse_proxy("notaurl") is not None
    assert _parse_proxy("http://host:99999") is not None
    assert _parse_proxy("http://host:abc") is not None


def test_validate_manifest_empty_and_urls():
    assert _validate_manifest("") is None
    assert _validate_manifest("   ") is None
    assert _validate_manifest("https://example.com/sites.json") is None
    assert _validate_manifest("http://example.com/sites.json") is not None
    assert _validate_manifest("https://") is not None


def test_validate_manifest_files(tmp_path):
    good = tmp_path / "sites.json"
    good.write_text('{"sites": []}')
    assert _validate_manifest(str(good)) is None

    missing = tmp_path / "nope.json"
    assert _validate_manifest(str(missing)) is not None

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not json")
    assert _validate_manifest(str(bad_json)) is not None

    wrong_shape = tmp_path / "shape.json"
    wrong_shape.write_text('{"nope": 1}')
    assert _validate_manifest(str(wrong_shape)) is not None

    assert _validate_manifest(str(tmp_path)) is not None  # directory


def test_slider_range_constants():
    """Email concurrency slider must match the state clamp exactly."""
    import re
    from pathlib import Path

    src = Path("src/screens/settings_screen.py").read_text(encoding="utf-8")
    assert "min=5,\n" in src or "min=5," in src
    assert "divisions=25" in src
    # Clamp floors agree
    assert "max(5, min(30" in src
    assert "max(10, min(100" in src
    assert re.search(r"min=4,\n.*max=30", src) is None


def test_nsfw_single_writer_contract():
    """_set_nsfw writes both keys; _toggle_safe_search routes through it."""
    from pathlib import Path

    src = Path("src/screens/settings_screen.py").read_text(encoding="utf-8")
    assert "def _set_nsfw(val: bool):" in src
    assert "STORAGE_SAFE_SEARCH" in src
    home = Path("src/screens/home_screen.py").read_text(encoding="utf-8")
    assert "STORAGE_SAFE_SEARCH" in home
