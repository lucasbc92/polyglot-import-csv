"""Cassandra bulk loads survive a transient stall instead of aborting the run.

A node busy flushing or compacting can stop answering for longer than the driver's
default 10s request timeout. Without a configured timeout and a retry, one slow
response raises OperationTimedOut and kills a benchmark matrix that has already
been running for half an hour.
"""

import pytest

import polyglotimportcsv.importers.cassandra_importer as ci
from polyglotimportcsv.business_exception import ImportExecutionError


class _Timeout(Exception):
    """Stands in for cassandra.OperationTimedOut (driver may be absent in CI)."""


def _concurrent_failing(fail_for, *, exc=None):
    """execute_concurrent_with_args stub: rows in ``fail_for`` fail on each call.

    ``fail_for`` is mutated by the caller between attempts to simulate a stall
    that clears. Records the params it was asked to write, per call.
    """
    seen = []

    def fake(session, prepared, params, concurrency=64, raise_on_first_error=True, **kw):
        params = list(params)
        seen.append(params)
        return [
            (False, exc or _Timeout("client request timeout"))
            if p in fail_for else (True, None)
            for p in params
        ]

    fake.seen = seen
    return fake


def _rows(n):
    return [[f"u{i}"] for i in range(n)]


def test_write_batched_retries_only_the_failed_rows(monkeypatch):
    rows = _rows(5)
    failing = [rows[2]]
    fake = _concurrent_failing(failing)
    monkeypatch.setattr(ci, "execute_concurrent_with_args", fake)

    def clear_after_first_attempt(_seconds):
        failing.clear()  # the node recovers before the retry

    written = ci._write_batched(
        object(), object(), rows, lambda n: None, sleep=clear_after_first_attempt
    )

    assert written == 5
    assert fake.seen[0] == rows          # first attempt: everything
    assert fake.seen[1] == [rows[2]]     # retry: only what failed
    assert len(fake.seen) == 2


def test_write_batched_does_not_retry_when_all_rows_succeed(monkeypatch):
    fake = _concurrent_failing([])
    monkeypatch.setattr(ci, "execute_concurrent_with_args", fake)

    written = ci._write_batched(object(), object(), _rows(3), lambda n: None)

    assert written == 3
    assert len(fake.seen) == 1  # no wasted round-trip


def test_write_batched_gives_up_after_the_retry_budget(monkeypatch):
    rows = _rows(4)
    fake = _concurrent_failing(rows)  # never recovers
    monkeypatch.setattr(ci, "execute_concurrent_with_args", fake)

    with pytest.raises(ImportExecutionError) as excinfo:
        ci._write_batched(
            object(), object(), rows, lambda n: None, retries=2, sleep=lambda s: None
        )

    msg = str(excinfo.value)
    assert "4" in msg and "3 attempt" in msg  # rows still failing, attempts made
    assert len(fake.seen) == 3  # initial attempt + 2 retries


def test_write_batched_backs_off_between_attempts(monkeypatch):
    rows = _rows(2)
    monkeypatch.setattr(ci, "execute_concurrent_with_args", _concurrent_failing(rows))
    delays = []

    with pytest.raises(ImportExecutionError):
        ci._write_batched(
            object(), object(), rows, lambda n: None,
            retries=3, sleep=delays.append,
        )

    # Backoff grows: hammering a node that is already stalling makes it worse.
    assert delays == sorted(delays) and len(set(delays)) > 1


def test_write_batched_advances_progress_by_the_full_batch(monkeypatch):
    rows = _rows(6)
    failing = [rows[0]]
    monkeypatch.setattr(ci, "execute_concurrent_with_args", _concurrent_failing(failing))
    advanced = []

    ci._write_batched(
        object(), object(), rows, advanced.append,
        sleep=lambda s: failing.clear(),
    )

    assert sum(advanced) == 6  # retried rows are not double-counted


def test_write_batched_tolerates_a_driver_returning_no_results(monkeypatch):
    """Older/stubbed drivers return an empty list; that must not read as failure."""
    def fake(session, prepared, params, concurrency=64, **kw):
        return []

    monkeypatch.setattr(ci, "execute_concurrent_with_args", fake)
    assert ci._write_batched(object(), object(), _rows(3), lambda n: None) == 3


def test_request_timeout_defaults_above_the_driver_default():
    # The driver's own default is 10s, which a flushing node exceeds under load.
    assert ci._request_timeout({}) == ci.DEFAULT_REQUEST_TIMEOUT
    assert ci.DEFAULT_REQUEST_TIMEOUT > 10.0


def test_request_timeout_reads_the_connection_block():
    assert ci._request_timeout({"request_timeout": 45}) == 45.0


def test_request_timeout_rejects_a_nonsense_value():
    with pytest.raises(ImportExecutionError, match="request_timeout"):
        ci._request_timeout({"request_timeout": 0})
