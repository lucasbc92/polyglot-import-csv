"""Every backend must shape rows inside its own 'write' timer (spec §4.5)."""

import inspect

from polyglotimportcsv.importers import mongodb_importer


def test_mongodb_builds_documents_inside_write_timer():
    src = inspect.getsource(mongodb_importer.run_mongodb_import)
    write_at = src.index('timed_phase("mongodb", part_name, "write")')
    docs_at = src.index("mongo_document_from_row")
    # The doc-building call must appear after the write timer opens, not before.
    assert docs_at > write_at, "MongoDB builds payloads before its write timer opens"
