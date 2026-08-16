"""Test collection policy for optional, external offline evaluation packs.

The public source tree deliberately excludes the 24 native carrier packages.
They are required only by the frozen offline/oracle evaluation suite, never by
the application runtime.  Keep those assertions intact when an authorized pack
root is supplied, and make their absence explicit in a fresh public clone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REAL_AUTH_TEST = False

def _install_authenticated_legacy_client() -> None:
    """Adapt pre-P6 API tests through FastAPI's supported dependency override.

    The authentication/ACL test module exercises real cookies and SQLite and is
    deliberately excluded. Production code has no test header bypass.
    """
    from fastapi.testclient import TestClient
    from app.api.dependencies import require_project_membership
    from app.contracts.authentication import AuthenticatedAccount

    if getattr(TestClient, "_signal_council_auth_adapter", False):
        return
    original_init = TestClient.__init__
    original_request = TestClient.request

    def patched_init(self: TestClient, app: object, *args: object, **kwargs: object) -> None:
        original_init(self, app, *args, **kwargs)
        if _REAL_AUTH_TEST:
            return
        self.app.state.legacy_test_role = "business"

        def principal_override() -> AuthenticatedAccount:
            role = self.app.state.legacy_test_role
            username = "coordinator" if role == "leadership" else role
            return AuthenticatedAccount(account_id=f"test-{username}", username=username, display_name=username, role=role)

        self.app.dependency_overrides[require_project_membership] = principal_override

    def patched_request(self: TestClient, method: str, url: object, *args: object, **kwargs: object):
        if _REAL_AUTH_TEST or not hasattr(self.app.state, "legacy_test_role"):
            return original_request(self, method, url, *args, **kwargs)
        headers = kwargs.get("headers") or {}
        role = headers.get("X-Compare-Role") if hasattr(headers, "get") else None
        path = str(url)
        if role is None and "/review/risk/" in path:
            role = "risk"
        elif role is None and "/review/business/" in path:
            role = "business"
        elif role is None and "/approval/transitions" in path:
            role = "leadership"
        if role in {"business", "risk", "leadership"}:
            self.app.state.legacy_test_role = role
        return original_request(self, method, url, *args, **kwargs)

    TestClient.__init__ = patched_init
    TestClient.request = patched_request
    TestClient._signal_council_auth_adapter = True

_install_authenticated_legacy_client()

@pytest.fixture(autouse=True)
def select_real_auth_tests(request: pytest.FixtureRequest):
    global _REAL_AUTH_TEST
    previous = _REAL_AUTH_TEST
    _REAL_AUTH_TEST = Path(str(request.fspath)).name == "test_authentication_and_acl.py"
    yield
    _REAL_AUTH_TEST = previous

from evals.model_gateway.material_paths import native_material_pack_root


_NATIVE_PACK_EVAL_MODULES = {
    "test_blind_eval_release.py",
    "test_blind_eval_release_v3.py",
    "test_blind_eval_rubric.py",
    "test_blind_eval_rubric_v2.py",
    "test_codex_oracle.py",
    "test_model_gateway_runner.py",
}


def _native_pack_is_available() -> bool:
    root = native_material_pack_root()
    return (root / "package-index.json").is_file() and (
        root / "project-01" / "manifest.json"
    ).is_file()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip only asset-dependent offline evaluations when their packs are absent."""

    if _native_pack_is_available():
        return

    marker = pytest.mark.skip(
        reason=(
            "optional external native-material-packs are not configured; "
            "the public clone keeps production material import behavior unchanged"
        )
    )
    for item in items:
        if Path(str(item.fspath)).name in _NATIVE_PACK_EVAL_MODULES:
            item.add_marker(marker)
