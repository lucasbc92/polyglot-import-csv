"""The validation read: the rows of every entity checked before anything is written.

``validate_data`` runs the write's own engine (``stream_runner.run_single_pass``) over
the plan, with sinks that write nothing. Each one sees, through the engine's inspect
hooks, the rows its real sink would get, after the same filters, casting and ``each``
split, and adds every problem to one ``ValidationReport``. The report counts every
occurrence and keeps a few examples of each problem, each with file, line, column and
value; the counts the engine returns are those the write will produce.

The rules: a value that does not convert to its column's inferred kind
(``not_convertible``), a value its DBMS type would refuse (``db_type``), an empty key
(``empty_key``), and a reference to a row or node the import will not hold
(``dangling_reference``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd
from rich import box
from rich.table import Table
from rich.text import Text

from polyglotimportcsv.db_type_checks import cassandra_value_problem, postgres_value_problem
from polyglotimportcsv.dbms_sink import DbmsSink
from polyglotimportcsv.entity_utils import (
    flat_leaf_columns,
    iter_leaf_columns,
    resolve_csv_column,
    target_field_name,
)
from polyglotimportcsv.import_plan import ImportPlan
from polyglotimportcsv.importers.cassandra_importer import _cassandra_column_plan
from polyglotimportcsv.importers.neo4j_importer import _rel_rows_for_batch
from polyglotimportcsv.materialize import cell_scalar
from polyglotimportcsv.reporting import print_rich
from polyglotimportcsv.stream_binding import EntityBinding
from polyglotimportcsv.stream_runner import StreamCounts, run_single_pass

#: Examples kept per problem group; every occurrence is still counted.
MAX_EXAMPLES = 5

#: The DBMS whose ``is_key`` columns must hold a value. MongoDB ignores ``is_key``.
_KEY_DBMS = frozenset({"postgres", "redis", "neo4j"})

#: Kinds whose cast can fail; boolean and string casts always succeed.
_CONVERTED_KINDS = frozenset({"integer", "float", "datetime"})


@dataclass
class Example:
    """One occurrence of a problem.

    ``line`` is the header line plus the data-record number (``index + 2``): the
    physical line of the file when it has no blank lines and no field spanning lines.
    ``value`` is the text in the file, or for a reference the value compared.
    """

    file: str
    line: int
    column: str
    value: Any
    reason: str = ""


@dataclass
class ProblemGroup:
    """Every occurrence of one problem in one place: a count and the first examples."""

    rule: str
    where: str
    detail: str
    count: int = 0
    examples: List[Example] = field(default_factory=list)


class ValidationReport:
    """The problems a validation read found, grouped by ``(rule, where, detail)``."""

    def __init__(self) -> None:
        self._groups: Dict[Tuple[str, str, str], ProblemGroup] = {}

    def add(self, rule: str, where: str, detail: str, example: Example) -> None:
        """Count one occurrence; keep it as an example while the group has fewer than
        ``MAX_EXAMPLES``."""
        group = self._groups.get((rule, where, detail))
        if group is None:
            group = self._groups[(rule, where, detail)] = ProblemGroup(rule, where, detail)
        group.count += 1
        if len(group.examples) < MAX_EXAMPLES:
            group.examples.append(example)

    def groups(self) -> List[ProblemGroup]:
        """The groups in the order of their first occurrence."""
        return list(self._groups.values())

    def ok(self) -> bool:
        return not self._groups

    def total(self) -> int:
        return sum(group.count for group in self._groups.values())


def _line(index: Any) -> int:
    return int(index) + 2


def _scalar(value: Any) -> Any:
    """The value a sink sends for a cast cell, with every null-like (NaN, NaT, pd.NA)
    as ``None``."""
    value = cell_scalar(value)
    return None if pd.api.types.is_scalar(value) and pd.isna(value) else value


def _reference(value: Any) -> Any:
    """A cast cell as a reference compares it, ``None`` when empty: an empty foreign
    key or endpoint means there is no relationship."""
    value = _scalar(value)
    return None if isinstance(value, str) and value == "" else value


def _unconverted(raw: pd.Series, cast: pd.Series, kind: str) -> pd.Series:
    """Mask of the cells whose text is not empty but did not convert to ``kind``.

    A failed integer or float cast leaves the original text; a failed datetime cast
    leaves ``None`` (``casting.cast_frame``).
    """
    if kind == "datetime":
        failed = cast.isna()
    else:
        failed = cast.map(lambda v: isinstance(v, str)).astype(bool)
    return (raw != "") & failed


def _check_convertible(
    report: ValidationReport,
    where: str,
    file_label: str,
    kinds: Dict[str, str],
    raw: pd.DataFrame,
    cast: pd.DataFrame,
    columns: Sequence[str],
) -> None:
    for col in dict.fromkeys(columns):
        kind = kinds.get(col, "string")
        if kind not in _CONVERTED_KINDS:
            continue
        detail = f"column '{col}' does not convert to {kind}"
        for idx in cast.index[_unconverted(raw[col], cast[col], kind).to_numpy()]:
            report.add("not_convertible", where, detail,
                       Example(file_label, _line(idx), col, raw.at[idx, col]))


def _key_columns(dbms: str, binding: EntityBinding, columns: List[str]) -> List[Tuple[str, str]]:
    """``(column, label)`` of every column of the entity that must hold a value."""
    if dbms == "cassandra":
        return [(c, "partition") for c in binding.cfg.get("cassandra_partition") or []] + [
            (c, "cluster") for c in binding.cfg.get("cassandra_cluster") or []
        ]
    if dbms in _KEY_DBMS:
        return [
            (resolve_csv_column(fk, spec, columns), "key")
            for _, fk, spec in iter_leaf_columns(binding.cfg)
            if spec.get("is_key")
        ]
    return []


def _check_values(
    report: ValidationReport,
    where: str,
    detail: str,
    file_label: str,
    raw: pd.DataFrame,
    cast: pd.DataFrame,
    col: str,
    problem: Callable[[Any], Optional[str]],
) -> None:
    # Columns repeat their values (statuses, prices, dates), so each distinct cell is
    # checked once per block; the type is in the key so that True and 1 stay apart.
    verdicts: Dict[Tuple[type, Any], Optional[str]] = {}
    for idx, cell in cast[col].items():
        key = (type(cell), cell)
        if key not in verdicts:
            value = _scalar(cell)
            verdicts[key] = None if value is None else problem(value)
        reason = verdicts[key]
        if reason is not None:
            report.add("db_type", where, detail,
                       Example(file_label, _line(idx), col, raw.at[idx, col], reason))


def check_rows(
    report: ValidationReport,
    dbms: str,
    file_label: str,
    entity: str,
    binding: EntityBinding,
    raw: pd.DataFrame,
    cast: pd.DataFrame,
) -> None:
    """Check the rows of ``entity`` its ``dbms`` sink would write; add the problems.

    ``raw`` holds the filtered, uncast text and ``cast`` the same rows cast, both indexed
    by the position of each data record in the file ``file_label``. Every row is
    checked: after the entity's filters, before any deduplication by the sink.

    - ``not_convertible``: in a mapped column, or the column of an ``each`` filter, a
      non-empty text that did not convert to the column's integer, float or datetime
      kind;
    - ``empty_key``: an empty ``is_key`` column (PostgreSQL, Redis, Neo4j), or an empty
      partition or cluster column (Cassandra);
    - ``db_type``: a value its column's declared PostgreSQL type, or its Cassandra CQL
      type, would refuse.
    """
    if cast.empty:
        return
    where = f"{dbms} · {entity}"
    columns = list(cast.columns)
    leaves = [
        (spec, resolve_csv_column(fk, spec, columns))
        for _, fk, spec in iter_leaf_columns(binding.cfg)
    ]
    each = [f["column"] for f in binding.cfg.get("filters") or [] if f.get("operator") == "each"]
    _check_convertible(report, where, file_label, binding.kinds, raw, cast,
                       [col for _, col in leaves] + each)

    for col, label in dict.fromkeys(_key_columns(dbms, binding, columns)):
        values = cast[col]
        for idx in cast.index[(values.isna() | (values == "")).to_numpy()]:
            report.add("empty_key", where, f"{label} column '{col}' is empty",
                       Example(file_label, _line(idx), col, raw.at[idx, col]))

    if dbms == "postgres":
        for spec, col in leaves:
            db_type = spec.get("db_type")
            if db_type:
                _check_values(report, where, f"column '{col}' does not fit {db_type}",
                              file_label, raw, cast, col,
                              lambda v, t=db_type: postgres_value_problem(t, v))
    elif dbms == "cassandra":
        cql_by_src = _cassandra_column_plan(binding.cfg, binding.kinds, columns)[3]
        for col, cql in cql_by_src.items():
            _check_values(report, where, f"column '{col}' does not fit CQL {cql}",
                          file_label, raw, cast, col,
                          lambda v, t=cql: cassandra_value_problem(t, v))


def _target_column(binding: EntityBinding, target: str, columns: List[str]) -> str:
    """The CSV column of the leaf whose target field is ``target``."""
    return next(
        resolve_csv_column(fk, spec, columns)
        for _, fk, spec in iter_leaf_columns(binding.cfg)
        if target_field_name(fk, spec) == target
    )


def _key_leaf(binding: EntityBinding) -> Tuple[str, Dict[str, Any]]:
    """``(field_key, spec)`` of the entity's single ``is_key`` leaf (Neo4j)."""
    return [(fk, sp) for fk, _, sp in flat_leaf_columns(binding.cfg) if sp.get("is_key")][0]


class CheckingSink:
    """A ``DbmsSink`` that connects to nothing: it checks the rows its DBMS would get.

    Rows arrive through ``inspect_rows`` and go to ``check_rows``. For PostgreSQL it
    also keeps, per relationship, the distinct ``references_key`` values of the ``to``
    entity and the first file and line of each distinct ``foreign_key`` value of the
    ``from`` entity; ``close()`` reports every foreign key value the ``to`` entity does
    not hold, as the foreign key ``PostgresSink.close()`` adds would refuse it.
    """

    def __init__(self, dbms: str, plan: ImportPlan, report: ValidationReport) -> None:
        self.dbms = dbms
        self.plan = plan
        self.report = report
        # The partition name is not the entity's when an `each` filter splits it.
        self._entity_of = {id(b): ename for ename, b in plan.bindings[dbms].items()}
        rels = (plan.config[dbms].get("relationships") or {}) if dbms == "postgres" else {}
        self._fk_rels: Dict[str, Dict[str, Any]] = rels
        self._referenced: Dict[str, Set[Any]] = {rname: set() for rname in rels}
        self._fk_column: Dict[str, str] = {}
        self._fk_first: Dict[str, Dict[Any, Tuple[str, int]]] = {rname: {} for rname in rels}

    def create_schema(self) -> None:
        """Nothing to create."""

    def ensure_partition(self, partition_name: str, binding: EntityBinding) -> None:
        """Nothing to create."""

    def write_batch(self, partition_name: str, binding: EntityBinding, batch: pd.DataFrame) -> int:
        return len(batch)

    def _file_label(self, source: str) -> str:
        return self.plan.profiles[source].path.name

    def inspect_rows(
        self, source: str, partition: str, binding: EntityBinding,
        raw: pd.DataFrame, cast: pd.DataFrame,
    ) -> None:
        file_label = self._file_label(source)
        check_rows(self.report, self.dbms, file_label, self._entity_of[id(binding)],
                   binding, raw, cast)
        columns = list(cast.columns)
        for rname, rspec in self._fk_rels.items():
            fk = rspec["foreign_key"]
            if partition == rspec["to"]:
                col = _target_column(binding, rspec.get("references_key") or fk, columns)
                self._referenced[rname].update(
                    v for v in map(_reference, cast[col]) if v is not None
                )
            if partition == rspec["from"]:
                col = self._fk_column[rname] = _target_column(binding, fk, columns)
                first = self._fk_first[rname]
                for idx, value in cast[col].items():
                    value = _reference(value)
                    if value is not None and value not in first:
                        first[value] = (file_label, _line(idx))

    def close(self) -> None:
        for rname, rspec in self._fk_rels.items():
            fk = rspec["foreign_key"]
            to, refk = rspec["to"], rspec.get("references_key") or fk
            referenced = self._referenced[rname]
            detail = f"{rspec['from']}.{fk} -> {to}.{refk}: value not found"
            for value, (file_label, line) in self._fk_first[rname].items():
                if value not in referenced:
                    self.report.add(
                        "dangling_reference", f"{self.dbms} · {rname}", detail,
                        Example(file_label, line, self._fk_column[rname], value,
                                f"not in {to}.{refk}"),
                    )


class Neo4jCheckingSink(CheckingSink):
    """``CheckingSink`` for Neo4j, which also checks the relationships.

    It keeps the distinct keys of every entity a relationship links, and reports each
    relationship row whose endpoints are both set but one names no node of its entity:
    the ``MATCH`` of ``Neo4jSink`` would create no edge for it, without a word.
    """

    def __init__(self, dbms: str, plan: ImportPlan, report: ValidationReport) -> None:
        super().__init__(dbms, plan, report)
        self._rels: Dict[str, Dict[str, Any]] = plan.config[dbms].get("relationships") or {}
        self._node_keys: Dict[str, Set[Any]] = {
            rspec[end]: set() for rspec in self._rels.values() for end in ("from", "to")
        }

    def inspect_rows(
        self, source: str, partition: str, binding: EntityBinding,
        raw: pd.DataFrame, cast: pd.DataFrame,
    ) -> None:
        super().inspect_rows(source, partition, binding, raw, cast)
        columns = list(cast.columns)
        keys = self._node_keys.get(partition)
        if keys is not None:
            col = resolve_csv_column(*_key_leaf(binding), columns)
            keys.update(v for v in map(_reference, cast[col]) if v is not None)
        # A relationship's properties come from its `from` entity's rows, the same rows
        # as here (an entity a relationship links has no `each` split): they are checked
        # now, while the raw text is at hand to tell an empty cell from a failed cast.
        for rname, rspec in self._rels.items():
            if rspec["from"] == partition:
                props = [resolve_csv_column(fk, spec, columns)
                         for fk, spec in (rspec.get("columns") or {}).items()]
                _check_convertible(self.report, f"{self.dbms} · {rname}",
                                   self._file_label(source), binding.kinds, raw, cast, props)

    def inspect_relationship_rows(
        self, source: str, rname: str, rspec: Dict[str, Any],
        from_binding: EntityBinding, to_binding: EntityBinding, cast: pd.DataFrame,
    ) -> None:
        columns = list(cast.columns)
        ends = [
            (rspec[end], resolve_csv_column(*_key_leaf(b), columns))
            for end, b in (("from", from_binding), ("to", to_binding))
        ]
        file_label = self._file_label(source)
        rel_type = rspec.get("type") or rname
        detail = f"({rspec['from']})-[:{rel_type}]->({rspec['to']}): node not found"
        values = [cast[col] for _, col in ends]
        for idx, a, b in zip(cast.index, *values):
            pair = (_reference(a), _reference(b))
            if None in pair:
                continue
            for (entity, col), value in zip(ends, pair):
                if value not in self._node_keys[entity]:
                    self.report.add(
                        "dangling_reference", f"{self.dbms} · {rname}", detail,
                        Example(file_label, _line(idx), col, value, f"no {entity} with this key"),
                    )
                    break

    def write_relationships(
        self, rname: str, rspec: Dict[str, Any],
        from_binding: EntityBinding, to_binding: EntityBinding, batch: pd.DataFrame,
    ) -> int:
        """The count ``Neo4jSink.write_relationships`` returns for the same rows."""
        columns = list(batch.columns)
        from_src = resolve_csv_column(*_key_leaf(from_binding), columns)
        to_src = resolve_csv_column(*_key_leaf(to_binding), columns)
        rel_cols = rspec.get("columns") or {}
        mk_names = [
            target_field_name(fk, spec) for fk, spec in rel_cols.items() if spec.get("is_key")
        ]
        return len(_rel_rows_for_batch(batch, from_src, to_src, rel_cols, mk_names))


def validate_data(
    plan: ImportPlan,
    *,
    on_batch: Optional[Callable[[str, str, pd.DataFrame], None]] = None,
) -> Tuple[ValidationReport, StreamCounts]:
    """Check every row the plan would write, writing nothing.

    One checking sink per DBMS of the plan (``Neo4jCheckingSink`` for Neo4j) runs under
    ``run_single_pass``, so one read of the sources serves them all. Returns the report
    and the row counts, the same the write produces. ``on_batch`` is passed through.
    """
    report = ValidationReport()
    sinks: Dict[str, DbmsSink] = {
        dbms: (Neo4jCheckingSink if dbms == "neo4j" else CheckingSink)(dbms, plan, report)
        for dbms in plan.dbms_names
    }
    counts = run_single_pass(plan, sinks, on_batch=on_batch)
    return report, counts


def _shown(value: Any) -> str:
    return '""' if value is None or value == "" else str(value)


def _example_text(example: Example) -> str:
    text = f"{example.file}:{example.line} {example.column}={_shown(example.value)}"
    return f"{text} ({example.reason})" if example.reason else text


def print_validation_report(report: ValidationReport) -> None:
    """Print one table row per problem group, with its count and examples."""
    # box.SQUARE for the same reason as reporting.metrics_table: the GUI font lacks
    # the heavy box glyphs.
    table = Table(title="Data validation problems", header_style="bold", box=box.SQUARE)
    table.add_column("Rule")
    table.add_column("Where")
    table.add_column("Count", justify="right")
    table.add_column("Examples")
    for group in report.groups():
        rule = Text(group.rule)
        rule.append(f"\n{group.detail}", style="dim")
        table.add_row(
            rule,
            Text(group.where),
            str(group.count),
            Text("\n".join(_example_text(e) for e in group.examples)),
        )
    print_rich(table, level=logging.ERROR)
