"""Customer-isolation contract test: verifies every analysis query is user-scoped.

Runs without a DB by inspecting source — guards against regressions where a
future edit forgets `Analysis.user_id == user.id`.
"""
import pathlib

API = pathlib.Path(__file__).parent.parent / "backend" / "app" / "api" / "analysis.py"
SRC = API.read_text()


def test_detail_delete_report_filter_by_user():
    # detail(), remove(), report_json(), report_pdf() must scope by user
    assert SRC.count("Analysis.user_id == user.id") >= 4


def test_history_filters_by_user():
    assert "Analysis.user_id == user.id" in SRC


def test_admin_routes_require_admin_user():
    assert SRC.count("Depends(admin_user)") >= 3


def test_roles_never_from_client():
    # auth.py must hard-code CUSTOMER on register; deps must read role from DB
    auth = (pathlib.Path(__file__).parent.parent / "backend" / "app" / "api" / "auth.py").read_text()
    assert 'role="CUSTOMER"' in auth
    deps = (pathlib.Path(__file__).parent.parent / "backend" / "app" / "security" / "deps.py").read_text()
    assert "user.role" in deps


def test_rls_hardening_migration_removes_client_writes():
    migration = (
        pathlib.Path(__file__).parent.parent
        / "supabase"
        / "migrations"
        / "0004_security_hardening.sql"
    ).read_text()
    assert 'drop policy if exists "own profile" on public.profiles;' in migration
    assert "for select to authenticated" in migration
    assert "revoke insert, update, delete on public.profiles" in migration
    assert "password_hash" not in migration.split("grant select", 1)[1].split(";", 1)[0]
    assert "storage.buckets" in migration
    assert "public = false" in migration


def test_no_public_storage_mount():
    main = (pathlib.Path(__file__).parent.parent / "backend" / "app" / "main.py").read_text()
    assert "StaticFiles" not in main
    assert "app.mount(" not in main
