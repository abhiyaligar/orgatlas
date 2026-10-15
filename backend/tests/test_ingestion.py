from pathlib import Path
from app.ingestion.seed import load_fixtures, generate_seed_queries, seed_database


def test_fixture_loading():
    fixtures_dir = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures"
    fixtures = load_fixtures(fixtures_dir)

    assert "organization" in fixtures
    assert "teams" in fixtures
    assert len(fixtures["teams"]) >= 2
    assert "services" in fixtures
    assert len(fixtures["services"]) >= 4
    assert "decisions" in fixtures
    assert any(d["id"] == "dec_kafka_async" for d in fixtures["decisions"])


def test_seed_query_generation():
    fixtures_dir = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures"
    fixtures = load_fixtures(fixtures_dir)
    queries = generate_seed_queries(fixtures)

    assert len(queries) > 30
    assert any("Organization" in q for q in queries)
    assert any("dec_kafka_async" in q for q in queries)
    assert any("svc_checkout" in q for q in queries)
    assert any("DEPENDS_ON" in q for q in queries)


def test_seed_database_dry_run():
    result = seed_database(dry_run=True)
    assert result["status"] == "dry_run"
    assert result["fixtures_count"] == 12
    assert result["seed_queries_count"] > 30
