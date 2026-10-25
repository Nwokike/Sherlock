"""Tolerant module loader + compat driver shape tests."""



from services import user_scanner_compat as compat


def test_load_user_modules_returns_pairs():
    mods = compat.load_user_modules()
    assert len(mods) > 2000
    cat, mod = mods[0]
    assert isinstance(cat, str)
    assert hasattr(mod, "__name__")


def test_load_email_modules_returns_pairs():
    mods = compat.load_email_modules()
    assert len(mods) > 100


def test_load_phone_modules_five_modules():
    mods = compat.load_phone_modules()
    assert len(mods) == 5
    cats = {c.lower() for c, _ in mods}
    assert cats == {"auth", "crm", "shopping", "social"}


def test_tolerant_loader_skips_broken_file(tmp_path):
    bad = tmp_path / "broken"
    good = tmp_path / "good"
    bad.mkdir()
    good.mkdir()
    (bad / "boom.py").write_text("raise RuntimeError('bad module')")
    (bad / "fine.py").write_text("def validate_fine(u):\n    return None")
    (good / "ok.py").write_text("def validate_ok(u):\n    return None")
    mods = compat._load_modules_tolerant(bad)
    assert len(mods) == 1
    assert compat._load_modules_tolerant(good)


def test_drivers_are_coroutines():
    for fn in ("run_username_scan", "run_email_scan", "run_cross_scan_async"):
        assert callable(getattr(compat, fn))


def test_cancel_event_stops_driver(tmp_path):
    from services.phone_service import PhoneService
    svc = PhoneService()
    svc._thread_cancel.set()
    result = svc.cancel()
    assert result is None
