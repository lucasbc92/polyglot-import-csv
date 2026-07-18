"""CQL type resolution for Cassandra DDL: explicit db_type vs. inferred kind fallback."""

from polyglotimportcsv.importers.cassandra_importer import _cassandra_type_for


def test_explicit_db_type_wins_over_kind():
    assert _cassandra_type_for({"db_type": "TIMESTAMPTZ"}, "string") == "timestamp"
    assert _cassandra_type_for({"db_type": "BIGINT"}, "string") == "bigint"


def test_missing_db_type_falls_back_to_inferred_kind():
    assert _cassandra_type_for({}, "integer") == "bigint"
    assert _cassandra_type_for({}, "float") == "double"
    assert _cassandra_type_for({}, "datetime") == "timestamp"
    assert _cassandra_type_for({}, "boolean") == "boolean"
    assert _cassandra_type_for({}, "string") == "text"


def test_manual_spec_without_db_type_falls_back_to_kind():
    assert _cassandra_type_for({"schema_column": "event_time"}, "datetime") == "timestamp"
