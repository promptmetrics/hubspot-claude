import pytest

from hubspot_agent.cache import SchemaCache
from hubspot_agent.validation import ValidationError, validate_properties, _type_compatible


@pytest.fixture
def cache(tmp_path):
    cache = SchemaCache("123", base_dir=tmp_path)
    cache.set(
        "contacts",
        {
            "results": [
                {"name": "email", "type": "string"},
                {"name": "phone", "type": "string"},
                {"name": "age", "type": "number"},
                {"name": "is_customer", "type": "bool"},
                {"name": "lifecyclestage", "type": "enumeration"},
                {"name": "createdate", "type": "date"},
            ]
        },
    )
    return cache


def test_validation_all_valid(cache, tmp_path):
    result = validate_properties(
        "contacts",
        {"email": "test@example.com", "age": 30, "is_customer": True},
        "123",
        base_dir=tmp_path,
    )
    assert result["valid"] is True
    assert result["errors"] == []


def test_validation_unknown_property(cache, tmp_path):
    result = validate_properties(
        "contacts",
        {"emial": "test@example.com"},
        "123",
        base_dir=tmp_path,
    )
    assert result["valid"] is False
    assert result["errors"][0]["reason"] == "unknown_property"
    assert "email" in result["errors"][0]["suggestions"]


def test_validation_type_mismatch_string(cache, tmp_path):
    result = validate_properties(
        "contacts",
        {"age": "thirty"},
        "123",
        base_dir=tmp_path,
    )
    assert result["valid"] is False
    assert "type_mismatch" in result["errors"][0]["reason"]


def test_validation_type_mismatch_bool(cache, tmp_path):
    result = validate_properties(
        "contacts",
        {"is_customer": "yes"},
        "123",
        base_dir=tmp_path,
    )
    assert result["valid"] is False
    assert "type_mismatch" in result["errors"][0]["reason"]


def test_validation_no_schema(tmp_path):
    result = validate_properties(
        "contacts",
        {"email": "test@example.com"},
        "123",
        base_dir=tmp_path,
    )
    assert result["valid"] is True
    assert result["errors"] == []


def test_type_compatible_string():
    assert _type_compatible("hello", "string") is True
    assert _type_compatible(123, "string") is False


def test_type_compatible_number():
    assert _type_compatible(42, "number") is True
    assert _type_compatible(3.14, "number") is True
    assert _type_compatible(True, "number") is False
    assert _type_compatible("42", "number") is False


def test_type_compatible_bool():
    assert _type_compatible(True, "bool") is True
    assert _type_compatible(False, "bool") is True
    assert _type_compatible("true", "bool") is False


def test_type_compatible_none():
    assert _type_compatible(None, "string") is True
    assert _type_compatible(None, "number") is True
    assert _type_compatible(None, "bool") is True


def test_validation_allows_none_value(cache, tmp_path):
    result = validate_properties(
        "contacts",
        {"email": None},
        "123",
        base_dir=tmp_path,
    )
    assert result["valid"] is True
    assert result["errors"] == []
