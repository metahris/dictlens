from dictlens import compare_dicts


def iot_station_combined_tolerances():
    """
    Simulate comparing two IoT station payloads with mixed tolerance rules:
    - Global tolerances handle normal sensor drift
    - Specific sensors have custom abs/rel tolerances
    - Some metadata fields are ignored (timestamps, IDs)
    """

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
            "version": 1.03   # version drift allowed (custom abs_tol)
        },
        "metrics": {
            "temperature": 21.6,   # tiny drift (global rel_tol ok)
            "humidity": 49.3,      # bigger drift (custom abs_tol ok)
            "pressure": 1013.5,    # tiny drift (global ok)
            "wind_speed": 5.6      # small drift (global ok)
        },
        "status": {
            "battery_level": 94.8,    # within abs_tol
            "signal_strength": -69    # within rel_tol (5%)
        },
        "timestamp": "2025-10-14T10:00:02Z"  # ignored
    }

    abs_tol_fields = {
        "$.metrics.humidity": 2.0,     # humidity sensors are noisy
        "$.station.version": 0.1       # small version drift allowed
    }

    rel_tol_fields = {
        "$.status.signal_strength": 0.05,
        "$.metrics.wind_speed": 0.05,
        "$.status.battery_level": 0.02  # allow ±2% battery drift
    }

    ignore_fields = ["timestamp"]

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

    return result
print(iot_station_combined_tolerances())