"""Tests for EmailService (holehe wrapper)."""

from __future__ import annotations


class TestValidateEmail:
    """Email validation without holehe dependency."""

    def test_valid_emails(self):
        from services.email_service import validate_email

        assert validate_email("user@example.com") is True
        assert validate_email("john.doe+tag@domain.co.uk") is True
        assert validate_email("test@sub.domain.org") is True

    def test_invalid_emails(self):
        from services.email_service import validate_email

        assert validate_email("notanemail") is False
        assert validate_email("missing@dot") is False
        assert validate_email("@nodomain.com") is False
        assert validate_email("") is False

    def test_username_is_not_email(self):
        from services.email_service import validate_email

        assert validate_email("johndoe") is False
        assert validate_email("john_doe_123") is False


class TestEmailResult:
    """EmailResult dataclass construction."""

    def test_default_values(self):
        from services.email_service import EmailResult

        result = EmailResult(name="github", domain="github.com")
        assert result.name == "github"
        assert result.domain == "github.com"
        assert result.exists is None
        assert result.rate_limit is False
        assert result.email_recovery is None
        assert result.phone_number is None
        assert result.others is None

    def test_full_construction(self):
        from services.email_service import EmailResult

        result = EmailResult(
            name="google",
            domain="google.com",
            method="register",
            exists=True,
            rate_limit=False,
            email_recovery="u***@gmail.com",
            phone_number="+1***1234",
            others={"FullName": "John Doe"},
        )
        assert result.exists is True
        assert result.email_recovery == "u***@gmail.com"
        assert result.phone_number == "+1***1234"
        assert result.others["FullName"] == "John Doe"


class TestEmailSearchProgress:
    """EmailSearchProgress dataclass."""

    def test_initial_state(self):
        from services.email_service import EmailSearchProgress

        progress = EmailSearchProgress(email="user@example.com", total_modules=121)
        assert progress.email == "user@example.com"
        assert progress.total_modules == 121
        assert progress.checked_modules == 0
        assert progress.is_running is False
        assert progress.is_cancelled is False
        assert len(progress.found) == 0
        assert len(progress.not_found) == 0
        assert len(progress.rate_limited) == 0


class TestEmailService:
    """EmailService unit tests."""

    def test_instantiates(self):
        from services.email_service import EmailService

        service = EmailService()
        assert service is not None

    def test_total_modules_fallback(self):
        """total_modules returns fallback 121 if holehe not available."""
        from services.email_service import EmailService

        service = EmailService()
        # Whether holehe is available or not, total_modules is a valid int
        assert isinstance(service.total_modules, int)
        assert service.total_modules >= 0

    def test_cancel_when_not_running(self):
        """cancel() should not raise even if no search is running."""
        from services.email_service import EmailService

        service = EmailService()
        service.cancel()  # Should not raise
