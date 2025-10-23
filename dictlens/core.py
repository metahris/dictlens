import logging
import math
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Utility helpers
# -----------------------------------------------------------------------------

def _is_number(v: Any) -> bool:
    """Return True only for real numeric types (not numeric strings)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _format_path(path: Tuple[Any, ...]) -> str:
    """Convert a tuple path into a JSONPath-style string."""
    parts = []
    for p in path:
        if isinstance(p, str):
            parts.append(p)
        elif isinstance(p, int):
            if not parts:
                parts.append(f"[{p}]")
            else:
                parts[-1] = f"{parts[-1]}[{p}]"
    return "$." + ".".join(parts) if parts else "$."


# -----------------------------------------------------------------------------
# Pattern matching (JSONPath-like, simplified)
# -----------------------------------------------------------------------------

def _match_pattern(pattern: str, path: str) -> bool:
    """Match a simplified JSONPath-like pattern to a specific path."""
    # Escape and convert JSONPath-like syntax to regex
    regex = re.escape(pattern)
    regex = regex.replace(r"\[\*\]", r"\[\d+\]")     # wildcard list index
    regex = regex.replace(r"\.\*", r"(?:\.[^.]+)")   # wildcard property
    regex = "^" + regex + "$"
    return re.match(regex, path) is not None


def _validate_pattern(pattern: str) -> None:
    """
    Validate a user-supplied pattern against the supported subset of JSONPath.

    Allowed:
        $.a.b
        $.items[0].price
        $.items[*].price
        $.data.*.value
    """
    VALID_PATTERN = re.compile(
        r"^\$"
        r"((\.[a-zA-Z_][a-zA-Z0-9_-]*)"  # .key
        r"|(\[\d+\])"                    # [0]
        r"|(\[\*\])"                     # [*]
        r"|(\.\*))+$"                    # .*
    )

    if not isinstance(pattern, str):
        raise TypeError(
            f"Invalid pattern type: expected 'str', got '{type(pattern).__name__}'"
        )

    if not VALID_PATTERN.match(pattern):
        hint = ""
        if not pattern.startswith("$"):
            hint = f" (Hint: Did you mean '$.{pattern}'?)"
        raise ValueError(
            f"❌ Invalid JSONPath-like pattern: {pattern}{hint}\n"
            "Allowed tokens: $, ., [n], [*], .*"
        )


def _compile_patterns(patterns: List[str]) -> List[re.Pattern]:
    """Precompile ignore/tolerance patterns for faster matching with validation."""
    compiled = []
    for p in patterns or []:
        try:
            _validate_pattern(p)
            rx = re.escape(p)
            rx = rx.replace(r"\[\*\]", r"\[\d+\]")
            rx = rx.replace(r"\.\*", r"\.[^.]+")
            compiled.append(re.compile("^" + rx + "$"))
        except Exception as e:
            logger.warning(f"[WARN] Ignoring invalid pattern '{p}': {e}")
    return compiled


def _path_matches_any(path_str: str, compiled_patterns: List[re.Pattern]) -> bool:
    """Return True if path_str matches any compiled regex pattern."""
    return any(rx.match(path_str) for rx in compiled_patterns or [])


# -----------------------------------------------------------------------------
# Tolerance resolution
# -----------------------------------------------------------------------------

def _get_tolerances_for_path(
    path_str: str,
    abs_tol: float,
    rel_tol: float,
    abs_tol_fields: Dict[str, float],
    rel_tol_fields: Dict[str, float],
) -> Tuple[float, float]:
    """Return absolute and relative tolerances for a given path."""
    local_abs = abs_tol or 0.0
    local_rel = rel_tol or 0.0

    try:
        # Exact match first
        abs_exact = path_str in abs_tol_fields
        rel_exact = path_str in rel_tol_fields

        if abs_exact:
            local_abs = float(abs_tol_fields[path_str])
        if rel_exact:
            local_rel = float(rel_tol_fields[path_str])

        # Pattern-based match (only if no exact match)
        if not abs_exact:
            for pattern, val in abs_tol_fields.items():
                if _match_pattern(pattern, path_str):
                    local_abs = float(val)
        if not rel_exact:
            for pattern, val in rel_tol_fields.items():
                if _match_pattern(pattern, path_str):
                    local_rel = float(val)

    except Exception as e:
        logger.warning(f"[WARN] Failed to resolve tolerances for {path_str}: {e}")

    return local_abs, local_rel


# -----------------------------------------------------------------------------
# Path-aware ignore
# -----------------------------------------------------------------------------

def _remove_ignored_by_path(
    obj: Any,
    ignore_patterns: List[re.Pattern],
    path: Tuple[Any, ...] = (),
) -> Any:
    """Recursively drop keys/items whose *path* matches any ignore pattern."""
    path_str = _format_path(path)
    try:
        if _path_matches_any(path_str, ignore_patterns):
            return None
    except Exception as e:
        logger.warning(f"[WARN] Ignoring path {path_str} failed: {e}")

    if isinstance(obj, list):
        kept = []
        for i, item in enumerate(obj):
            child = _remove_ignored_by_path(item, ignore_patterns, path + (i,))
            if child is not None:
                kept.append(child)
        return kept

    if isinstance(obj, dict):
        new_d = {}
        for k, v in obj.items():
            child = _remove_ignored_by_path(v, ignore_patterns, path + (k,))
            if child is not None or v is None:
                new_d[k] = child
        return new_d

    return obj


# -----------------------------------------------------------------------------
# Main comparison
# -----------------------------------------------------------------------------

def compare_dicts(
    left: Dict[str, Any],
    right: Dict[str, Any],
    *,
    ignore_fields: List[str] = None,
    abs_tol: float = 0.0,
    rel_tol: float = 0.0,
    abs_tol_fields: Dict[str, float] = None,
    rel_tol_fields: Dict[str, float] = None,
    epsilon: float = 1e-12,
    show_debug: bool = False,
) -> bool:
    """
    Compare two Python dictionaries (or lists) safely and informatively.
    """
    ignore_fields = ignore_fields or []
    abs_tol_fields = abs_tol_fields or {}
    rel_tol_fields = rel_tol_fields or {}

    try:
        all_patterns = list(abs_tol_fields.keys()) + list(rel_tol_fields.keys()) + list(ignore_fields)
        for p in all_patterns:
            _validate_pattern(p)
    except Exception as e:
        raise ValueError(
            f"❌ Invalid pattern detected in compare_dicts input: {e}\n"
            "Each field in 'ignore_fields', 'abs_tol_fields', and 'rel_tol_fields' "
            "must follow JSONPath-like syntax."
        ) from None

    compiled_ignores = _compile_patterns(ignore_fields)

    if not isinstance(left, (dict, list)) or not isinstance(right, (dict, list)):
        raise TypeError(
            f"compare_dicts() expects two dict or list structures, got {type(left).__name__} and {type(right).__name__}"
        )

    try:
        old_obj = _remove_ignored_by_path(left, compiled_ignores)
        new_obj = _remove_ignored_by_path(right, compiled_ignores)
    except Exception as e:
        logger.warning(f"[WARN] Failed during ignore filtering: {e}")
        old_obj, new_obj = left, right

    try:
        return _deep_compare(
            old_obj,
            new_obj,
            (),
            abs_tol or 0.0,
            rel_tol or 0.0,
            abs_tol_fields,
            rel_tol_fields,
            epsilon,
            show_debug,
        )
    except Exception as e:
        logger.error(f"[ERROR] Unexpected error during deep comparison: {e}")
        return False


# -----------------------------------------------------------------------------
# Recursive deep comparison
# -----------------------------------------------------------------------------

def _deep_compare(
    a: Any,
    b: Any,
    path: Tuple[Any, ...],
    abs_tol: float,
    rel_tol: float,
    abs_tol_fields: Dict[str, float],
    rel_tol_fields: Dict[str, float],
    epsilon: float,
    show_debug: bool,
) -> bool:
    """Recursive deep comparison with structured debug logging."""
    if show_debug:
        logger.setLevel(logging.DEBUG)
        if not logger.hasHandlers():
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)

    path_str = _format_path(path)

    if a is None and b is None:
        logger.debug(f"[MATCH] {path_str}: OK → {a!r}")
        return True
    if (a is None) != (b is None):
        logger.debug(f"[MISMATCH] {path_str}: one side is None → {a!r} vs {b!r}")
        return False

    if type(a) != type(b):
        if _is_number(a) and _is_number(b):
            pass
        else:
            logger.debug(f"[TYPE MISMATCH] {path_str}: {type(a).__name__} vs {type(b).__name__}")
            return False

    if isinstance(a, dict):
        keys_a, keys_b = set(a.keys()), set(b.keys())
        if keys_a != keys_b:
            logger.debug(f"[KEY MISMATCH] {path_str}: keys differ {keys_a ^ keys_b}")
            return False
        for k in a:
            if not _deep_compare(a[k], b[k], path + (k,),
                                 abs_tol, rel_tol, abs_tol_fields, rel_tol_fields, epsilon, show_debug):
                logger.debug(f"[FAIL IN DICT] {path_str}.{k}")
                return False
        logger.debug(f"[MATCH] {path_str}: dict OK")
        return True

    if isinstance(a, list):
        if len(a) != len(b):
            logger.debug(f"[LIST LENGTH MISMATCH] {path_str}: {len(a)} vs {len(b)}")
            return False
        for i, (x, y) in enumerate(zip(a, b)):
            if not _deep_compare(x, y, path + (i,),
                                 abs_tol, rel_tol, abs_tol_fields, rel_tol_fields, epsilon, show_debug):
                logger.debug(f"[FAIL IN LIST] {path_str}[{i}]")
                return False
        logger.debug(f"[MATCH] {path_str}: list OK")
        return True

    if _is_number(a) and _is_number(b):
        local_abs, local_rel = _get_tolerances_for_path(path_str, abs_tol, rel_tol,
                                                        abs_tol_fields, rel_tol_fields)
        a_val, b_val = float(a), float(b)
        diff = abs(a_val - b_val)
        threshold = max(local_abs, local_rel * max(abs(a_val), abs(b_val)))
        result = math.isclose(a_val, b_val, abs_tol=local_abs + epsilon, rel_tol=local_rel)
        logger.debug(
            f"[NUMERIC COMPARE] {path_str}: {a_val} vs {b_val} | diff={diff:.6f} | "
            f"abs_tol={local_abs} | rel_tol={local_rel} | threshold={threshold:.6f} | result={result}"
        )
        return result

    if a != b:
        logger.debug(f"[VALUE MISMATCH] {path_str}: {a!r} != {b!r}")
        return False

    logger.debug(f"[MATCH] {path_str}: OK → {a!r}")
    return True
