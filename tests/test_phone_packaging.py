"""Android packaging regression: phonsint must be extracted, not ZIP-imported.

serious_python (Flet's Android packager) stores pure-Python packages in ZIPs.
phonsint discovers validators through Path(__file__).parent/"modules"; that
path does not exist under zipimport, so its catalog silently becomes empty and
a scan reports 0/0 without making a request.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import phonsint
import pytest

from services import phone_service as ps

ROOT = Path(__file__).resolve().parent.parent


def test_phonsint_is_in_android_extract_packages():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extract = config["tool"]["flet"]["android"]["extract_packages"]
    assert "phonsint" in extract


def test_zipimport_reproduces_the_empty_catalog(tmp_path):
    package = Path(phonsint.__file__).parent
    archive = tmp_path / "phonsint.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for file in package.rglob("*.py"):
            zf.write(file, file.relative_to(package.parent))

    code = (
        "import sys;sys.path.insert(0,sys.argv[1]);"
        "from phonsint.core.helpers import load_categories;"
        "print(len(load_categories()))"
    )
    result = subprocess.check_output(  # noqa: S603 — constant code/args, local zip
        [sys.executable, "-I", "-c", code, str(archive)],
        text=True,
    )
    assert result.strip() == "0", "zipimport should hide phonsint's module directory"


def test_service_reports_unavailable_when_catalog_is_empty(monkeypatch):
    monkeypatch.setattr(ps, "load_catalog", lambda: [])
    service = ps.PhoneService()
    available, reason = service.check_available()
    assert available is False
    assert "catalog is empty" in reason
    assert "extract_packages" in reason
    assert service.is_available is False


def test_service_reports_catalog_exception(monkeypatch):
    def broken_catalog():
        raise OSError("modules directory missing")

    monkeypatch.setattr(ps, "load_catalog", broken_catalog)
    available, reason = ps.PhoneService().check_available()
    assert available is False
    assert "phonsint catalog failed" in reason
    assert "modules directory missing" in reason


def test_search_refuses_an_empty_catalog(monkeypatch):
    import asyncio

    monkeypatch.setattr(ps, "load_catalog", lambda: [])
    with pytest.raises(RuntimeError, match="catalog is empty"):
        asyncio.run(ps.PhoneService().search("+14155552671"))
