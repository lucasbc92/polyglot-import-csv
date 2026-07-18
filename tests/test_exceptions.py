"""Shallow exception hierarchy: category types under BusinessException."""

import pytest

from polyglotimportcsv.business_exception import (
    BusinessException,
    ConfigError,
    ImportExecutionError,
    MappingError,
    SourceError,
)


@pytest.mark.parametrize(
    "exc_type", [ConfigError, SourceError, MappingError, ImportExecutionError]
)
def test_categories_subclass_business_exception(exc_type):
    assert issubclass(exc_type, BusinessException)
    with pytest.raises(BusinessException):
        raise exc_type("boom")


def test_message_is_preserved():
    try:
        raise SourceError("file not found: x.csv")
    except BusinessException as e:
        assert "x.csv" in str(e)
