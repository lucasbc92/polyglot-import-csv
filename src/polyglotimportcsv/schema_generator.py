"""Generate SQL DDL for PostgreSQL from entity definitions."""

from __future__ import annotations

from typing import Any, Dict, List


def postgres_column_ddl(col_name: str, db_type: str) -> str:
    safe = col_name.replace('"', "")
    return f'"{safe}" {db_type}'


def build_postgres_create_tables(
    schema: str,
    entities: Dict[str, Dict[str, Any]],
    relationships: Dict[str, Dict[str, Any]],
) -> List[str]:
    """Return ordered CREATE TABLE statements (no FK yet)."""
    stmts: List[str] = []
    stmts.append(f'CREATE SCHEMA IF NOT EXISTS "{schema}";')
    for table, ecfg in entities.items():
        cols: List[str] = []
        pks: List[str] = []
        for src, spec in (ecfg.get("columns") or {}).items():
            db_col = spec.get("db_column") or spec.get("alias_db") or src
            db_type = spec.get("db_type") or "TEXT"
            safe_col = db_col.replace('"', "")
            cols.append(postgres_column_ddl(safe_col, db_type))
            if spec.get("is_key"):
                pks.append(f'"{safe_col}"')
        if pks:
            cols.append(f"PRIMARY KEY ({', '.join(pks)})")
        fq = f'"{schema}"."{table}"'
        stmts.append(f"CREATE TABLE IF NOT EXISTS {fq} (\n  " + ",\n  ".join(cols) + "\n);")
    return stmts


def build_postgres_foreign_keys(
    schema: str,
    entities: Dict[str, Dict[str, Any]],
    relationships: Dict[str, Dict[str, Any]],
) -> List[str]:
    """ALTER TABLE ... ADD CONSTRAINT for each relationship."""
    stmts: List[str] = []
    for rname, rspec in (relationships or {}).items():
        from_t = rspec["from"]
        to_t = rspec["to"]
        fk = rspec["foreign_key"]
        refk = rspec.get("references_key") or fk
        con_name = f"{from_t}_{to_t}_{rname}_fk".replace("-", "_")
        fq_from = f'"{schema}"."{from_t}"'
        fq_to = f'"{schema}"."{to_t}"'
        stmts.append(
            f'ALTER TABLE {fq_from} DROP CONSTRAINT IF EXISTS "{con_name}";'
            f'ALTER TABLE {fq_from} ADD CONSTRAINT "{con_name}" '
            f'FOREIGN KEY ("{fk}") REFERENCES {fq_to} ("{refk}");'
        )
    return stmts
