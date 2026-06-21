from __future__ import annotations

from pathlib import Path

from app.db.config import get_database_settings
from app.db.connection import DatabaseConnectionFactory

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        current.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(current).rstrip().rstrip(";"))
            current = []
    if current:
        statements.append("\n".join(current).rstrip().rstrip(";"))
    return [statement for statement in statements if statement.strip()]


def run_migrations() -> list[str]:
    settings = get_database_settings()
    if not settings.database_url:
        raise RuntimeError("POLYBOT_DATABASE_URL or DATABASE_URL is required")

    factory = DatabaseConnectionFactory(settings)
    applied: list[str] = []
    with factory.connect() as conn:
        with conn.transaction():
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.name
            sql = path.read_text(encoding="utf-8")
            with conn.transaction():
                exists = conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = %s",
                    (version,),
                ).fetchone()
                if exists:
                    continue
                for statement in _split_sql_statements(sql):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (version,),
                )
            applied.append(version)
    return applied


def main() -> None:
    applied = run_migrations()
    if applied:
        print("Applied migrations:")
        for version in applied:
            print(f"- {version}")
    else:
        print("No pending migrations.")


if __name__ == "__main__":
    main()
