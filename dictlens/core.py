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
            parts[-1] = f"{parts[-1]}[{p}]"
    return "$." + ".".join(parts) if parts else "$."


# -----------------------------------------------------------------------------
# Pattern matching (JSONPath-like)
# -----------------------------------------------------------------------------

def _match_pattern(pattern: str, path: str) -> bool:
    """
    Match a JSONPath-like pattern to a specific path.

    Supported:
      - [*] : any array index
      - [n] : exact array index
      - .*  : any property (one level)
      - $..key : recursive descent (any depth, specific key)
    """
    regex = re.escape(pattern)
    regex = regex.replace(r"\[\*\]", r"\[\d+\]")      # any numeric index
    regex = regex.replace(r"\.\*", r"\.[^.]+")        # any single property
    regex = regex.replace(r"\$\.\.", r"\$\.?.*")      # recursive descent
    regex = "^" + regex + "$"
    return re.match(regex, path) is not None


def _validate_pattern(pattern: str) -> None:
    """Validate a user-supplied pattern against the supported subset of JSONPath."""
    VALID_PATTERN = re.compile(
        r"^\$((\.[a-zA-Z_][a-zA-Z0-9_-]*)|(\[\d+\])|(\[\*\])|(\.\*)|(\.\.[a-zA-Z_][a-zA-Z0-9_-]*)?)*$"
    )
    if not VALID_PATTERN.match(pattern):
        raise ValueError(
            f"Invalid JSONPath-like pattern: {pattern}\n"
            "Allowed tokens: $, ., [n], [*], .*, $..key"
        )


def _compile_patterns(patterns: List[str]) -> List[re.Pattern]:
    """Precompile ignore/tolerance patterns for faster matching."""
    compiled = []
    for p in patterns:
        _validate_pattern(p)
        rx = re.escape(p)
        rx = rx.replace(r"\[\*\]", r"\[\d+\]")
        rx = rx.replace(r"\.\*", r"\.[^.]+")
        rx = rx.replace(r"\$\.\.", r"\$\.?.*")
        compiled.append(re.compile("^" + rx + "$"))
    return compiled


def _path_matches_any(path_str: str, compiled_patterns: List[re.Pattern]) -> bool:
    return any(rx.match(path_str) for rx in compiled_patterns)


def _get_tolerances_for_path(
    path_str: str,
    abs_tol: float,
    rel_tol: float,
    abs_tol_fields: Dict[str, float],
    rel_tol_fields: Dict[str, float],
) -> Tuple[float, float]:
    """
    Resolve abs_tol and rel_tol for a given path.
    - Exact matches have the highest priority.
    - Patterns with [*], .*, or $.. act as wildcards.
    - Falls back to global abs/rel tolerances if nothing matches.
    """
    local_abs = abs_tol
    local_rel = rel_tol

    # Exact match first
    if path_str in abs_tol_fields:
        local_abs = abs_tol_fields[path_str]
    if path_str in rel_tol_fields:
        local_rel = rel_tol_fields[path_str]

    # Pattern match (wildcards / recursive)
    for pattern, val in abs_tol_fields.items():
        if _match_pattern(pattern, path_str):
            local_abs = val
    for pattern, val in rel_tol_fields.items():
        if _match_pattern(pattern, path_str):
            local_rel = val

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
    if _path_matches_any(path_str, ignore_patterns):
        # Entire current node is ignored
        return None  # sentinel indicating "dropped"

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
            if child is not None:
                new_d[k] = child
        return new_d

    return obj


# -----------------------------------------------------------------------------
# Main comparison
# -----------------------------------------------------------------------------

def compare_dicts(
    old: Dict[str, Any],
    new: Dict[str, Any],
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
    Compare two Python dictionaries (or lists) with:
      - global abs/rel tolerance
      - per-field abs/rel tolerance via JSONPath-like patterns
      - path-based ignored nodes (via JSONPath-like patterns)
      - strict array order
      - floating-point safety via epsilon

    Path Pattern Schema (subset of JSONPath):
      $             : root
      .key          : property access
      [n] / [*]     : array index / all elements
      .*            : wildcard property
      $..key        : recursive descent for a given key

    Unsupported:
      filters [?(..)], slices [0:2], unions [0,2], expressions.
    """
    ignore_fields = ignore_fields or []
    abs_tol_fields = abs_tol_fields or {}
    rel_tol_fields = rel_tol_fields or {}

    # Validate & precompile patterns once
    for p in list(abs_tol_fields.keys()) + list(rel_tol_fields.keys()) + list(ignore_fields):
        _validate_pattern(p)
    compiled_ignores = _compile_patterns(ignore_fields)

    # Apply path-based ignores to both structures
    old_obj = _remove_ignored_by_path(old, compiled_ignores, ())
    new_obj = _remove_ignored_by_path(new, compiled_ignores, ())

    return _deep_compare(
        old_obj,
        new_obj,
        (),
        abs_tol,
        rel_tol,
        abs_tol_fields,
        rel_tol_fields,
        epsilon,
        show_debug,
    )


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
            formatter = logging.Formatter("%(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)

    path_str = _format_path(path)

    # Type mismatch — but allow numeric equivalence
    if type(a) != type(b):
        if _is_number(a) and _is_number(b):
            pass  # allow numeric comparison
        else:
            logger.debug(f"[TYPE MISMATCH] {path_str}: {type(a).__name__} vs {type(b).__name__}")
            return False

    # Dict comparison
    if isinstance(a, dict):
        keys_a, keys_b = set(a.keys()), set(b.keys())
        if keys_a != keys_b:
            missing_in_a = keys_b - keys_a
            missing_in_b = keys_a - keys_b
            if missing_in_a:
                logger.debug(f"[KEY MISMATCH] {path_str}: Missing in left dict → {sorted(missing_in_a)}")
            if missing_in_b:
                logger.debug(f"[KEY MISMATCH] {path_str}: Missing in right dict → {sorted(missing_in_b)}")
            return False

        for k in a:
            if not _deep_compare(
                a[k], b[k], path + (k,),
                abs_tol, rel_tol, abs_tol_fields, rel_tol_fields, epsilon, show_debug,
            ):
                logger.debug(f"[FAIL IN DICT] {path_str}.{k}")
                return False
        logger.debug(f"[MATCH] {path_str}: dict OK")
        return True

    # List comparison
    if isinstance(a, list):
        if len(a) != len(b):
            logger.debug(f"[LIST LENGTH MISMATCH] {path_str}: {len(a)} vs {len(b)}")
            return False

        for i, (x, y) in enumerate(zip(a, b)):
            if not _deep_compare(
                x, y, path + (i,),
                abs_tol, rel_tol, abs_tol_fields, rel_tol_fields, epsilon, show_debug,
            ):
                logger.debug(f"[FAIL IN LIST] {path_str}[{i}]")
                return False
        logger.debug(f"[MATCH] {path_str}: list OK")
        return True

    # Numeric comparison
    if _is_number(a) and _is_number(b):
        local_abs, local_rel = _get_tolerances_for_path(path_str, abs_tol, rel_tol, abs_tol_fields, rel_tol_fields)
        a_val, b_val = float(a), float(b)
        diff = abs(a_val - b_val)
        threshold = max(local_abs, local_rel * max(abs(a_val), abs(b_val)))

        logger.debug(
            f"[NUMERIC COMPARE] {path_str}: {a_val} vs {b_val} | "
            f"diff={diff:.6f} | abs_tol={local_abs} | rel_tol={local_rel} | threshold={threshold:.6f}"
        )

        result = math.isclose(a_val, b_val, abs_tol=local_abs + epsilon, rel_tol=local_rel)
        if not result:
            logger.debug(f"[FAIL NUMERIC] {path_str} → diff={diff:.6f} > threshold={threshold:.6f}")
        else:
            logger.debug(f"[MATCH NUMERIC] {path_str}: within tolerance")
        return result

    # Generic value comparison
    if a != b:
        logger.debug(f"[VALUE MISMATCH] {path_str}: {a!r} != {b!r}")
        return False

    logger.debug(f"[MATCH] {path_str}: OK → {a!r}")
    return True
