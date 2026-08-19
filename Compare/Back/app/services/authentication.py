from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.contracts.authentication import AuthenticatedAccount
from app.contracts.errors import ForbiddenError, ServiceError
from app.repositories.schema import SCHEMA_SQL, SCHEMA_VERSION

PASSWORD_ITERATIONS = 310_000
SESSION_COOKIE_NAME = "signal_council_session"
DEMO_ACCOUNTS = (
    ("account-business", "business", "业务", "business"),
    ("account-risk", "risk", "风控", "risk"),
    ("account-coordinator", "coordinator", "协管", "leadership"),
)

def _utc_now() -> datetime:
    return datetime.now(UTC)

def _timestamp(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat()

def _derive_password(password: str, salt: bytes, iterations: int = PASSWORD_ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()

class AuthenticationService:
    """SQLite-backed local-demo authentication with no raw secret persistence."""

    def __init__(self, database_path: str | Path, *, session_hours: int = 12) -> None:
        self.database_path = str(Path(database_path).resolve())
        self.session_hours = session_hours
        self._lock = threading.RLock()
        self._seed_complete = False

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def seed(self) -> None:
        if self._seed_complete:
            return
        with self._lock:
            if self._seed_complete:
                return
            with self._connect() as db:
                db.executescript(SCHEMA_SQL)
                for account_id, username, display_name, role in DEMO_ACCOUNTS:
                    if db.execute("SELECT 1 FROM accounts WHERE id=?", (account_id,)).fetchone():
                        continue
                    salt = secrets.token_bytes(16)
                    db.execute(
                        """INSERT INTO accounts(id, username, display_name, role, password_salt,
                           password_hash, password_iterations, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (account_id, username, display_name, role, salt.hex(), _derive_password("123456", salt), PASSWORD_ITERATIONS, _timestamp()),
                    )
                if db.execute("SELECT 1 FROM seed_runs WHERE seed_key='signal-council-auth-v1'").fetchone() is None:
                    db.execute(
                        """INSERT OR IGNORE INTO project_memberships(project_id, account_id, created_at)
                           SELECT p.id, a.id, ? FROM projects p CROSS JOIN accounts a""",
                        (_timestamp(),),
                    )
                    project_count = db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
                    db.execute(
                        "INSERT INTO seed_runs(seed_key, source, project_count, created_at) VALUES ('signal-council-auth-v1', 'local_demo_auth', ?, ?)",
                        (project_count, _timestamp()),
                    )
                db.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)", (SCHEMA_VERSION, _timestamp())
                )
            # Mark complete only after the transaction exits successfully, so a
            # failed seed remains retryable.
            self._seed_complete = True

    def reconcile_project_memberships(self) -> None:
        """Idempotently grant the local demo accounts access to seeded projects.

        Workbench project seeding is lazy, so the first authentication seed can
        legitimately run before any project exists. Reconcile after Workbench
        initialization to cover projects added later without rerunning schema
        initialization on every request. Only projects with no memberships at
        all are healed; partial per-project ACLs remain backend-enforced.
        """
        with self._lock, self._connect() as db:
            unmembered = db.execute(
                """SELECT 1 FROM projects p
                   WHERE NOT EXISTS (
                       SELECT 1 FROM project_memberships m WHERE m.project_id = p.id
                   ) LIMIT 1"""
            ).fetchone()
            if unmembered is None:
                return
            db.execute(
                """INSERT OR IGNORE INTO project_memberships(project_id, account_id, created_at)
                   SELECT p.id, a.id, ? FROM projects p CROSS JOIN accounts a
                   WHERE NOT EXISTS (
                       SELECT 1 FROM project_memberships m WHERE m.project_id = p.id
                   )""",
                (_timestamp(),),
            )

    @staticmethod
    def _account(row: sqlite3.Row) -> AuthenticatedAccount:
        return AuthenticatedAccount(account_id=row["id"], username=row["username"], display_name=row["display_name"], role=row["role"])

    def login(
        self,
        username: str,
        password: str,
        *,
        revoke_existing_sessions: bool = True,
    ) -> tuple[AuthenticatedAccount, str, datetime]:
        self.seed()
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM accounts WHERE username=?", (username.strip().lower(),)).fetchone()
            if row is None:
                # Equalize the expensive path without disclosing account existence.
                _derive_password(password, bytes(16))
                valid = False
            else:
                candidate = _derive_password(password, bytes.fromhex(row["password_salt"]), row["password_iterations"])
                valid = hmac.compare_digest(candidate, row["password_hash"])
            if not valid or row is None:
                raise ServiceError(code="authentication_failed", message="账号或密码错误。", category="validation", status_code=401)
            now = _utc_now()
            expires_at = now + timedelta(hours=self.session_hours)
            if revoke_existing_sessions:
                db.execute(
                    "UPDATE account_sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL",
                    (_timestamp(now), row["id"]),
                )
            token = secrets.token_urlsafe(48)
            db.execute(
                """INSERT INTO account_sessions(token_hash, account_id, created_at, expires_at, last_active_at, revoked_at)
                   VALUES (?, ?, ?, ?, ?, NULL)""",
                (_token_hash(token), row["id"], _timestamp(now), _timestamp(expires_at), _timestamp(now)),
            )
            return self._account(row), token, expires_at

    def authenticate(self, token: str | None) -> AuthenticatedAccount:
        if not token:
            raise ServiceError(code="authentication_required", message="请先登录。", category="validation", status_code=401)
        self.seed()
        digest = _token_hash(token)
        with self._lock, self._connect() as db:
            row = db.execute(
                """SELECT a.* FROM account_sessions s JOIN accounts a ON a.id=s.account_id
                   WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>?""",
                (digest, _timestamp()),
            ).fetchone()
            if row is None:
                raise ServiceError(code="session_expired", message="登录状态已失效，请重新登录。", category="validation", status_code=401)
            db.execute("UPDATE account_sessions SET last_active_at=? WHERE token_hash=?", (_timestamp(), digest))
            return self._account(row)

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._lock, self._connect() as db:
            db.execute("UPDATE account_sessions SET revoked_at=COALESCE(revoked_at, ?) WHERE token_hash=?", (_timestamp(), _token_hash(token)))

    def require_membership(self, principal: AuthenticatedAccount, project_id: str) -> None:
        self.seed()
        with self._connect() as db:
            row = db.execute("SELECT 1 FROM project_memberships WHERE project_id=? AND account_id=?", (project_id, principal.account_id)).fetchone()
        if row is None:
            raise ForbiddenError("project_access_denied", "当前账号无权访问该项目。")

    def require_role(self, principal: AuthenticatedAccount, *roles: str) -> None:
        if principal.role not in roles:
            raise ForbiddenError("role_action_forbidden", "当前账号角色无权执行该操作。", details={"allowedRoles": list(roles)})
