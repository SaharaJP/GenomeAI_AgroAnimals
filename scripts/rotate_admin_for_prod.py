#!/usr/bin/env python3
"""Rotate seed-admin credentials before exposing prod to the internet.

Default ``admin/admin`` is a known credential pair shipped for dev. The
moment the deployment becomes publicly addressable (e.g. genomeai.ru
A-record + HTTPS via Let's Encrypt) keeping it active is equivalent to
shipping an open shell. This utility:

1. Creates (or reactivates) a new admin user with a strong password
   hashed via the same pbkdf2-sha256 routine as the live web auth.
2. Deactivates the default ``admin`` user (is_active=FALSE) so its
   sessions are immediately invalidated and password-based login
   stops working. We do NOT DELETE — audit references stay intact.

Run from the backend container so it reaches Postgres via the
GENOMEAI_RUNTIME_POSTGRES_DSN_FILE secret. The auth_users table is
populated by alembic migration 20260414_03_runtime_state_postgres_
baseline.

Usage (inside docker compose):

    docker compose -f compose.yaml -f compose.prod.yaml \\
      --env-file env/prod.env exec backend-api \\
      python scripts/rotate_admin_for_prod.py \\
        --new-username owner \\
        --new-password <strong> \\
        --tenant-id default \\
        --deactivate-default-admin

Run --dry-run first to confirm the SQL that will be executed.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any


def _hash(password: str) -> str:
    # Late import so the script can also be smoke-tested without the
    # full backend stack present (the import resolves via PYTHONPATH).
    from web_cabinet.auth import hash_password

    return hash_password(password)


def _connect() -> Any:
    from core.infra.postgres_compat import connect_postgres_compat

    return connect_postgres_compat()


def _user_exists(conn: Any, *, tenant_id: str, username: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM auth_users WHERE tenant_id=? AND username=?",
        (tenant_id, username),
    ).fetchone()
    return row is not None


def _insert_or_update_admin(
    conn: Any,
    *,
    tenant_id: str,
    username: str,
    password_hash: str,
    dry_run: bool,
) -> str:
    if _user_exists(conn, tenant_id=tenant_id, username=username):
        sql = (
            "UPDATE auth_users SET password_hash=?, is_active=TRUE, role='Admin' "
            "WHERE tenant_id=? AND username=?"
        )
        params = (password_hash, tenant_id, username)
        action = "UPDATE existing user"
    else:
        sql = (
            "INSERT INTO auth_users(tenant_id, username, password_hash, role, is_active) "
            "VALUES(?,?,?, 'Admin', TRUE)"
        )
        params = (tenant_id, username, password_hash)
        action = "INSERT new user"

    if dry_run:
        print(f"[DRY-RUN] {action}: {sql} params=(<hash redacted>, ...)")
        return action

    conn.execute(sql, params)
    conn.commit()
    return action


def _deactivate_default_admin(conn: Any, *, tenant_id: str, dry_run: bool) -> bool:
    sql = "UPDATE auth_users SET is_active=FALSE WHERE tenant_id=? AND username='admin'"
    if dry_run:
        print(f"[DRY-RUN] {sql} params=({tenant_id!r},)")
        return False
    conn.execute(sql, (tenant_id,))
    conn.commit()
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-username", required=True, help="username for the new prod admin")
    parser.add_argument("--new-password", required=True, help="strong password (>=16 chars recommended)")
    parser.add_argument("--tenant-id", default="default", help="tenant_id (default: 'default')")
    parser.add_argument(
        "--deactivate-default-admin",
        action="store_true",
        help="set is_active=FALSE on the default 'admin' user (recommended for prod)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the SQL without executing")
    args = parser.parse_args(argv)

    if len(args.new_password) < 12:
        print(
            "WARN: password length < 12 — prod admin credentials should be at least 16 chars.",
            file=sys.stderr,
        )

    password_hash = _hash(args.new_password)

    if args.dry_run:
        conn = None
    else:
        conn = _connect()

    try:
        if conn is not None:
            action = _insert_or_update_admin(
                conn,
                tenant_id=args.tenant_id,
                username=args.new_username,
                password_hash=password_hash,
                dry_run=False,
            )
            print(f"OK {action}: tenant_id={args.tenant_id} username={args.new_username}")
            if args.deactivate_default_admin:
                deactivated = _deactivate_default_admin(conn, tenant_id=args.tenant_id, dry_run=False)
                print(
                    "OK deactivated default 'admin' user"
                    if deactivated
                    else "SKIP default 'admin' deactivation"
                )
        else:
            _insert_or_update_admin(
                conn=None,  # type: ignore[arg-type]
                tenant_id=args.tenant_id,
                username=args.new_username,
                password_hash=password_hash,
                dry_run=True,
            )
            if args.deactivate_default_admin:
                _deactivate_default_admin(conn=None, tenant_id=args.tenant_id, dry_run=True)  # type: ignore[arg-type]
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    print(
        "Done. Verify by hitting POST /api/app/v1/auth/login with the new credentials, "
        "then run --deactivate-default-admin once you've confirmed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
