"""Tests for EmailService (holehe-v2 wrapper)."""

from __future__ import annotations

import asyncio
import os


class TestValidateEmail:
    """Email validation (local regex — holehe-v2 dropped is_email)."""

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

        progress = EmailSearchProgress(email="user@example.com", total_modules=181)
        assert progress.email == "user@example.com"
        assert progress.total_modules == 181
        assert progress.checked_modules == 0
        assert progress.is_running is False
        assert progress.is_cancelled is False
        assert len(progress.found) == 0
        assert len(progress.not_found) == 0
        assert len(progress.rate_limited) == 0

    def test_progress_has_unavailable_bucket(self):
        from services.email_service import EmailSearchProgress

        progress = EmailSearchProgress(email="a@b.com")
        assert progress.unavailable == []
        assert progress.rate_limited == []

    def test_email_result_unavailable_default(self):
        from services.email_service import EmailResult

        result = EmailResult(name="x", domain="x.com")
        assert result.unavailable is False
        assert result.rate_limit is False


class TestHoleheV2Integration:
    """holehe-v2 registry guarantees (the port's foundation)."""

    def test_registry_loads_validators(self):
        from holehe_v2.core.loader import load_validators

        validators = load_validators()
        # 181 validators in 1.0.3 (old holehe shipped 121)
        assert len(validators) >= 180
        assert "github" in validators
        assert "adobe" in validators
        assert all(callable(fn) for fn in validators.values())

    def test_service_total_modules_matches_registry(self):
        from services.email_service import EmailService

        service = EmailService()
        assert service.is_available is True
        assert service.total_modules >= 180

    def test_skip_password_recovery_drops_only_adobe(self):
        from services.email_service import EmailService

        service = EmailService()
        full = service._load_modules()
        skipped = service._load_modules(skip_password_recovery=True)
        # adobe is the only original skip-list member present in v2;
        # mail_ru/odnoklassniki/samsung are absent (kept as no-op names).
        assert set(full) - set(skipped) == {"adobe"}

    def test_invalid_email_rejected_before_scan(self):
        import pytest

        from services.email_service import EmailService

        service = EmailService()
        with pytest.raises(ValueError):
            asyncio.run(
                service.search("not-an-email", on_progress=lambda p: None)
            )


class TestErrorClassification:
    """v2 Result.message → rate_limited vs unavailable (taxonomy)."""

    def test_rate_limited_patterns(self):
        from services.email_service import _is_rate_limited

        for msg in (
            "Rate limited (429)",
            "Rate limited, wait for a few minutes",
            "Rate limit exceeded",
            "Caught by WAF or IP Block (403",
            "Cloudflare challenge, cannot be solved without a browser",
            "CAPTCHA detected (IP may be flagged)",
            "CSRF token not found (IP may be flagged)",
            "Your IP has been flagged by mastodon",
            "registration attempt has been blocked",
            "HTTP Error: 429",
            "Blocked by Allen WAF (403",
            "GitHub's signup form is behind a bot challenge",
        ):
            assert _is_rate_limited(msg), msg

    def test_unavailable_patterns_are_not_rate_limits(self):
        from services.email_service import _is_rate_limited

        for msg in (
            "Connection timed out",
            "Connection timed out! maybe region blocks",
            "Server took too long to respond (Read Timeout)",
            "Unexpected response body, report it via GitHub issues",
            "Unexpected response status: 404, report it via GitHub issues",
            "HTTP Error: 404",
            "HTTP Error: 500",
            "Failed to extract CSRF/token",
            "The email is experiencing email delivery issues",
            "",
            None,
        ):
            assert not _is_rate_limited(msg), msg


class TestResultMapping:
    """holehe-v2 Result → EmailResult bucket mapping."""

    @staticmethod
    def _map(name, r):
        from services.email_service import _map_result

        return _map_result(name, r)

    def test_taken_maps_to_found_with_extra(self):
        from holehe_v2 import Result

        r = Result.taken(
            url="https://github.com",
            extra={"login": "octocat", "profile": "https://github.com/octocat"},
            media={"avatar": "https://avatars.example/x.png"},
        )
        out = self._map("github", r)
        assert out.exists is True
        assert out.domain == "github.com"
        assert out.rate_limit is False and out.unavailable is False
        assert out.others["extra"]["login"] == "octocat"
        assert out.others["media"]["avatar"].startswith("https://")

    def test_available_maps_to_not_found(self):
        from holehe_v2 import Result

        out = self._map("spotify", Result.available(url="https://spotify.com"))
        assert out.exists is False
        assert out.rate_limit is False and out.unavailable is False

    def test_error_429_maps_to_rate_limited(self):
        from holehe_v2 import Result

        out = self._map("canva", Result.error("Rate limited (429)"))
        assert out.rate_limit is True
        assert out.unavailable is False
        assert out.exists is None

    def test_error_parse_rot_maps_to_unavailable(self):
        from holehe_v2 import Result

        out = self._map(
            "x", Result.error("Unexpected response body, report it via GitHub issues")
        )
        assert out.unavailable is True
        assert out.rate_limit is False

    def test_gravatar_extra_feeds_recovery_hints(self):
        from holehe_v2 import Result

        r = Result.taken(
            url="https://gravatar.com/u/1",
            extra={"public_emails": ["a@b.com"], "phone_numbers": ["+15551234"]},
        )
        out = self._map("gravatar", r)
        assert out.email_recovery == "a@b.com"
        assert out.phone_number == "+15551234"

    def test_walmart_prose_url_sanitized(self):
        from holehe_v2 import Result

        # Known upstream bug: message passed positionally as url.
        out = self._map("walmart", Result.taken("Account flagged as compromised"))
        assert out.exists is True
        assert out.domain == "walmart.com"
        assert out.others["url"] == "Account flagged as compromised"

    def test_domain_fallbacks(self):
        from services.email_service import _domain_from

        assert _domain_from("chess_com", None) == "chess.com"
        assert _domain_from("gravatar", "https://gravatar.com") == "gravatar.com"
        assert _domain_from("x", "https://x.com") == "x.com"


class TestScanDriver:
    """Worker-thread driver: buckets, timeout, cancel, proxy scoping."""

    @staticmethod
    def _run(stubs, **search_kwargs):
        from services import email_service as es

        async def scenario():
            ticks = []
            svc = es.EmailService()
            original = es._holehe_modules
            es._holehe_modules = dict(stubs)
            try:
                progress = await svc.search(
                    "user@example.com",
                    on_progress=ticks.append,
                    **search_kwargs,
                )
            finally:
                es._holehe_modules = original
            return progress, ticks

        return asyncio.run(scenario())

    def test_buckets_sum_to_total(self):
        from holehe_v2 import Result

        async def taken(email):
            return Result.taken(url="https://a.com")

        async def avail(email):
            return Result.available()

        async def rl(email):
            return Result.error("Rate limited (429)")

        async def unav(email):
            return Result.error("Unexpected response body")

        progress, ticks = self._run(
            {"s1": taken, "s2": taken, "s3": avail, "s4": rl, "s5": unav}
        )
        assert progress.total_modules == 5
        assert progress.checked_modules == 5
        assert len(progress.found) == 2
        assert len(progress.not_found) == 1
        assert len(progress.rate_limited) == 1
        assert len(progress.unavailable) == 1
        assert progress.is_running is False
        assert progress.is_cancelled is False
        assert ticks  # initial + final notify

    def test_validator_exception_becomes_unavailable(self):
        async def boom(email):
            raise RuntimeError("exploded")

        progress, _ = self._run({"bad": boom})
        assert len(progress.unavailable) == 1
        assert progress.unavailable[0].others["error"] == "exploded"
        assert progress.checked_modules == 1

    def test_timeout_becomes_unavailable(self):
        async def slow(email):
            await asyncio.sleep(30)

        progress, _ = self._run({"slow": slow}, timeout=1)
        assert len(progress.unavailable) == 1
        assert progress.unavailable[0].others["error"] == "Connection timed out"

    def test_cancel_stops_scan(self):
        from services import email_service as es

        async def slow(email):
            await asyncio.sleep(30)

        stubs = {f"s{i}": slow for i in range(6)}

        async def scenario():
            original = es._holehe_modules
            es._holehe_modules = dict(stubs)
            svc = es.EmailService()
            try:
                task = asyncio.create_task(
                    svc.search(
                        "user@example.com",
                        on_progress=lambda p: None,
                        timeout=3,
                    )
                )
                await asyncio.sleep(0.5)  # worker thread + loop up
                svc.cancel()
                return await asyncio.wait_for(task, timeout=15)
            finally:
                es._holehe_modules = original

        progress = asyncio.run(scenario())
        assert progress.is_cancelled is True
        assert progress.is_running is False

    def test_proxy_env_scoped_to_scan(self):
        from holehe_v2 import Result

        async def avail(email):
            return Result.available()

        before = {k: os.environ.get(k) for k in ("HTTP_PROXY", "HTTPS_PROXY")}
        progress, _ = self._run(
            {"a": avail}, proxy="http://proxy.test:8080"
        )
        after = {k: os.environ.get(k) for k in ("HTTP_PROXY", "HTTPS_PROXY")}
        assert progress.checked_modules == 1
        assert after == before  # env restored after the scan


class TestEmailService:
    """EmailService unit tests."""

    def test_instantiates(self):
        from services.email_service import EmailService

        service = EmailService()
        assert service is not None

    def test_total_modules_is_int(self):
        """total_modules returns a valid int regardless of availability."""
        from services.email_service import EmailService

        service = EmailService()
        assert isinstance(service.total_modules, int)
        assert service.total_modules >= 0

    def test_cancel_when_not_running(self):
        """cancel() should not raise even if no search is running."""
        from services.email_service import EmailService

        service = EmailService()
        service.cancel()  # Should not raise
