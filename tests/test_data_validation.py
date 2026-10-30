"""The validation read: the write's own engine, with sinks that check instead of writing.

Every rule is exercised end to end, from small CSVs through ``plan_import`` and
``validate_data``, so what is checked is what the write would send.
"""

import dataclasses
import gc
import tracemalloc
from pathlib import Path

import pytest
from rich.console import Console

from polyglotimportcsv import reporting
from polyglotimportcsv.benchmark_runner import _MODE_CONFIG, _overrides
from polyglotimportcsv.business_exception import BusinessException, DataValidationError
from polyglotimportcsv.config_parser import load_import_config
from polyglotimportcsv.data_validation import (
    MAX_EXAMPLES,
    Example,
    ValidationReport,
    print_validation_report,
    validate_data,
)
from polyglotimportcsv.import_plan import plan_import
from polyglotimportcsv.sinks.neo4j_sink import Neo4jSink
from polyglotimportcsv.stream_runner import run_stream_import
from polyglotimportcsv.validation import BACKENDS

ROOT = Path(__file__).resolve().parents[1]
ECOM = ROOT / "data" / "ecommerce"
BENCH = ROOT / "data" / "benchmark"


def _write_csv(path, header, rows):
    path.write_text(",".join(header) + "\n" +
                    "".join(",".join(str(c) for c in r) + "\n" for r in rows),
                    encoding="utf-8")


def _dates(n):
    return [f"2023-01-{1 + i % 28:02d}" for i in range(n)]


def _validate(tmp_path, config, dbms_names=None, kinds=None):
    """Validate ``config`` over the CSVs in ``tmp_path``. ``kinds`` forces the kind of
    columns the inference would not give that kind, to reach the casts that can fail."""
    plan = plan_import(config, tmp_path, dbms_names=dbms_names or [
        b for b in BACKENDS if b in config
    ])
    for entities in plan.bindings.values():
        for binding in entities.values():
            binding.kinds.update({c: k for c, k in (kinds or {}).items() if c in binding.kinds})
    return validate_data(plan)


def _only_group(report):
    (group,) = report.groups()
    return group


def _events_config(columns, dbms="postgres", **entity):
    return {
        "sources": {"ev": "ev.csv"},
        dbms: {"entities": {"events": {"source": "ev", "columns": columns, **entity}}},
    }


def _write_events_with_a_bad_date(tmp_path, bad_index=7, n=20):
    when = _dates(n)
    when[bad_index] = "2023-02-30"
    _write_csv(tmp_path / "ev.csv", ["id", "when"], list(zip(range(n), when)))


def test_an_unparseable_date_in_a_mapped_column_is_an_error(tmp_path):
    _write_events_with_a_bad_date(tmp_path, bad_index=7)
    report, _ = _validate(tmp_path, _events_config({"id": {"is_key": True}, "when": {}}))
    group = _only_group(report)
    assert (group.rule, group.where, group.count) == ("not_convertible", "postgres · events", 1)
    assert "when" in group.detail and "datetime" in group.detail
    (ex,) = group.examples
    assert (ex.file, ex.line, ex.column, ex.value) == ("ev.csv", 7 + 2, "when", "2023-02-30")


def test_the_same_bad_date_in_an_unmapped_column_is_not(tmp_path):
    _write_events_with_a_bad_date(tmp_path)
    report, _ = _validate(tmp_path, _events_config({"id": {"is_key": True}}))
    assert report.ok() and report.total() == 0 and report.groups() == []


def test_integer_text_fallback_is_an_error(tmp_path):
    qty = [str(i) for i in range(10)]
    qty[4] = "n/a"  # the inference calls the column text: forced to integer, the text stays
    _write_csv(tmp_path / "ev.csv", ["id", "qty"], list(zip(range(10), qty)))
    report, _ = _validate(tmp_path, _events_config({"id": {"is_key": True}, "qty": {}}),
                          kinds={"qty": "integer"})
    group = _only_group(report)
    assert (group.rule, group.where) == ("not_convertible", "postgres · events")
    assert "qty" in group.detail and "integer" in group.detail
    assert [(e.line, e.value) for e in group.examples] == [(6, "n/a")]


def test_integral_numbers_in_an_integer_column_are_valid_and_cast_exactly(tmp_path):
    # pandas writes an integer column with a missing value as 1.0, 2.0; spreadsheets write
    # 10.0. The inference counts them as integers and the cast converts them.
    qty = ["1.0", "", "3.0", "1e3", "9007199254740993.0"]
    _write_csv(tmp_path / "ev.csv", ["id", "qty"], list(zip(range(5), qty)))
    config = _events_config({"id": {"is_key": True}, "qty": {}}, dbms="mongodb")
    plan = plan_import(config, tmp_path, dbms_names=["mongodb"])
    assert plan.bindings["mongodb"]["events"].kinds["qty"] == "integer"
    cast = []
    report, _ = validate_data(plan, on_batch=lambda dbms, part, frame: cast.extend(frame["qty"]))
    assert report.ok(), _report_text(report)
    assert cast == [1, None, 3, 1000, 9007199254740993]  # exact: a float gives ...992
    assert all(v is None or type(v) is int for v in cast)


def test_an_each_split_entity_is_one_place_and_its_each_column_is_checked(tmp_path):
    when = _dates(20)
    when[1] = when[12] = "2023-02-30"
    region = ["1" if i % 2 else "2" for i in range(20)]
    region[5] = "n/a"  # forced to integer below, so that it is the one that does not convert
    _write_csv(tmp_path / "ev.csv", ["id", "when", "region"], list(zip(range(20), when, region)))
    config = _events_config(
        {"id": {"is_key": True}, "when": {}},
        filters=[{"column": "region", "operator": "each"}],
    )
    report, counts = _validate(tmp_path, config, kinds={"region": "integer"})
    assert set(counts.written["postgres"]) == {"events_1", "events_2", "events_n_a"}
    by_rule = {g.rule + ":" + g.detail.split("'")[1]: g for g in report.groups()}
    assert set(by_rule) == {"not_convertible:when", "not_convertible:region"}
    dates = by_rule["not_convertible:when"]
    assert dates.where == "postgres · events" and dates.count == 2  # rows of two partitions
    assert [e.line for e in by_rule["not_convertible:region"].examples] == [7]


def test_a_bad_date_in_a_datetime_each_column_is_an_error(tmp_path):
    # The row goes to no partition (its each value casts to None), so only the rows the
    # split drops show it; the empty each cell is dropped too, but is no error.
    when = [f"2023-01-{1 + i % 3:02d}" for i in range(20)]
    when[4], when[9] = "2023-02-30", ""
    _write_csv(tmp_path / "ev.csv", ["id", "when"], list(zip(range(20), when)))
    config = _events_config({"id": {"is_key": True}},
                            filters=[{"column": "when", "operator": "each"}])
    report, counts = _validate(tmp_path, config)
    group = _only_group(report)
    assert (group.rule, group.where) == ("not_convertible", "postgres · events")
    assert [(e.line, e.column, e.value) for e in group.examples] == [(6, "when", "2023-02-30")]
    assert counts.entity_rows["postgres"]["events"] == 18


def test_empty_key_is_an_error_for_postgres_redis_neo4j_not_mongodb(tmp_path):
    _write_csv(tmp_path / "items.csv", ["id", "name"], [("a", "x"), ("", "y"), ("c", "z")])
    entity = {"source": "items", "columns": {"id": {"is_key": True}, "name": {}}}
    config = {"sources": {"items": "items.csv"}}
    for dbms in ("postgres", "mongodb", "redis", "neo4j"):
        config[dbms] = {"entities": {"items": dict(entity)}}
    report, _ = _validate(tmp_path, config)
    assert [(g.rule, g.where, g.count) for g in report.groups()] == [
        ("empty_key", "postgres · items", 1),
        ("empty_key", "redis · items", 1),
        ("empty_key", "neo4j · items", 1),
    ]
    assert all(g.examples[0].line == 3 and g.examples[0].column == "id" for g in report.groups())


def test_empty_cassandra_partition_or_cluster_is_an_error(tmp_path):
    rows = [("u1", "2023-01-01", "a"), ("", "2023-01-02", "b"), ("u3", "", "c"),
            ("u4", "2023-01-04", "")]  # an empty note is no key
    _write_csv(tmp_path / "ev.csv", ["user_id", "ts", "note"], rows)
    config = _events_config(
        {"user_id": {}, "ts": {}, "note": {}}, dbms="cassandra",
        cassandra_partition=["user_id"], cassandra_cluster=["ts"],
    )
    report, _ = _validate(tmp_path, config)
    found = [(g.rule, g.where, g.examples[0].line, g.examples[0].column) for g in report.groups()]
    assert found == [
        ("empty_key", "cassandra · events", 3, "user_id"),
        ("empty_key", "cassandra · events", 4, "ts"),
    ]


def test_text_in_a_declared_bigint_is_an_error(tmp_path):
    amount = [str(i * 10) for i in range(10)]
    amount[3] = "n/a"  # the column is text; PostgreSQL would refuse it in BIGINT
    _write_csv(tmp_path / "ev.csv", ["id", "amount"], list(zip(range(10), amount)))
    config = _events_config({"id": {"is_key": True}, "amount": {"db_type": "BIGINT"}})
    report, _ = _validate(tmp_path, config)
    group = _only_group(report)
    assert (group.rule, group.where, group.count) == ("db_type", "postgres · events", 1)
    assert "amount" in group.detail and "BIGINT" in group.detail
    (ex,) = group.examples
    assert (ex.line, ex.column, ex.value, ex.reason) == (5, "amount", "n/a", "not an integer")


def test_a_value_out_of_the_cassandra_bigint_range_is_an_error(tmp_path):
    big = [str(i) for i in range(5)] + [str(2**64)]
    _write_csv(tmp_path / "ev.csv", ["user_id", "n"], [(f"u{i}", v) for i, v in enumerate(big)])
    config = _events_config({"user_id": {}, "n": {}}, dbms="cassandra",
                            cassandra_partition=["user_id"])
    report, _ = _validate(tmp_path, config)
    group = _only_group(report)
    assert (group.rule, group.where) == ("db_type", "cassandra · events")
    assert "bigint" in group.detail
    assert [(e.line, e.value, e.reason) for e in group.examples] == [
        (7, str(2**64), "out of bigint range")
    ]


def _int64_config():
    entity = {"source": "ev", "columns": {"id": {"is_key": True}, "n": {}}}
    return {"sources": {"ev": "ev.csv"},
            "mongodb": {"entities": {"events": dict(entity)}},
            "neo4j": {"entities": {"events": dict(entity)}},
            "redis": {"entities": {"events": dict(entity)}}}


def test_an_integer_beyond_64_bits_is_an_error_for_mongodb_and_neo4j(tmp_path):
    # BSON and the Neo4j packer refuse it in the middle of the write; Redis (JSON) takes it.
    n = ["5", "9223372036854775807", "12345678901234567890", "-9223372036854775808",
         "-9223372036854775809"]
    _write_csv(tmp_path / "ev.csv", ["id", "n"], list(zip(range(5), n)))
    report, _ = _validate(tmp_path, _int64_config())
    assert [(g.rule, g.where, g.count) for g in report.groups()] == [
        ("db_type", "mongodb · events", 2), ("db_type", "neo4j · events", 2),
    ]
    for group in report.groups():
        assert "n" in group.detail and "64-bit" in group.detail
        assert [(e.file, e.line, e.column, e.value, e.reason) for e in group.examples] == [
            ("ev.csv", 4, "n", "12345678901234567890", "out of 64-bit integer range"),
            ("ev.csv", 6, "n", "-9223372036854775809", "out of 64-bit integer range"),
        ]


def test_the_64_bit_limits_themselves_are_valid(tmp_path):
    n = ["5", "9223372036854775807", "-9223372036854775808"]
    _write_csv(tmp_path / "ev.csv", ["id", "n"], list(zip(range(3), n)))
    report, _ = _validate(tmp_path, _int64_config())
    assert report.ok(), _report_text(report)


def test_the_64_bit_rule_covers_mapped_columns_and_neo4j_relationship_properties(tmp_path):
    big = "12345678901234567890"
    # `other` is not mapped: nothing sends it. `quantity` is an edge property.
    _write_csv(tmp_path / "stock.csv", ["product_id"], [(1,), (2,)])
    _write_csv(tmp_path / "purchase.csv", ["user_id", "product_id", "order_number", "quantity", "other"],
               [("u1", 1, "o1", 1, big), ("u2", 2, "o2", big, big), ("u3", "", "o3", big, 1)])
    report, _ = _validate(tmp_path, _graph_config())
    group = _only_group(report)  # no edge for u3: its property is not sent
    assert (group.rule, group.where, group.count) == ("db_type", "neo4j · PURCHASED", 1)
    assert [(e.line, e.column, e.value) for e in group.examples] == [(3, "quantity", big)]


def _shop_config(customer_filters=None):
    customers = {"source": "customers", "columns": {"id": {"is_key": True}, "active": {}}}
    if customer_filters:
        customers["filters"] = customer_filters
    return {
        "sources": {"customers": "customers.csv", "orders": "orders.csv"},
        "postgres": {
            "entities": {
                "customers": customers,
                "orders": {
                    "source": "orders",
                    "columns": {"order_id": {"is_key": True}, "customer_id": {}},
                },
            },
            "relationships": {
                "order_customer": {
                    "from": "orders", "to": "customers",
                    "foreign_key": "customer_id", "references_key": "id",
                },
            },
        },
    }


def _write_shop(tmp_path, order_customers, ids=(1, 2, 3)):
    _write_csv(tmp_path / "customers.csv", ["id", "active"],
               list(zip(ids, ["yes", "no", "yes"])))
    _write_csv(tmp_path / "orders.csv", ["order_id", "customer_id"],
               [(f"o{i}", c) for i, c in enumerate(order_customers)])


def test_dangling_postgres_foreign_key_is_an_error(tmp_path):
    _write_shop(tmp_path, [1, 99, 3, 99, 98])
    report, _ = _validate(tmp_path, _shop_config())
    group = _only_group(report)
    assert (group.rule, group.where) == ("dangling_reference", "postgres · order_customer")
    assert group.count == 2  # distinct values: 99 twice counts once
    assert [(e.file, e.line, e.column, e.value) for e in group.examples] == [
        ("orders.csv", 3, "customer_id", "99"), ("orders.csv", 6, "customer_id", "98"),
    ]  # no db_type: both columns are TEXT, which stores the integers as their digits


def test_fk_to_a_row_the_target_filter_drops_is_dangling(tmp_path):
    _write_shop(tmp_path, [1, 2, 3])
    config = _shop_config([{"column": "active", "operator": "==", "value": "yes"}])
    report, _ = _validate(tmp_path, config)
    group = _only_group(report)
    assert group.rule == "dangling_reference"
    assert [(e.line, e.value) for e in group.examples] == [(3, "2")]


def test_references_compare_the_values_postgresql_stores(tmp_path):
    # customers.id is text (one key is "x9") and orders.customer_id integer, but neither
    # declares a db_type: both columns are TEXT, where PostgreSQL stores '1', '2', '7'.
    _write_shop(tmp_path, [1, 2, 7, 2], ids=(1, 2, "x9"))
    report, _ = _validate(tmp_path, _shop_config())
    group = _only_group(report)
    assert group.count == 1
    assert [(e.line, e.column, e.value) for e in group.examples] == [(4, "customer_id", "7")]


def test_references_compare_numbers_in_numeric_columns(tmp_path):
    _write_shop(tmp_path, ["1", "002", "5"])
    config = _shop_config()
    config["postgres"]["entities"]["customers"]["columns"]["id"]["db_type"] = "TEXT"
    config["postgres"]["entities"]["orders"]["columns"]["customer_id"]["db_type"] = "BIGINT"
    report, _ = _validate(tmp_path, config)  # '1' (TEXT) vs 1 (BIGINT): not the same
    assert [e.value for e in _only_group(report).examples] == [1, 2, 5]
    config["postgres"]["entities"]["customers"]["columns"]["id"]["db_type"] = "INTEGER"
    report, _ = _validate(tmp_path, config)  # 002 is stored as the number 2
    assert [e.value for e in _only_group(report).examples] == [5]


@pytest.mark.parametrize("ids", [(1, 2, 3), ("c1", "c2", "c3")])  # cast None, or text ""
def test_null_foreign_key_is_not_an_error(tmp_path, ids):
    _write_shop(tmp_path, [ids[0], "", ids[2]], ids)
    report, counts = _validate(tmp_path, _shop_config())
    assert report.ok()
    assert counts.written["postgres"] == {"customers": 3, "orders": 3}


def _graph_config():
    return {
        "sources": {"purchase": "purchase.csv", "stock": "stock.csv"},
        "neo4j": {
            "entities": {
                "User": {"source": "purchase", "columns": {"user_id": {"is_key": True}}},
                "Product": {"source": "stock", "columns": {"product_id": {"is_key": True}}},
            },
            "relationships": {
                "PURCHASED": {
                    "from": "User", "to": "Product", "type": "PURCHASED",
                    "columns": {"order_number": {"is_key": True}, "quantity": {}},
                },
            },
        },
    }


def _write_graph(tmp_path, purchases):
    _write_csv(tmp_path / "stock.csv", ["product_id"], [(1,), (2,), (3,)])
    _write_csv(tmp_path / "purchase.csv", ["user_id", "product_id", "order_number", "quantity"],
               purchases)


def test_dangling_neo4j_endpoint_is_an_error(tmp_path):
    _write_graph(tmp_path, [
        ("u1", 1, "o1", 1), ("u2", 99, "o2", 1), ("u3", "", "o3", 1), ("u1", 99, "o4", 2),
    ])
    report, counts = _validate(tmp_path, _graph_config())
    group = _only_group(report)
    assert (group.rule, group.where) == ("dangling_reference", "neo4j · PURCHASED")
    assert group.count == 2  # one per row; the empty endpoint is no relationship
    assert [(e.file, e.line, e.column, e.value) for e in group.examples] == [
        ("purchase.csv", 3, "product_id", 99), ("purchase.csv", 5, "product_id", 99),
    ]
    assert counts.written["neo4j"][":PURCHASED"] == 3  # the real sink's count: both ends set


def test_an_empty_text_endpoint_is_not_an_error(tmp_path):
    _write_csv(tmp_path / "stock.csv", ["product_id"], [("p1",), ("p2",)])
    _write_csv(tmp_path / "purchase.csv", ["user_id", "product_id", "order_number", "quantity"],
               [("u1", "p1", "o1", 1), ("u2", "", "o2", 1)])
    report, counts = _validate(tmp_path, _graph_config())
    assert report.ok()
    assert counts.written["neo4j"][":PURCHASED"] == 1  # only the edges that get created


@pytest.mark.parametrize("numbers", [("o1", "o4"), (1, 4)])  # text "", or cast None
def test_an_empty_relationship_merge_key_is_an_error(tmp_path, numbers):
    _write_graph(tmp_path, [
        ("u1", 1, numbers[0], 1), ("u2", 2, "", 1), ("u3", "", "", 1), ("u4", 3, numbers[1], 1),
    ])
    report, _ = _validate(tmp_path, _graph_config())
    group = _only_group(report)
    assert (group.rule, group.where) == ("empty_key", "neo4j · PURCHASED")
    assert "order_number" in group.detail
    # the row with an empty endpoint makes no edge, so its merge key does not matter
    assert [(e.file, e.line, e.column) for e in group.examples] == [
        ("purchase.csv", 3, "order_number")
    ]


def test_a_bad_property_on_a_row_that_makes_no_edge_is_not_an_error(tmp_path):
    _write_graph(tmp_path, [("u1", 1, "o1", "1"), ("u2", "", "o2", "n/a"), ("u3", 2, "o3", "3")])
    report, _ = _validate(tmp_path, _graph_config(), kinds={"quantity": "integer"})
    assert report.ok()


def test_an_unconvertible_relationship_property_is_an_error(tmp_path):
    quantity = [str(i) for i in range(10)]
    quantity[6] = "n/a"
    _write_graph(tmp_path, [(f"u{i}", 1 + i % 3, f"o{i}", q) for i, q in enumerate(quantity)])
    report, _ = _validate(tmp_path, _graph_config(), kinds={"quantity": "integer"})
    group = _only_group(report)
    assert (group.rule, group.where) == ("not_convertible", "neo4j · PURCHASED")
    assert "quantity" in group.detail
    assert [(e.line, e.column, e.value) for e in group.examples] == [(8, "quantity", "n/a")]


def test_at_most_five_examples_but_every_occurrence_counted(tmp_path):
    when = _dates(100)
    bad = list(range(3, 100, 8))[:12]
    for i in bad:
        when[i] = "2023-02-30"
    _write_csv(tmp_path / "ev.csv", ["id", "when"], list(zip(range(100), when)))
    report, _ = _validate(tmp_path, _events_config({"id": {"is_key": True}, "when": {}}))
    (g,) = report.groups()
    assert g.count == 12 and len(g.examples) == MAX_EXAMPLES == 5
    assert [e.line for e in g.examples] == [i + 2 for i in bad[:5]]
    assert report.total() == 12 and not report.ok()


def test_line_numbers_on_a_bom_crlf_file(tmp_path):
    when = _dates(10)
    when[2] = "not a date"  # data row 3
    text = "id,when\r\n" + "".join(f"{i},{w}\r\n" for i, w in enumerate(when))
    (tmp_path / "ev.csv").write_bytes(("\ufeff" + text).encode("utf-8"))
    report, _ = _validate(tmp_path, _events_config({"id": {"is_key": True}, "when": {}}))
    (ex,) = _only_group(report).examples
    assert (ex.line, ex.column, ex.value) == (4, "when", "not a date")


def test_data_validation_error_is_a_business_exception():
    assert issubclass(DataValidationError, BusinessException)


def test_report_groups_keep_the_order_of_first_occurrence():
    report = ValidationReport()
    for rule, where in [("b", "x"), ("a", "y"), ("b", "x"), ("a", "z")]:
        report.add(rule, where, "d", Example("f.csv", 2, "c", "v"))
    assert [(g.rule, g.where, g.count) for g in report.groups()] == [
        ("b", "x", 2), ("a", "y", 1), ("a", "z", 1),
    ]
    assert report.total() == 4


def test_print_validation_report_lists_each_group_with_its_examples(capsys, monkeypatch):
    monkeypatch.setattr(reporting, "_console", Console(width=200))  # no cell wrapping
    report = ValidationReport()
    report.add("db_type", "postgres · orders", "column 'amount' does not fit BIGINT",
               Example("orders.csv", 5, "amount", "n/a", "not an integer"))
    report.add("empty_key", "redis · cart", "key column 'id' is empty",
               Example("cart.csv", 9, "id", ""))
    print_validation_report(report)
    out = capsys.readouterr().out
    for text in ("Rule", "Where", "Count", "Examples", "postgres · orders", "db_type",
                 "orders.csv:5 amount=n/a (not an integer)", 'cart.csv:9 id=""'):
        assert text in out
    assert "┌" in out and "┏" not in out  # box.SQUARE


_DATE_DETAIL = "column 'order_date' does not convert to datetime"


def _narrow_report(capsys, monkeypatch, name, wheres):
    """The report of one date problem per place in ``wheres``, printed at 80 columns."""
    monkeypatch.setattr(reporting, "_console", Console(width=80, soft_wrap=True))
    report = ValidationReport()
    for where in wheres:
        report.add("not_convertible", where, _DATE_DETAIL,
                   Example(name, 1234, "order_date", "2023-11-31T14:30:00-05:00"))
    print_validation_report(report)
    return capsys.readouterr().out.splitlines()


def test_a_narrow_report_keeps_file_and_line_in_one_piece_for_a_usual_file_name(
    capsys, monkeypatch
):
    lines = _narrow_report(capsys, monkeypatch, "ecommerce_purchase.csv", ["postgres · orders"])
    assert max(len(line) for line in lines) <= 80
    assert any("ecommerce_purchase.csv:1234" in line for line in lines)


def test_a_narrow_report_folds_the_examples_instead_of_cutting_them(capsys, monkeypatch):
    # A file name longer than the Examples column must wrap inside the cell, never end in an
    # ellipsis, so file, line, column and value stay in the report.
    name = "ecommerce_purchase_with_a_very_long_file_name.csv"
    lines = _narrow_report(capsys, monkeypatch, name, ["postgres · orders", "cassandra · orders"])
    assert max(len(line) for line in lines) <= 80
    assert "…" not in "".join(lines)
    # The Examples cell of every row, line by line (header row left out), with the breaks
    # the wrapping added taken out: nothing is missing from the text.
    cells = [line.split("│")[-2] for line in lines if line.startswith("│")][1:]
    shown = "".join("".join(cells).split())
    full = f"{_DATE_DETAIL} {name}:1234 order_date=2023-11-31T14:30:00-05:00"
    assert shown == 2 * "".join(full.split())


class _RecordingSink:
    def __init__(self, cfg=None):
        pass

    def create_schema(self):
        pass

    def ensure_partition(self, partition_name, binding):
        pass

    def write_batch(self, partition_name, binding, batch):
        return len(batch)

    def close(self):
        pass


class _NeoDriver:
    """Just enough of a neo4j driver for the real ``Neo4jSink`` to run."""

    class _Session:
        def run(self, q, **params):
            return []

        def execute_write(self, fn):
            return fn(self)

    def session(self, database=None):
        return self._Session()

    def close(self):
        pass


def test_validation_counts_equal_the_write_counts(tmp_path):
    _write_csv(tmp_path / "stock.csv", ["product_id", "region", "ts"],
               [(i, "north" if i % 3 else "south", f"2023-01-{1 + i:02d}") for i in range(12)])
    _write_csv(tmp_path / "purchase.csv",
               ["user_id", "product_id", "order_number", "quantity", "ts"],
               [(f"u{i % 4}", "" if i == 5 else i % 12, f"o{i}", i, f"2023-02-{1 + i:02d}")
                for i in range(20)])
    config = {
        "sources": {"stock": "stock.csv", "purchase": "purchase.csv"},
        "postgres": {
            "entities": {
                "products": {"source": "stock", "columns": {"product_id": {"is_key": True}}},
                "orders": {"source": "purchase", "columns": {
                    "order_number": {"is_key": True}, "product_id": {}}},
                "regional": {"source": "stock", "columns": {"product_id": {"is_key": True}},
                             "filters": [{"column": "region", "operator": "each"}]},
            },
            "relationships": {"order_product": {
                "from": "orders", "to": "products",
                "foreign_key": "product_id", "references_key": "product_id"}},
        },
        "cassandra": {"entities": {"log": {
            "source": ["stock", "purchase"],
            "columns": {"ts": {}, "_source": {}, "product_id": {}},
            "cassandra_partition": ["ts"], "cassandra_cluster": ["_source"],
        }}},
        "redis": {"entities": {"buyers": {"source": "purchase",
                                          "columns": {"order_number": {"is_key": True}}}}},
        "neo4j": {
            "entities": {
                "User": {"source": "purchase", "columns": {"user_id": {"is_key": True}}},
                "Product": {"source": "stock", "columns": {"product_id": {"is_key": True}}},
            },
            "relationships": {"PURCHASED": {
                "from": "User", "to": "Product",
                "columns": {"order_number": {"is_key": True}, "quantity": {}}}},
        },
    }
    plan = plan_import(config, tmp_path, dbms_names=["postgres", "cassandra", "redis", "neo4j"])
    # Blocks of 5 and 6 rows: every count is summed over several chunks.
    plan = dataclasses.replace(plan, rows_per_chunk={"stock": 5, "purchase": 6})
    report, counts = validate_data(plan)
    fakes = {d: _RecordingSink for d in ("postgres", "cassandra", "redis")}
    fakes["neo4j"] = lambda cfg: Neo4jSink(cfg, driver_factory=lambda c: _NeoDriver())
    written = run_stream_import(plan, sink_factories=fakes)
    assert report.ok(), [(g.rule, g.where, g.detail) for g in report.groups()]
    assert counts.written == written.written
    assert counts.entity_rows == written.entity_rows
    assert counts.written["neo4j"][":PURCHASED"] == 19  # the empty product_id is no edge


def _report_text(report):
    return "\n".join(
        f"{g.rule} | {g.where} | {g.detail} | {g.count} | "
        + "; ".join(f"{e.file}:{e.line} {e.column}={e.value!r} ({e.reason})" for e in g.examples)
        for g in report.groups()
    )


def _all_dbms(config):
    return [b for b in BACKENDS if b in config]


@pytest.mark.parametrize("cfg_name", ["import_config.json", "import_config_combined.json"])
def test_the_ecommerce_examples_pass(cfg_name):
    config = load_import_config(ECOM / cfg_name)
    plan = plan_import(config, ECOM, dbms_names=_all_dbms(config))
    report, counts = validate_data(plan)
    assert report.ok(), _report_text(report)
    assert counts.written["neo4j"][":PURCHASED"] > 0


@pytest.mark.parametrize("mode", ["multi", "combined"])
def test_the_committed_reference_dataset_passes(mode):
    config = load_import_config(ECOM / _MODE_CONFIG[mode][0])
    plan = plan_import(config, ECOM, dbms_names=_all_dbms(config),
                       overrides=_overrides(mode, BENCH))
    report, counts = validate_data(plan)
    assert report.ok(), _report_text(report)
    assert sum(counts.written["postgres"].values()) > 0


_PROBE_CHUNK = 2048


def _validation_peak(base_dir, n_rows):
    # No relationships, and keys of bounded cardinality: nothing the checks keep grows
    # with the rows, so the peak is one read block plus the partition buffers.
    _write_csv(base_dir / "ev.csv", ["id", "when", "amount", "note"],
               [(i % 100, f"2023-01-{1 + i % 28:02d}", i, f"n{i}-{'x' * 20}")
                for i in range(n_rows)])
    config = {
        "sources": {"ev": "ev.csv"},
        "postgres": {"entities": {"ev": {"source": "ev", "columns": {
            "id": {"is_key": True, "db_type": "BIGINT"}, "when": {"db_type": "TIMESTAMPTZ"},
            "amount": {"db_type": "BIGINT"}, "note": {"db_type": "TEXT"}}}}},
        "redis": {"entities": {"ev": {"source": "ev", "columns": {"id": {"is_key": True}}}}},
    }
    plan = plan_import(config, base_dir, dbms_names=["postgres", "redis"])
    plan = dataclasses.replace(plan, rows_per_chunk={"ev": _PROBE_CHUNK})
    gc.collect()
    tracemalloc.start()
    tracemalloc.reset_peak()
    report, _ = validate_data(plan)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert report.ok()
    return peak


def test_validation_peak_does_not_scale_with_rows(tmp_path):
    (tmp_path / "small").mkdir()
    (tmp_path / "large").mkdir()
    small = _validation_peak(tmp_path / "small", 10_000)
    gc.collect()
    large = _validation_peak(tmp_path / "large", 40_000)
    assert large < 1.5 * small, f"peak {small} -> {large} ({large / small:.2f}x)"
