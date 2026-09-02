"""Unit tests for live email progress streaming and module isolation."""

from services.email_service import EmailResult, EmailSearchProgress, EmailService


def test_email_search_progress_live_accumulation():
    progress = EmailSearchProgress(email="target@example.com", total_modules=5)
    assert progress.email == "target@example.com"
    assert progress.total_modules == 5
    assert progress.checked_modules == 0

    # Add a found result
    res1 = EmailResult(
        name="Instagram", domain="instagram.com", exists=True, method="recovery"
    )
    progress.found.append(res1)
    progress.checked_modules += 1

    assert len(progress.found) == 1
    assert progress.checked_modules == 1

    # Add a not found result
    res2 = EmailResult(name="Twitter", domain="twitter.com", exists=False)
    progress.not_found.append(res2)
    progress.checked_modules += 1

    assert len(progress.not_found) == 1
    assert progress.checked_modules == 2

    # Add a rate limited result
    res3 = EmailResult(
        name="LinkedIn", domain="linkedin.com", exists=False, rate_limit=True
    )
    progress.rate_limited.append(res3)
    progress.checked_modules += 1

    assert len(progress.rate_limited) == 1
    assert progress.checked_modules == 3


def test_email_service_cancellation():
    service = EmailService()
    service.cancel()
    assert service._thread_cancel.is_set() is True
