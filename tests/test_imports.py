"""Import smoke tests for Sherlock-V2."""



def test_import_main():
    import main  # noqa: F401


def test_import_app_shell():
    import app_shell  # noqa: F401


def test_import_services():
    from services import (
        email_service,
        phone_service,
        sherlock_service,
    )
    assert sherlock_service.SherlockService is not None
    assert email_service.EmailService is not None
    assert phone_service.PhoneService is not None


def test_import_screens():
    from screens import (
        home_screen,
    )
    assert home_screen.HomeScreen is not None


def test_import_components():
    from components import active_scan_banner
    assert active_scan_banner.ActiveScanBanner is not None
