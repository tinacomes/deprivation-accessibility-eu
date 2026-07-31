"""E.2 — the country-wide Overpass count layer over quality/completeness.py.

The network call itself runs on GitHub's runners (workflow "OSM completeness
benchmark (E.2)"); these tests pin the pure pieces: the count query shape and
the ``out count`` payload parsing, plus the registry-source passthrough that
keeps the table auditable.
"""

import pandas as pd

from depacc.quality.completeness import (
    build_country_count_query,
    completeness_table,
    parse_count_payload,
)


def test_country_count_query_shape():
    q = build_country_count_query(
        "DE", [{"key": "amenity", "value": "pharmacy"}])
    assert '"ISO3166-1"="DE"' in q and '"admin_level"="2"' in q
    assert 'nwr["amenity"="pharmacy"](area.country);' in q
    assert q.rstrip().endswith("out count;")
    # A require-clause rule (e.g. emergency hospitals) carries both filters.
    q2 = build_country_count_query(
        "DE", [{"key": "amenity", "value": "hospital",
                "require": {"key": "emergency", "value": "yes"}}])
    assert '["amenity"="hospital"]["emergency"="yes"]' in q2


def test_parse_count_payload():
    payload = {"elements": [
        {"type": "count", "id": 0,
         "tags": {"nodes": "10", "ways": "5", "relations": "1", "total": "16"}}]}
    assert parse_count_payload(payload) == 16
    assert parse_count_payload({"elements": []}) == 0
    assert parse_count_payload({}) == 0


def test_completeness_table_keeps_registry_source():
    osm = pd.DataFrame([
        {"country": "DE", "service": "hospital", "osm_count": 1700},
        {"country": "DE", "service": "pharmacy", "osm_count": 16800},
    ])
    registry = pd.DataFrame([
        {"country": "DE", "service": "hospital", "registry_count": 1893,
         "source": "Destatis Grunddaten 2022", "year": 2022},
        {"country": "DE", "service": "pharmacy", "registry_count": 17571,
         "source": "ABDA 2023", "year": 2023},
    ])
    pop = pd.Series({"DE": 84_669_326.0})
    table = completeness_table(osm, pop, registry)
    t = table.set_index("service")
    assert t.loc["hospital", "completeness_ratio"] == 1700 / 1893
    assert t.loc["pharmacy", "source"] == "ABDA 2023"
    assert t.loc["hospital", "facilities_per_100k"] > 0
