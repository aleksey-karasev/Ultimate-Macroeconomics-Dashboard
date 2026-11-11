"""Frequency inference for short and irregular forecasting histories."""

import pandas as pd
import pytest
from umd_common.timeutil import resolve_forecast_frequency


@pytest.mark.parametrize(
    ("dates", "expected_gap"),
    [
        (["2024-01-08", "2024-01-01"], "7 days"),
        (["2024-01-01", "2024-01-01", "2024-01-08"], "7 days"),
        (["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-29"], "7 days"),
    ],
)
def test_frequency_uses_positive_gaps(dates: list[str], expected_gap: str) -> None:
    frequency = resolve_forecast_frequency(pd.DatetimeIndex(dates))
    assert pd.tseries.frequencies.to_offset(frequency) == pd.tseries.frequencies.to_offset(
        pd.Timedelta(expected_gap)
    )


@pytest.mark.parametrize("dates", [[], ["2024-01-01"], ["2024-01-01", "2024-01-01"]])
def test_frequency_defaults_without_a_positive_gap(dates: list[str]) -> None:
    assert resolve_forecast_frequency(pd.DatetimeIndex(dates), default="h") == "h"
