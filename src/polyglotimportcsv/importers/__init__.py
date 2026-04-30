"""Database-specific import implementations."""

from polyglotimportcsv.importers.base import BackendImporterFn, ImporterRegistry
from polyglotimportcsv.importers.cassandra_importer import run_cassandra_import
from polyglotimportcsv.importers.mongodb_importer import run_mongodb_import
from polyglotimportcsv.importers.neo4j_importer import run_neo4j_import
from polyglotimportcsv.importers.postgres_importer import run_postgres_import
from polyglotimportcsv.importers.redis_importer import run_redis_import


def default_importer_registry() -> ImporterRegistry:
    """Wired defaults for production CLI; tests may supply a custom registry."""
    return {
        "postgres": run_postgres_import,
        "redis": run_redis_import,
        "mongodb": run_mongodb_import,
        "cassandra": run_cassandra_import,
        "neo4j": run_neo4j_import,
    }


__all__ = [
    "BackendImporterFn",
    "ImporterRegistry",
    "default_importer_registry",
    "run_postgres_import",
    "run_redis_import",
    "run_mongodb_import",
    "run_cassandra_import",
    "run_neo4j_import",
]
