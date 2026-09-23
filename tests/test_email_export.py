"""Email-mode export bytes (CSV/JSON/TXT) + v2 extras rendering — Wave C."""

from __future__ import annotations

from types import SimpleNamespace

ROWS = [
    {
        "name": "gravatar",
        "domain": "gravatar.com",
        "exists": True,
        "rateLimit": False,
        "unavailable": False,
        "others": {
            "message": None,
            "extra": {"bio": "hi"},
            "media": {"avatar": "https://example.com/a.png"},
        },
    },
    {
        "name": "canva",
        "domain": "canva.com",
        "exists": None,
        "rateLimit": True,
        "unavailable": False,
        "others": {"message": "Rate limited (429)"},
    },
    {
        "name": "oldsite",
        "domain": "oldsite.com",
        "exists": None,
        "rateLimit": False,
        "unavailable": True,
        "others": {"error": "Connection timed out"},
    },
]


def _state(rows=None, addr="user@example.com"):
    return SimpleNamespace(
        email_results=rows if rows is not None else ROWS,
        email_results_address=addr,
    )


class TestEmailExport:
    """_email_export_bytes: the email-mode formats (P4-8 first slice)."""

    def test_csv(self):
        import csv
        import io

        from app_shell import _email_export_bytes

        raw = _email_export_bytes("csv", _state())
        assert raw is not None
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8"))))
        assert rows[0][:4] == ["email", "platform", "domain", "status"]
        assert rows[1][1] == "gravatar" and rows[1][3] == "FOUND"
        assert rows[2][3] == "RATE_LIMITED"
        assert rows[3][3] == "UNAVAILABLE"
        assert rows[2][4] == "Rate limited (429)"
        assert rows[3][4] == "Connection timed out"
        assert '"bio"' in rows[1][5]
        assert rows[1][0] == "user@example.com"

    def test_json(self):
        import json

        from app_shell import _email_export_bytes

        data = json.loads(_email_export_bytes("json", _state()).decode("utf-8"))
        assert data["email"] == "user@example.com"
        assert data["found"] == 1
        assert len(data["results"]) == 3

    def test_txt(self):
        from app_shell import _email_export_bytes

        text = _email_export_bytes("txt", _state()).decode("utf-8")
        assert "Sherlock email OSINT — user@example.com" in text
        assert "gravatar (gravatar.com): FOUND" in text
        assert "canva (canva.com): RATE_LIMITED" in text
        assert "oldsite (oldsite.com): UNAVAILABLE" in text

    def test_username_only_formats_return_none(self):
        from app_shell import _email_export_bytes

        assert _email_export_bytes("pdf", _state()) is None
        assert _email_export_bytes("xmind", _state()) is None

    def test_empty_rows_still_export(self):
        from app_shell import _email_export_bytes

        empty = _state(rows=[])
        assert b"email" in _email_export_bytes("csv", empty)
        assert b'"results": []' in _email_export_bytes("json", empty)


class TestV2ExtrasRendering:
    """result_card renders holehe-v2 media/extra from the others dict."""

    @staticmethod
    def _texts(card):
        from tests.flet_tree import walk

        return [
            c.value
            for c in walk(card)
            if hasattr(c, "value") and isinstance(c.value, str)
        ]

    def test_extra_lines_and_avatar(self):
        from components.result_card import ResultCard

        card = ResultCard(
            site_name="Gravatar",
            status="Available",
            others={
                "extra": {
                    "display_name": "Gravatar User",
                    "bio": "hello world",
                    "verified_accounts": ["a", "b"],
                    "contact_info": {"emails": ["x@y.z"]},  # skipped (dict)
                    "timezone": "UTC",  # skipped (noise)
                },
                "media": {"avatar": "https://example.com/a.png"},
            },
        )
        texts = self._texts(card)
        assert any("Display Name: Gravatar User" in t for t in texts)
        assert any("Bio: hello world" in t for t in texts)
        assert any("Verified Accounts: 2 linked" in t for t in texts)
        assert not any("Timezone" in t for t in texts)
        assert not any("Contact Info" in t for t in texts)
        from tests.flet_tree import walk

        assert any(c.__class__.__name__ == "Image" for c in walk(card))

    def test_extra_cap_six_lines(self):
        from components.result_card import ResultCard

        extras = {f"field_{i}": f"value{i}" for i in range(10)}
        card = ResultCard(
            site_name="X", status="Available", others={"extra": extras}
        )
        rendered = [
            t for t in self._texts(card) if t.startswith("Field ")
        ]
        assert len(rendered) == 6
