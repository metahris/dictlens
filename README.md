# dictlens

Deep structural comparison for Python dicts with per-field numeric
tolerance and JSONPath-like targeting.

## Overview

`dictlens` is a lightweight Python library for comparing two nested
`dict` structures (or any dict-like objects) with **fine-grained
tolerance control**.

It supports:

- ✅ Global absolute (`abs_tol`) and relative (`rel_tol`) numeric
  tolerances
- ✅ Per-field tolerance overrides via JSONPath-like expressions
- ✅ Ignoring volatile or irrelevant fields
- ✅ Detailed debug logs that explain *why* two structures differ

It’s ideal for comparing API payloads, serialized models, ML metrics, or
configurations where small numeric drifts are expected.

## Installation

    pip install dictlens

## Quick Examples

``` python
from dictlens import compare_dicts

a = {"sensor": {"temp": 21.5, "humidity": 48.0}}
b = {"sensor": {"temp": 21.7, "humidity": 48.5}}

# Default tolerances
res = compare_dicts(a, b, abs_tol=0.05, rel_tol=0.01, show_debug=True)
print(res)  # False
```

```console
### Output (debug)

[NUMERIC COMPARE] $.sensor.temp: 21.5 vs 21.7 | diff=0.200000 | abs_tol=0.05 | rel_tol=0.01 | threshold=0.217000
[MATCH NUMERIC] $.sensor.temp: within tolerance
[NUMERIC COMPARE] $.sensor.humidity: 48.0 vs 48.5 | diff=0.500000 | abs_tol=0.05 | rel_tol=0.01 | threshold=0.485000
[FAIL NUMERIC] $.sensor.humidity → diff=0.500000 > threshold=0.485000
[FAIL IN DICT] $.sensor.humidity
[FAIL IN DICT] $..sensor
```

#### Ignore Fields

```python
from dictlens import compare_dicts


def test_ignore_path_root_field():
    a = {"id": 1, "timestamp": "now"}
    b = {"id": 1, "timestamp": "later"}

    # Ignore only the root timestamp field
    ignore_fields = ["$.timestamp"]

    result = compare_dicts(a, b, ignore_fields=ignore_fields)
    print(result)  # True


def test_ignore_fields_complex():
    """
    Ignore multiple paths with different patterns:
      - Exact path:            $.user.profile.updated_at
      - Array wildcard:        $.devices[*].debug
      - Recursive descent key: $..trace
    """
    a = {
        "user": {
            "id": 7,
            "profile": {"updated_at": "2025-10-14T10:00:00Z", "age": 30}
        },
        "devices": [
            {"id": "d1", "debug": "alpha", "temp": 20.0},
            {"id": "d2", "debug": "beta", "temp": 20.1}
        ],
        "sessions": [
            {"events": [{"meta": {"trace": "abc"}, "value": 10.0}]},
            {"events": [{"meta": {"trace": "def"}, "value": 10.5}]}
        ]
    }

    b = {
        "user": {
            "id": 7,
            "profile": {"updated_at": "2025-10-15T10:00:05Z", "age": 30}
        },
        "devices": [
            {"id": "d1", "debug": "changed", "temp": 20.05},
            {"id": "d2", "debug": "changed", "temp": 20.18}
        ],
        "sessions": [
            {"events": [{"meta": {"trace": "xyz"}, "value": 10.01}]},
            {"events": [{"meta": {"trace": "uvw"}, "value": 10.52}]}
        ]
    }

    # Ignore updated_at (exact), all device.debug (wildcard), any 'trace' anywhere (recursive)
    ignore_fields = [
        "$.user.profile.updated_at",
        "$.devices[*].debug",
        "$..trace",
    ]

    # Small global tolerance to allow minor sensor/value drift
    result = compare_dicts(
        a, b,
        ignore_fields=ignore_fields,
        abs_tol=0.05,
        rel_tol=0.02
    )
    print(result)  # True
```

#### Per-field Tolerances

You can override tolerances for specific paths using JSONPath-like
expressions.

```python
from dictlens import compare_dicts

a = {"a": 1.0, "b": 2.0}
b = {"a": 1.5, "b": 2.5}
abs_tol_fields = {"$.b": 1.0}
result = compare_dicts(a, b,abs_tol=0.5, abs_tol_fields=abs_tol_fields) 
print(result)  # True
```

#### array specific index tolerance

```python
from dictlens import compare_dicts

a = {"sensors": [{"temp": 20.0}, {"temp": 21.0}]}
b = {"sensors": [{"temp": 20.05}, {"temp": 21.5}]}
abs_tol_fields = {"$.sensors[0].temp": 0.1, "$.sensors[1].temp": 1.0} 
result = compare_dicts(a, b, abs_tol_fields=abs_tol_fields)
print(result) # True
```

#### array wildcard tolerance

```python
from dictlens import compare_dicts

a = {"sensors": [{"temp": 20.0}, {"temp": 21.0}]}
b = {"sensors": [{"temp": 20.2}, {"temp": 21.1}]}
abs_tol_fields = {"$.sensors[*].temp": 0.5}
result = compare_dicts(a, b, abs_tol_fields=abs_tol_fields)
print(result) # True
```

#### property wildcard tolerance

```python
from dictlens import compare_dicts

a = {"network": {"n1": {"v": 10}, "n2": {"v": 10}}}
b = {"network": {"n1": {"v": 10.5}, "n2": {"v": 9.8}}}
abs_tol_fields = {"$.network.*.v": 1.0}
result = compare_dicts(a, b, abs_tol_fields=abs_tol_fields)
print(result) # True
```

#### recursive wildcard tolerance

```python
from dictlens import compare_dicts

a  = {"meta": {"deep": {"very": {"x": 100}}}}
b = {"meta": {"deep": {"very": {"x": 101}}}}
abs_tol_fields = {"$..x": 2.0}
result = compare_dicts(a, b, abs_tol_fields=abs_tol_fields)
print(result)
```

#### combined global and field tolerances

```python 
from dictlens import compare_dicts

# Original reading (e.g., baseline snapshot)
a = {
    "station": {
        "id": "ST-42",
        "location": "Paris",
        "version": 1.0
    },
    "metrics": {
        "temperature": 21.5,
        "humidity": 48.0,
        "pressure": 1013.2,
        "wind_speed": 5.4
    },
    "status": {
        "battery_level": 96.0,
        "signal_strength": -72
    },
    "timestamp": "2025-10-14T10:00:00Z"
}

# New reading (e.g., after transmission)
b = {
    "station": {
        "id": "ST-42",
        "location": "Paris",
        "version": 1.03  # version drift allowed (custom abs_tol)
    },
    "metrics": {
        "temperature": 21.6,  # tiny drift (global rel_tol ok)
        "humidity": 49.3,  # bigger drift (custom abs_tol ok)
        "pressure": 1013.5,  # tiny drift (global ok)
        "wind_speed": 5.6  # small drift (global ok)
    },
    "status": {
        "battery_level": 94.8,  # within abs_tol
        "signal_strength": -69  # within rel_tol (5%)
    },
    "timestamp": "2025-10-14T10:00:02Z"  # ignored
}

abs_tol_fields = {
    "$.metrics.humidity": 2.0,  # humidity sensors are noisy
    "$.station.version": 0.1  # small version drift allowed
}

rel_tol_fields = {
    "$.status.signal_strength": 0.05,
    "$.metrics.wind_speed": 0.05,
    "$.status.battery_level": 0.02  # allow ±2% battery drift
}

ignore_fields = ["$.meta.id"]

result = compare_dicts(
    a,
    b,
    abs_tol=0.05,
    rel_tol=0.01,
    abs_tol_fields=abs_tol_fields,
    rel_tol_fields=rel_tol_fields,
    ignore_fields=ignore_fields,
    show_debug=True
)

print(result)  # True
```

## Supported Path Patterns

`dictlens` implements a simplified subset of JSONPath syntax:

<table>
<thead>
<tr>
<th>Pattern</th>
<th>Description</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>$.a.b</code></td>
<td>Exact field path</td>
</tr>
<tr>
<td><code>$.items[0].price</code></td>
<td>Specific array index</td>
</tr>
<tr>
<td><code>$.items[*].price</code></td>
<td>Any array element</td>
</tr>
<tr>
<td><code>$.data.*.value</code></td>
<td>Any property name</td>
</tr>
<tr>
<td><code>$..x</code></td>
<td>Recursive descent for key <code>x</code></td>
</tr>
</tbody>
</table>

🔍 Supported and Future JSONPath Features

dictlens currently supports a focused subset of JSONPath syntax designed for simplicity and performance in numeric
comparisons.

These patterns cover the vast majority of practical comparison use cases.

At the moment, advanced JSONPath features such as filters ([?()]), unions ([0,1,2]), slices ([0:2]), or expressions are
not yet supported.
Future versions of dictlens may expand support for these features once performance and readability trade-offs are fully
evaluated.

## Full API

    compare_dicts(
        left: dict,
        right: dict,
        *,
        ignore_fields: list[str] = None,
        abs_tol: float = 0.0,
        rel_tol: float = 0.0,
        abs_tol_fields: dict[str, float] = None,
        rel_tol_fields: dict[str, float] = None,
        epsilon: float = 1e-12,
        show_debug: bool = False,
    ) -> bool

### Arguments

<table>
<thead>
<tr>
<th>Parameter D</th>
<th>escription</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>left, right</code></td>
<td>The two structures to compare.</td>
</tr>
<tr>
<td><code>ignore_fields</code></td>
<td>Keys to ignore during comparison.</td>
</tr>
<tr>
<td><code>abs_tol</code></td>
<td>Global absolute tolerance for numeric drift.</td>
</tr>
<tr>
<td><code>rel_tol</code></td>
<td>Global relative tolerance.</td>
</tr>
<tr>
<td><code>abs_tol_fields</code></td>
<td>Dict of per-field absolute tolerances.</td>
</tr>
<tr>
<td><code>rel_tol_fields</code></td>
<td>Dict of per-field relative tolerances.</td>
</tr>
<tr>
<td><code>epsilon</code></td>
<td>Small float to absorb FP rounding errors.</td>
</tr>
<tr>
<td><code>show_debug</code></td>
<td>If True, prints detailed comparison logs.</td>
</tr>
</tbody>
</table>


## Tips

- Both dicts must have the same keys — missing keys fail the comparison.
- Lists are compared in order.
- For dataclasses or Pydantic models, call `.dict()` first:
  `compare_dicts(model_a.dict(), model_b.dict())`
- Numeric strings (`"1.0"`) are **not treated as numbers**. Only real
  numeric types (`int`/`float`) are compared numerically.

## Use Cases

- Snapshot testing of API responses or data models.
- Machine-learning drift and metric comparison.
- CI/CD pipelines to verify payload consistency.
- Configuration or schema diffing.

## License

Apache License 2.0 — © 2025 Mohamed Tahri Contributions welcome 🤝
