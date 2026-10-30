#!/usr/bin/env python3
"""Seed deterministic synthetic data for offline integration/UI tests.

Run inside ``downloader_general`` after its schema exists. Inserts are idempotent
and never delete data. This is test data, not a replacement for real ingestion.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import os

from sqlalchemy import create_engine, text
from src.utils.db_bootstrap import ensure_llm_role
from src.utils.downloads import _get_sql_config
from src.utils.schema import _build_metadata, load_database_schema


def _insert_world_bank(
    connection, config_path: str = "_configs/world_bank_download_config.json"
) -> None:
    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
    items = [item for section in config.values() for item in section]
    countries = {
        "USA": "United States",
        "DEU": "Germany",
        "FRA": "France",
        "JPN": "Japan",
        "BRA": "Brazil",
        "IND": "India",
    }
    db_ids = sorted({int(item.get("db", 2)) for item in items})
    connection.execute(
        text(
            "INSERT INTO world_bank_databases (id, name, code) "
            "VALUES (2, :name, :code) ON CONFLICT (id) DO NOTHING"
        ),
        {"name": "World Development Indicators", "code": "WDI"},
    )
    for db_id in db_ids:
        if db_id != 2:
            connection.execute(
                text(
                    "INSERT INTO world_bank_databases (id, name, code) "
                    "VALUES (:id, :name, :code) ON CONFLICT (id) DO NOTHING"
                ),
                {"id": db_id, "name": f"Test database {db_id}", "code": f"DB{db_id}"},
            )
    for index, (code, name) in enumerate(countries.items()):
        connection.execute(
            text(
                "INSERT INTO world_bank_countries (id, value, aggregate, longitude, latitude, "
                '"region.id", "region.value") VALUES (:id, :value, false, :longitude, '
                ":latitude, :region_id, :region_value) ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": code,
                "value": name,
                "longitude": float(index * 10),
                "latitude": float(40 - index),
                "region_id": "TEST",
                "region_value": "Test region",
            },
        )
    for index, item in enumerate(items):
        indicator_id = item["id"]
        db_id = int(item.get("db", 2))
        name = item.get("name", indicator_id)
        connection.execute(
            text(
                "INSERT INTO world_bank_database_indicators (id, description, database_id) "
                "VALUES (:id, :description, :db_id) ON CONFLICT (id, database_id) DO NOTHING"
            ),
            {"id": indicator_id, "description": name, "db_id": db_id},
        )
        connection.execute(
            text(
                "INSERT INTO world_bank_metadata "
                "(indicator_id, db_id, indicator_name, units, source) "
                "VALUES (:id, :db_id, :name, :units, :source) "
                "ON CONFLICT (indicator_id, db_id) DO NOTHING"
            ),
            {
                "id": indicator_id,
                "db_id": db_id,
                "name": name,
                "units": "synthetic units",
                "source": "Offline UI verification fixture",
            },
        )
        for country_index, economy in enumerate(countries):
            for year in range(2020, 2025):
                value = float((index + 1) * 100 + country_index * 20 + (year - 2020) * 5)
                connection.execute(
                    text(
                        "INSERT INTO world_bank_indicators "
                        "(economy, year, value, indicator_id, db_id) "
                        "VALUES (:economy, :year, :value, :indicator_id, :db_id) "
                        "ON CONFLICT (economy, year, indicator_id, db_id) DO NOTHING"
                    ),
                    {
                        "economy": economy,
                        "year": year,
                        "value": value,
                        "indicator_id": indicator_id,
                        "db_id": db_id,
                    },
                )


def _insert_markets(connection, start: datetime) -> None:
    for ticker_index, ticker in enumerate(["AAPL", "MSFT"]):
        connection.execute(
            text(
                "INSERT INTO yahoo_metadata (ticker, asset_name, category, short_name, sector, "
                "industry, currency, exchange, business_summary) VALUES "
                "(:t, :a, :cat, :s, :sec, :ind, :cur, :ex, :summary) "
                "ON CONFLICT (ticker) DO NOTHING"
            ),
            {
                "t": ticker,
                "a": ticker,
                "cat": "Companies",
                "s": ticker,
                "sec": "Technology",
                "ind": "Software",
                "cur": "USD",
                "ex": "NMS",
                "summary": "Synthetic UI test asset",
            },
        )
        for day in range(40):
            close = 100.0 + ticker_index * 50 + day
            connection.execute(
                text(
                    "INSERT INTO yahoo_historical_prices "
                    "(date, open, high, low, close, volume, ticker, category) "
                    "VALUES (:date, :open, :high, :low, :close, :volume, :ticker, :category) "
                    "ON CONFLICT (date, ticker) DO NOTHING"
                ),
                {
                    "date": start + timedelta(days=day),
                    "open": close - 1,
                    "high": close + 2,
                    "low": close - 2,
                    "close": close,
                    "volume": 1000000 + day * 1000,
                    "ticker": ticker,
                    "category": "Companies",
                },
            )
    for coin_index, (symbol, base) in enumerate([("BTCUSDT", "BTC"), ("ETHUSDT", "ETH")]):
        last = 50000.0 if base == "BTC" else 3000.0
        connection.execute(
            text(
                "INSERT INTO binance_metadata (symbol, base_asset, quote_asset, status, rank, "
                "description, last_price, price_change_percent_24h, high_24h, low_24h, "
                "quote_volume_24h, trade_count_24h) VALUES (:symbol, :base, :quote, :status, "
                ":rank, :description, :last, :change, :high, :low, :qv, :trades) "
                "ON CONFLICT (symbol) DO NOTHING"
            ),
            {
                "symbol": symbol,
                "base": base,
                "quote": "USDT",
                "status": "TRADING",
                "rank": coin_index + 1,
                "description": "Synthetic UI test pair",
                "last": last,
                "change": 1.5,
                "high": last * 1.02,
                "low": last * 0.98,
                "qv": 1e9 / (coin_index + 1),
                "trades": 100000,
            },
        )
        for day in range(40):
            close = last + day * (10 if base == "BTC" else 2)
            connection.execute(
                text(
                    "INSERT INTO binance_historical_prices (date, open, high, low, close, "
                    "volume, quote_volume, symbol, base_asset) VALUES (:date, :open, :high, "
                    ":low, :close, :volume, :quote_volume, :symbol, :base) "
                    "ON CONFLICT (date, symbol) DO NOTHING"
                ),
                {
                    "date": start + timedelta(days=day),
                    "open": close - 1,
                    "high": close + 2,
                    "low": close - 2,
                    "close": close,
                    "volume": 100.0 + day,
                    "quote_volume": close * (100.0 + day),
                    "symbol": symbol,
                    "base": base,
                },
            )


def _insert_regions(connection) -> None:
    states = {
        "CA": ("California", "06"),
        "TX": ("Texas", "48"),
        "NY": ("New York", "36"),
        "FL": ("Florida", "12"),
        "WA": ("Washington", "53"),
        "IL": ("Illinois", "17"),
    }
    for code, (name, fips) in states.items():
        connection.execute(
            text(
                "INSERT INTO fred_states (id, name, fips, region, division) "
                "VALUES (:id, :name, :fips, :region, :division) ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": code,
                "name": name,
                "fips": fips,
                "region": "Test region",
                "division": "Test division",
            },
        )
    connection.execute(
        text(
            "INSERT INTO fred_state_indicators (indicator_id, name, category, series_group, "
            "example_series_id, units, frequency, seasonal_adjustment, region_type, min_date, "
            "max_date, notes) VALUES (:id, :name, :cat, :group, :example, :units, :frequency, "
            ":sa, :rt, :min_date, :max_date, :notes) ON CONFLICT (indicator_id) DO NOTHING"
        ),
        {
            "id": "unemployment_rate",
            "name": "Unemployment Rate",
            "cat": "Labor Market",
            "group": "test",
            "example": "CAUR",
            "units": "Percent",
            "frequency": "Monthly",
            "sa": "SA",
            "rt": "state",
            "min_date": "2020-01-01",
            "max_date": "2024-01-01",
            "notes": "Synthetic UI test indicator",
        },
    )
    for state_index, state in enumerate(states):
        for year in range(2020, 2025):
            connection.execute(
                text(
                    "INSERT INTO fred_state_indicator_values (state, year, value, indicator_id) "
                    "VALUES (:state, :year, :value, :indicator) "
                    "ON CONFLICT (state, year, indicator_id) DO NOTHING"
                ),
                {
                    "state": state,
                    "year": year,
                    "value": 3.0 + state_index + (year - 2020) * 0.2,
                    "indicator": "unemployment_rate",
                },
            )

    regions = {
        "DE21": ("Oberbayern", "Germany"),
        "FR10": ("Île de France", "France"),
        "ES30": ("Comunidad de Madrid", "Spain"),
        "ITC4": ("Lazio", "Italy"),
        "PL91": ("Warszawski stołeczny", "Poland"),
    }
    for code, (name, country) in regions.items():
        connection.execute(
            text(
                "INSERT INTO eurostat_regions (id, name, country_code, country_name, nuts1_id, "
                "level) VALUES (:id, :name, :cc, :country, :nuts1, 2) ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": code,
                "name": name,
                "cc": code[:2],
                "country": country,
                "nuts1": code[:3],
            },
        )
    connection.execute(
        text(
            "INSERT INTO eurostat_indicators (indicator_id, name, category, dataset, filters, "
            "units, frequency, nuts_level, min_year, max_year, source_label, notes) VALUES "
            "(:id, :name, :cat, :dataset, :filters, :units, :frequency, 2, :min_year, "
            ":max_year, :source, :notes) ON CONFLICT (indicator_id) DO NOTHING"
        ),
        {
            "id": "gdp_per_capita_pps",
            "name": "GDP per capita (PPS)",
            "cat": "Economy & output",
            "dataset": "test_dataset",
            "filters": "{}",
            "units": "PPS",
            "frequency": "Annual",
            "min_year": 2020,
            "max_year": 2024,
            "source": "Synthetic UI test dataset",
            "notes": "Offline verification",
        },
    )
    for region_index, region in enumerate(regions):
        for year in range(2020, 2025):
            connection.execute(
                text(
                    "INSERT INTO eurostat_indicator_values (region, year, value, indicator_id) "
                    "VALUES (:region, :year, :value, :indicator) "
                    "ON CONFLICT (region, year, indicator_id) DO NOTHING"
                ),
                {
                    "region": region,
                    "year": year,
                    "value": 20000.0 + region_index * 5000 + (year - 2020) * 1000,
                    "indicator": "gdp_per_capita_pps",
                },
            )


def main() -> None:
    uri = _get_sql_config(
        os.environ["POSTGRES_USER"],
        os.environ["POSTGRES_PASSWORD"],
        "db",
        5432,
        os.environ["POSTGRES_DB"],
    )
    schema = load_database_schema("database_schema.yaml")
    engine = create_engine(uri)
    with engine.begin() as connection:
        for group in schema["databases"]:
            metadata, _ = _build_metadata(schema, group)
            metadata.create_all(connection)
        _insert_world_bank(connection)
        _insert_markets(connection, datetime(2024, 1, 1))
        _insert_regions(connection)
    ensure_llm_role(
        sql_uri=uri,
        llm_username=os.environ["POSTGRES_LLM_USER"],
        llm_password=os.environ["POSTGRES_LLM_PASSWORD"],
    )
    print("Seeded deterministic offline UI fixtures.")


if __name__ == "__main__":
    main()
