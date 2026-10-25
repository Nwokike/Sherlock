"""Service contract tests for Sherlock-V2."""


from services.email_service import EmailService, validate_email
from services.phone_service import PhoneService
from services.sherlock_service import SherlockService, parse_usernames


def test_sherlock_service_available():
    svc = SherlockService()
    assert svc.is_available is True


def test_email_service_available():
    svc = EmailService()
    assert svc.is_available is True


def test_phone_service_available():
    svc = PhoneService()
    assert svc.is_available is True


def test_validate_email():
    assert validate_email("a@b.com") is True
    assert validate_email("not-an-email") is False


def test_parse_usernames():
    assert parse_usernames("a b c") == ["a", "b", "c"]
    assert parse_usernames("a,b,c") == ["a", "b", "c"]
    assert parse_usernames("") == []


def test_sherlock_search_returns_progress():
    import asyncio
    svc = SherlockService()
    asyncio.run(svc.load_sites())
    assert svc._modules is not None
    assert len(svc._modules) > 0


def test_phone_search_returns_progress():
    import asyncio
    svc = PhoneService()
    asyncio.run(svc.load_sites())
    assert svc._modules is not None
    assert len(svc._modules) == 5
