import logging
import re

import pytest

from dictlens import core
from dictlens.core import (
    _validate_pattern,
    _compile_patterns,
    _get_tolerances_for_path,
    _remove_ignored_by_path,
    _format_path,
    _match_pattern,
    _is_number, _deep_compare,
)


# --------------------------------------------------------------------------
# _is_number
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (42, True),
    (-100, True),
    (0, True),
    (3.14, True),
    (-2.5, True),
    (0.0, True),
    (True, False),
    (False, False),
    ("123", False),
    ("3.14", False),
    (None, False),
    ([1, 2, 3], False),
    ({"a": 1}, False),
])
def test_is_number(value, expected):
    """Should correctly detect numeric types and reject others."""
    assert _is_number(value) == expected


# --------------------------------------------------------------------------
# _validate_pattern
# --------------------------------------------------------------------------

@pytest.mark.parametrize("pattern", [
    "$.a.b",
    "$.items[0].price",
    "$.items[*].price",
    "$.data.*.value",
])
def test_validate_pattern_valid(pattern):
    """Should accept all allowed JSONPath-like formats."""
    _validate_pattern(pattern)  # no exception


@pytest.mark.parametrize("pattern", [
    "$..a",  # recursive descent not supported
    "a.b",  # missing leading $
    "$.a..b",  # invalid double dots
    "$.items[abc]",  # invalid index
    "$.data[1.2]",  # invalid index type
    123,  # wrong type
    None,  # not a string
])
def test_validate_pattern_invalid(pattern):
    """Should raise ValueError or TypeError for invalid syntax."""
    if isinstance(pattern, str):
        with pytest.raises(ValueError):
            _validate_pattern(pattern)
    else:
        with pytest.raises(TypeError):
            _validate_pattern(pattern)


# --------------------------------------------------------------------------
# _compile_patterns
# --------------------------------------------------------------------------

def test_compile_patterns_valid():
    """Should compile valid patterns into regex objects."""
    patterns = ["$.data[*].value", "$.items[0].price"]
    compiled = _compile_patterns(patterns)
    assert len(compiled) == 2
    assert all(isinstance(rx, re.Pattern) for rx in compiled)
    assert compiled[0].match("$.data[3].value")


def test_compile_patterns_invalid(monkeypatch, caplog):
    """Should skip invalid patterns but not crash."""
    with caplog.at_level(logging.WARNING):
        compiled = _compile_patterns(["invalid", "$.a..b"])
        assert compiled == []  # both skipped
        assert any("Ignoring invalid pattern" in m for m in caplog.messages)


# --------------------------------------------------------------------------
# _get_tolerances_for_path
# --------------------------------------------------------------------------

def test_get_tolerances_for_path_exact_match():
    """Exact match in tolerance dicts should override defaults."""
    abs_fields = {"$.a.b": 0.2}
    rel_fields = {"$.a.b": 0.05}
    abs_tol, rel_tol = _get_tolerances_for_path("$.a.b", 0.0, 0.0, abs_fields, rel_fields)
    assert abs_tol == 0.2
    assert rel_tol == 0.05


def test_get_tolerances_for_path_pattern_match():
    """Pattern match should apply when exact key not found."""
    abs_fields = {"$.a[*].b": 0.3}
    rel_fields = {"$.a[*].b": 0.1}
    abs_tol, rel_tol = _get_tolerances_for_path("$.a[1].b", 0.0, 0.0, abs_fields, rel_fields)
    assert abs_tol == 0.3
    assert rel_tol == 0.1


def test_get_tolerances_for_path_no_match_defaults():
    """Should fall back to provided default tolerances."""
    abs_tol, rel_tol = _get_tolerances_for_path("$.missing", 0.1, 0.05, {}, {})
    assert abs_tol == 0.1
    assert rel_tol == 0.05


def test_get_tolerances_for_path_exact_takes_precedence():
    """Exact match should override wildcard patterns."""
    abs_fields = {"$.user.age": 0.5, "$.users[*].age": 0.8}
    abs_tol, rel_tol = _get_tolerances_for_path("$.user.age", 0.1, 0.01, abs_fields, {})
    assert abs_tol == 0.5


def test_get_tolerances_for_path_invalid(monkeypatch, caplog):
    """Should log a warning but not crash on internal error."""
    with caplog.at_level(logging.WARNING):
        monkeypatch.setattr(core, "_match_pattern", lambda *_: (_ for _ in ()).throw(ValueError("oops")))
        _ = _get_tolerances_for_path("$.a.b", 0.1, 0.05, {"$.x.y": 1}, {"$.y.z": 2})
        assert any("Failed to resolve tolerances" in msg for msg in caplog.messages)


# --------------------------------------------------------------------------
# _remove_ignored_by_path
# --------------------------------------------------------------------------

def test_remove_ignored_by_path_simple_dict():
    """Should remove ignored key by pattern."""
    obj = {"a": 1, "b": 2}
    patterns = _compile_patterns(["$.b"])
    result = _remove_ignored_by_path(obj, patterns)
    assert result == {"a": 1}


def test_remove_ignored_by_path_nested_dict():
    """Should handle nested paths correctly."""
    obj = {"a": {"b": {"c": 3}}, "x": 1}
    patterns = _compile_patterns(["$.a.b"])
    result = _remove_ignored_by_path(obj, patterns)
    assert result == {"a": {}, "x": 1}


def test_remove_ignored_by_path_list_elements():
    """Should remove matching list items."""
    obj = {"data": [1, 2, 3]}
    patterns = _compile_patterns(["$.data[1]"])
    result = _remove_ignored_by_path(obj, patterns)
    assert result == {"data": [1, 3]}


def test_remove_ignored_by_path_nested_list():
    """Should correctly recurse through lists of dicts."""
    obj = {"items": [{"id": 1}, {"id": 2}, {"id": 3}]}
    patterns = _compile_patterns(["$.items[*].id"])
    result = _remove_ignored_by_path(obj, patterns)
    assert result == {"items": [{}, {}, {}]}  # IDs removed


def test_remove_ignored_by_path_mixed_list():
    """Should handle mixed structures inside lists."""
    obj = {"mixed": [{"a": 1, "b": 2}, {"b": 3, "c": 4}]}
    patterns = _compile_patterns(["$.mixed[*].b"])
    result = _remove_ignored_by_path(obj, patterns)
    assert result == {"mixed": [{"a": 1}, {"c": 4}]}


def test_remove_ignored_by_path_graceful_failure(monkeypatch, caplog):
    """Should log warning but not raise on internal exception."""
    with caplog.at_level(logging.WARNING):
        monkeypatch.setattr(core, "_path_matches_any", lambda *_: (_ for _ in ()).throw(ValueError("fail")))
        _remove_ignored_by_path({"a": 1}, [])
        assert any("Ignoring path" in msg for msg in caplog.messages)


# --------------------------------------------------------------------------
# _format_path
# --------------------------------------------------------------------------

@pytest.mark.parametrize("path,expected", [
    ((), "$."),
    (("a",), "$.a"),
    (("a", "b"), "$.a.b"),
    (("data", 0, "value"), "$.data[0].value"),
    ((0,), "$.[0]"),
    (("data", 0, 1, "value"), "$.data[0][1].value"),
    (("item1", "sub2", "val3"), "$.item1.sub2.val3"),
])
def test_format_path_various(path, expected):
    """Should format tuple paths correctly to JSONPath strings."""
    assert _format_path(path) == expected


# --------------------------------------------------------------------------
# _match_pattern
# --------------------------------------------------------------------------

@pytest.mark.parametrize("pattern,path,expected", [
    ("$.a.b", "$.a.b", True),
    ("$.a.b", "$.a.c", False),
    ("$.items[0].price", "$.items[0].price", True),
    ("$.items[*].price", "$.items[1].price", True),
    ("$.items[*].price", "$.items[2].value", False),
    ("$.data.*.value", "$.data.x.value", True),
    ("$.data.*.value", "$.data.y.wrong", False),
    ("$.users[*].*.id", "$.users[0].profile.id", True),
    ("$.data[*].*.value", "$.data[1].item.value", True),
    ("$.user.*", "$.user.name", True),
    ("$.user.*", "$.user.age", True),
])
def test_match_pattern(pattern, path, expected):
    """Should match simplified JSONPath correctly."""
    assert _match_pattern(pattern, path) == expected


def test_match_pattern_edge_cases():
    """Should handle edge pattern and invalid cases gracefully."""
    assert not _match_pattern("$.data.*.value", "$.data")  # too short
    assert not _match_pattern("$.a[*].b", "$.a.b")  # missing index
    assert not _match_pattern("$.user.*", "$.user")  # incomplete


# --------------------------------------------------------------------------
# _deep_compare
# --------------------------------------------------------------------------

@pytest.mark.parametrize("a,b,expected", [
    ({"a": 1, "b": 2}, {"a": 1, "b": 2}, True),
    ({"a": 1}, {"a": 1, "b": 2}, False),  # missing key
    ([1, 2, 3], [1, 2, 3], True),
    ([1, 2, 3], [1, 2, 4], False),
    ({"a": {"b": [1, 2]}}, {"a": {"b": [1, 2]}}, True),
    ({"a": {"b": [1, 2]}}, {"a": {"b": [2, 1]}}, False),
])
def test_deep_compare_basic(a, b, expected):
    """Should correctly compare nested dicts/lists."""
    assert _deep_compare(a, b, (), 0.0, 0.0, {}, {}, 1e-12, False) == expected


@pytest.mark.parametrize("a,b,abs_tol,expected", [
    (1.0, 1.0, 0.0, True),
    (1.0, 1.001, 0.01, True),
    (1.0, 1.1, 0.01, False),
])
def test_deep_compare_numeric_absolute(a, b, abs_tol, expected):
    """Should use absolute tolerance for numeric comparison."""
    assert _deep_compare(a, b, (), abs_tol, 0.0, {}, {}, 1e-12, False) == expected


@pytest.mark.parametrize("a,b,rel_tol,expected", [
    (100.0, 101.0, 0.02, True),
    (100.0, 103.0, 0.02, False),
])
def test_deep_compare_numeric_relative(a, b, rel_tol, expected):
    """Should use relative tolerance for numeric comparison."""
    assert _deep_compare(a, b, (), 0.0, rel_tol, {}, {}, 1e-12, False) == expected


def test_deep_compare_type_and_none_mismatches():
    """Should correctly handle type mismatches and None values."""
    assert not _deep_compare(1, "1", (), 0.0, 0.0, {}, {}, 1e-12, False)
    assert not _deep_compare(None, "a", (), 0.0, 0.0, {}, {}, 1e-12, False)
    assert _deep_compare(None, None, (), 0.0, 0.0, {}, {}, 1e-12, False)


def test_deep_compare_numeric_field_tolerances():
    """Should apply field-specific tolerances from tolerance dicts."""
    abs_fields = {"$.value": 0.05}
    rel_fields = {}
    assert _deep_compare(1.0, 1.04, ("value",), 0.0, 0.0, abs_fields, rel_fields, 1e-12, False)
    assert not _deep_compare(1.0, 1.1, ("value",), 0.0, 0.0, abs_fields, rel_fields, 1e-12, False)


def test_deep_compare_lists_length_mismatch():
    """Should detect differing list lengths."""
    assert not _deep_compare([1, 2], [1, 2, 3], (), 0.0, 0.0, {}, {}, 1e-12, False)


def test_deep_compare_bool_numeric_mismatch():
    """Booleans should not be treated as numeric."""
    assert not _deep_compare(True, 1, (), 0.0, 0.0, {}, {}, 1e-12, False)
    assert not _deep_compare(False, 0, (), 0.0, 0.0, {}, {}, 1e-12, False)


@pytest.mark.parametrize("a,b,expected", [
    (float("inf"), float("inf"), True),
    (float("inf"), float("-inf"), False),
    (float("nan"), float("nan"), False),
])
def test_deep_compare_special_values(a, b, expected):
    """Should handle NaN and infinities consistently."""
    assert _deep_compare(a, b, (), 0.0, 0.0, {}, {}, 1e-12, False) == expected


def test_deep_compare_show_debug_does_not_crash(caplog):
    """Debug flag should enable logging without affecting result."""
    with caplog.at_level(logging.DEBUG):
        result = _deep_compare({"x": 1}, {"x": 1}, (), 0.0, 0.0, {}, {}, 1e-12, True)
        assert result is True
        assert any("MATCH" in msg for msg in caplog.messages)
