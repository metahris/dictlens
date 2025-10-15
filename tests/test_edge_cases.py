"""
Edge case tests to achieve 100% code coverage.
These tests target error paths and debug logging scenarios.
"""

import pytest
import logging
from dictlens.core import compare_dicts, _validate_pattern, logger


# --------------------------------------------------------------------------
# 1️- INVALID PATTERN TESTS\n
# --------------------------------------------------------------------------

def test_invalid_pattern_missing_dollar():
    """Test pattern validation: must start with $"""
    with pytest.raises(ValueError, match="Invalid JSONPath-like pattern"):
        _validate_pattern("user.age")  # Missing $


def test_invalid_pattern_unsupported_filter():
    """Test pattern validation: filters not supported"""
    with pytest.raises(ValueError, match="Invalid JSONPath-like pattern"):
        _validate_pattern("$.items[?(@.price > 10)]")


def test_invalid_pattern_unsupported_slice():
    """Test pattern validation: slices not supported"""
    with pytest.raises(ValueError, match="Invalid JSONPath-like pattern"):
        _validate_pattern("$.items[0:3]")


def test_invalid_pattern_unsupported_union():
    """Test pattern validation: unions not supported"""
    with pytest.raises(ValueError, match="Invalid JSONPath-like pattern"):
        _validate_pattern("$.items[0,2,5]")


def test_invalid_pattern_in_ignore_paths():
    """Test that invalid patterns in ignore_paths raise ValueError"""
    a = {"x": 1}
    b = {"x": 1}

    with pytest.raises(ValueError, match="Invalid JSONPath-like pattern"):
        compare_dicts(a, b, ignore_paths=["invalid_pattern"])


def test_invalid_pattern_in_abs_tol_fields():
    """Test that invalid patterns in abs_tol_fields raise ValueError"""
    a = {"x": 1.0}
    b = {"x": 1.1}

    with pytest.raises(ValueError, match="Invalid JSONPath-like pattern"):
        compare_dicts(a, b, abs_tol_fields={"[invalid]": 0.5})


def test_invalid_pattern_in_rel_tol_fields():
    """Test that invalid patterns in rel_tol_fields raise ValueError"""
    a = {"x": 100.0}
    b = {"x": 101.0}

    with pytest.raises(ValueError, match="Invalid JSONPath-like pattern"):
        compare_dicts(a, b, rel_tol_fields={"$.items[?]": 0.05})


# --------------------------------------------------------------------------
# 2- DEBUG LOGGING TESTS\n
# --------------------------------------------------------------------------

def test_debug_logging_handler_creation():
    """
    Test debug logging handler creation (lines 221-224).
    Clear handlers first to ensure the 'if not logger.hasHandlers()' branch is executed.
    """
    import logging as log_module

    # Get the logger and clear its handlers
    test_logger = log_module.getLogger('dictlens.core')
    original_handlers = test_logger.handlers[:]
    original_level = test_logger.level

    # Clear handlers to force creation path
    test_logger.handlers.clear()
    test_logger.setLevel(log_module.WARNING)

    try:
        a = {"temp": 20.0}
        b = {"temp": 20.1}

        # This should create a new handler
        result = compare_dicts(a, b, abs_tol=0.5, show_debug=True)
        assert result is True

        # After show_debug=True, logger level should be DEBUG
        assert test_logger.level == log_module.DEBUG

    finally:
        # Restore original state
        test_logger.handlers = original_handlers
        test_logger.setLevel(original_level)


def test_debug_logging_multiple_calls():
    """
    Test debug logging with multiple compare_dicts calls.
    This ensures handler reuse works correctly.
    """
    a = {"temp": 20.0}
    b = {"temp": 20.1}

    # First call with debug
    result1 = compare_dicts(a, b, abs_tol=0.5, show_debug=True)
    assert result1 is True

    # Second call with debug - should reuse existing handler
    result2 = compare_dicts(a, b, abs_tol=0.5, show_debug=True)
    assert result2 is True

    # Third call without debug
    result3 = compare_dicts(a, b, abs_tol=0.5, show_debug=False)
    assert result3 is True


def test_debug_with_nested_structure():
    """Test debug logging with complex nested data"""
    a = {
        "level1": {
            "level2": {
                "level3": {"value": 100.0}
            }
        }
    }
    b = {
        "level1": {
            "level2": {
                "level3": {"value": 100.5}
            }
        }
    }

    result = compare_dicts(a, b, abs_tol=1.0, show_debug=True)
    assert result is True


# --------------------------------------------------------------------------
# 3- LIST MISMATCH TESTS\n
# --------------------------------------------------------------------------

def test_list_length_mismatch_left_longer():
    """Test list comparison when left has more items"""
    a = {"items": [1, 2, 3, 4]}
    b = {"items": [1, 2, 3]}

    result = compare_dicts(a, b, show_debug=True)
    assert result is False


def test_list_length_mismatch_right_longer():
    """Test list comparison when right has more items"""
    a = {"items": [1, 2]}
    b = {"items": [1, 2, 3, 4, 5]}

    result = compare_dicts(a, b, show_debug=True)
    assert result is False


def test_list_empty_vs_nonempty():
    """Test empty list vs non-empty list"""
    a = {"items": []}
    b = {"items": [1]}

    result = compare_dicts(a, b, show_debug=True)
    assert result is False


def test_nested_list_length_mismatch():
    """Test length mismatch in nested lists"""
    a = {"outer": [{"inner": [1, 2, 3]}]}
    b = {"outer": [{"inner": [1, 2]}]}

    result = compare_dicts(a, b, show_debug=True)
    assert result is False


# --------------------------------------------------------------------------
# 4- VALUE MISMATCH TESTS\n
# --------------------------------------------------------------------------

def test_string_value_mismatch():
    """Test string value mismatch (non-numeric comparison)"""
    a = {"name": "Alice"}
    b = {"name": "Bob"}

    result = compare_dicts(a, b, show_debug=True)
    assert result is False


def test_boolean_value_mismatch():
    """Test boolean value mismatch"""
    a = {"active": True}
    b = {"active": False}

    result = compare_dicts(a, b, show_debug=True)
    assert result is False


def test_none_value_mismatch():
    """Test None vs value mismatch"""
    a = {"value": None}
    b = {"value": "something"}

    result = compare_dicts(a, b, show_debug=True)
    assert result is False


def test_nested_string_mismatch():
    """Test string mismatch in nested structure"""
    a = {"user": {"role": "admin"}}
    b = {"user": {"role": "guest"}}

    result = compare_dicts(a, b, show_debug=True)
    assert result is False


def test_mixed_type_string_vs_number():
    """Test type mismatch: string vs number (non-numeric types)"""
    a = {"id": "123"}
    b = {"id": 123}

    result = compare_dicts(a, b, show_debug=True)
    assert result is False


def test_list_vs_dict():
    """Test type mismatch: list vs dict"""
    a = {"data": [1, 2, 3]}
    b = {"data": {"items": [1, 2, 3]}}

    result = compare_dicts(a, b, show_debug=True)
    assert result is False


# --------------------------------------------------------------------------
# 5️- ADDITIONAL EDGE CASES\n
# --------------------------------------------------------------------------

def test_empty_dicts_with_debug():
    """Test empty dictionaries with debug enabled"""
    result = compare_dicts({}, {}, show_debug=True)
    assert result is True


def test_deeply_nested_mismatch_with_debug():
    """Test deeply nested structure with mismatch and debug"""
    a = {"a": {"b": {"c": {"d": {"e": "deep"}}}}}
    b = {"a": {"b": {"c": {"d": {"e": "different"}}}}}

    result = compare_dicts(a, b, show_debug=True)
    assert result is False


def test_unicode_string_mismatch():
    """Test Unicode string value mismatch"""
    a = {"message": "Hello "}
    b = {"message": "Goodbye "}

    result = compare_dicts(a, b, show_debug=True)
    assert result is False


def test_special_characters_in_string():
    """Test special characters in string values"""
    a = {"path": "C:\\Users\\test"}
    b = {"path": "C:\\Users\\prod"}

    result = compare_dicts(a, b, show_debug=True)
    assert result is False


def test_multiline_string_mismatch():
    """Test multiline string value mismatch"""
    a = {"description": "Line 1\nLine 2\nLine 3"}
    b = {"description": "Line 1\nLine 2\nDifferent"}

    result = compare_dicts(a, b, show_debug=True)
    assert result is False


# --------------------------------------------------------------------------
# 6️- PATTERN VALIDATION EDGE CASES\n
# --------------------------------------------------------------------------

def test_valid_pattern_complex_path():
    """Test validation of complex but valid patterns"""
    a = {"a": {"b": [{"c": 1}]}}
    b = {"a": {"b": [{"c": 1}]}}

    # This should NOT raise ValueError
    result = compare_dicts(
        a, b,
        abs_tol_fields={"$.a.b[0].c": 0.5}
    )
    assert result is True


def test_valid_pattern_recursive_descent():
    """Test validation of recursive descent pattern"""
    a = {"x": {"y": {"z": 1}}}
    b = {"x": {"y": {"z": 1}}}

    # This should NOT raise ValueError
    result = compare_dicts(
        a, b,
        ignore_paths=["$..z"]
    )
    assert result is True


def test_multiple_invalid_patterns():
    """Test that first invalid pattern is caught"""
    a = {"x": 1}
    b = {"x": 1}

    with pytest.raises(ValueError):
        compare_dicts(
            a, b,
            ignore_paths=["valid_pattern", "another_invalid"],  # Both invalid
        )


# --------------------------------------------------------------------------
# 7- COMBINATIONS WITH DEBUG MODE\n
# --------------------------------------------------------------------------

def test_all_error_types_with_debug():
    """
    Test that triggers multiple error types with debug enabled.
    This ensures all debug logging paths are exercised.
    """
    # Type mismatch
    a1 = {"x": "string"}
    b1 = {"x": 123}
    assert compare_dicts(a1, b1, show_debug=True) is False

    # Key mismatch
    a2 = {"key1": 1}
    b2 = {"key2": 1}
    assert compare_dicts(a2, b2, show_debug=True) is False

    # List length mismatch
    a3 = {"list": [1, 2]}
    b3 = {"list": [1, 2, 3]}
    assert compare_dicts(a3, b3, show_debug=True) is False

    # Value mismatch
    a4 = {"status": "active"}
    b4 = {"status": "inactive"}
    assert compare_dicts(a4, b4, show_debug=True) is False

    # Numeric tolerance exceeded
    a5 = {"value": 10.0}
    b5 = {"value": 20.0}
    assert compare_dicts(a5, b5, abs_tol=1.0, show_debug=True) is False
