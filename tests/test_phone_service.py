"""Phone engine adapter — catalog, parsing, mapping and scan driver.

The network is never touched: module functions are stubbed and the mapping
test uses phonsint's real Result factories.
"""

from __future__ import annotations

import asyncio
import sys
import types

import pytest

from services import phone_service as ps


def test_catalog_comes_from_the_engine():
    names = ps.catalog_names()
    assert names, "phonsint catalog is empty — dependency missing?"
    assert len(set(names)) == len(names)
    assert ps.catalog_categories()
    # Every catalog entry is one (category, module) pair.
    assert len(ps.load_catalog()) == len(names)


def test_supported_regions_are_not_hardcoded():
    regions = ps.supported_regions()
    assert "NG" in regions and "US" in regions
    assert len(regions) > 200


def test_validate_and_normalize_e164_and_local():
    assert ps.validate_phone("+14155552671")
    assert ps.normalize_phone("+14155552671") == "+14155552671"
    assert ps.validate_phone("08012345678", "NG")
    assert ps.normalize_phone("08012345678", "NG") == "+2348012345678"
    assert not ps.validate_phone("not-a-number")


def test_result_mapping_keeps_extra_and_media():
    from phonsint.core.parser import parse_phone_number
    from phonsint.core.result import Result

    info = parse_phone_number("+14155552671")
    result = Result.taken(
        url="https://example.com",
        extra={"email": "j***e@gmail.com", "name": "Jane"},
        media={"avatar": "https://cdn.example/a.jpg"},
    )
    row = ps._map_result("Social", "Facebook", result, info)
    assert row.exists is True
    assert row.extra["email"].startswith("j")
    assert row.media["avatar"].startswith("https://")
    assert row.phone == "+14155552671"
    assert row.category == "Social"


def _stub_module(name: str, taken: bool):
    module = types.ModuleType(name)

    async def _validate(value):
        from phonsint.core.result import Result

        return Result.taken(url=f"https://{name}.example") if taken else Result.available()

    _validate.__name__ = f"validate_{name}"
    setattr(module, f"validate_{name}", _validate)
    return module


def test_search_streams_buckets_and_filters(monkeypatch):
    entries = [
        ("Social", _stub_module("alpha", True)),
        ("Shopping", _stub_module("beta", False)),
    ]
    monkeypatch.setattr(ps, "load_catalog", lambda: list(entries))
    service = ps.PhoneService()

    progress = asyncio.run(
        service.search("+14155552671", concurrency=2, timeout=5)
    )
    assert progress.total_modules == 2
    assert progress.checked_modules == 2
    assert [r.name for r in progress.found] == ["Alpha"]
    assert [r.name for r in progress.not_found] == ["Beta"]
    assert progress.phone == "+14155552671"

    # Category filter limits the scan and the denominator.
    filtered = asyncio.run(
        service.search("+14155552671", categories=["Social"], concurrency=2, timeout=5)
    )
    assert filtered.total_modules == 1
    assert filtered.checked_modules == 1
    assert [r.name for r in filtered.found] == ["Alpha"]

    # Module filter uses the live site names.
    by_name = asyncio.run(
        service.search("+14155552671", modules=["Beta"], concurrency=2, timeout=5)
    )
    assert by_name.total_modules == 1
    assert [r.name for r in by_name.not_found] == ["Beta"]


def test_loud_modules_are_skipped(monkeypatch):
    """Silent-operation guard: an upstream loud module must never run."""
    from phonsint.core import helpers

    entries = [
        ("Social", _stub_module("alpha", True)),
        ("Social", _stub_module("beta", True)),
    ]
    monkeypatch.setattr(ps, "load_catalog", lambda: list(entries))
    monkeypatch.setattr(helpers, "LOUD_MODULES", ["beta"])

    progress = asyncio.run(
        ps.PhoneService().search("+14155552671", concurrency=2, timeout=5)
    )
    assert [r.name for r in progress.found] == ["Alpha"]
    skipped = [r for r in progress.unavailable if r.name == "Beta"]
    assert skipped and skipped[0].reason == "skipped (loud)"
    assert progress.checked_modules == 2


def test_total_modules_property():
    service = ps.PhoneService()
    assert service.total_modules == len(ps.load_catalog())


@pytest.mark.skipif(sys.platform == "emscripten", reason="worker threads unavailable")
def test_search_cancel_marks_progress_cancelled():
    async def _go():
        service = ps.PhoneService()

        async def _slow(_v):
            await asyncio.sleep(5)
            from phonsint.core.result import Result

            return Result.taken()

        module = types.ModuleType("phone_slow")
        slow_fn = _slow
        slow_fn.__name__ = "validate_slow"
        module.validate_slow = slow_fn
        entries = [("Social", module)]

        import services.phone_service as mod

        original = mod.load_catalog
        mod.load_catalog = lambda: entries
        try:
            task = asyncio.create_task(service.search("+14155552671", timeout=1))
            await asyncio.sleep(0.2)
            service.cancel()
            progress = await task
        finally:
            mod.load_catalog = original
        assert progress.is_cancelled is True or progress.checked_modules == 0

    asyncio.run(_go())
