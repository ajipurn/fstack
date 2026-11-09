import pytest

from app.db.session import transaction
from app.llm.backends import Usage, usage_from
from app.services import pricing
from tests.conftest import MODELS_DEV


@pytest.fixture()
def priced(database: str) -> str:
    with transaction(database) as db:
        pricing.sync_catalog(db, MODELS_DEV)
    return database


def test_sync_keeps_manual_overrides(priced: str) -> None:
    with transaction(priced) as db:
        pricing.set_manual_price(db, "openai", "gpt-test-mini", {"input": 9.0, "output": 9.0})
        result = pricing.sync_catalog(db, MODELS_DEV)
        rates = pricing.find_rates(db, "openai", "gpt-test-mini")
    assert result["manual_kept"] == 1
    assert rates and rates.source == "manual" and rates.input == 9.0


def test_lookup_fallbacks(priced: str) -> None:
    with transaction(priced) as db:
        # Bedrock cross-region inference profile → base model id
        assert pricing.find_rates(db, "amazon-bedrock", "us.anthropic.claude-test-v1:0")
        # OpenAI-compatible gateway with no catalog → first-party price
        assert pricing.find_rates(db, "", "gpt-test-mini").catalog_id == "openai"
        # vendor/model style ids
        assert pricing.find_rates(db, "openrouter", "openai/gpt-test-mini")
        assert pricing.find_rates(db, "openai", "unknown-model") is None


def test_cost_bills_cache_and_tiers(priced: str) -> None:
    with transaction(priced) as db:
        mini = pricing.find_rates(db, "openai", "gpt-test-mini")
        claude = pricing.find_rates(db, "anthropic", "claude-test")
    # 1M input of which 400k cached, 100k output
    usage = Usage(input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=400_000)
    assert pricing.cost_usd(mini, usage) == pytest.approx(0.6 * 0.25 + 0.4 * 0.025 + 0.1 * 2.0)
    small = Usage(input_tokens=100_000, output_tokens=1000)
    big = Usage(input_tokens=300_000, output_tokens=1000)
    assert pricing.cost_usd(claude, small) == pytest.approx(0.1 * 1.0 + 0.001 * 5.0)
    assert pricing.cost_usd(claude, big) == pytest.approx(0.3 * 2.0 + 0.001 * 10.0)
    assert pricing.cost_usd(None, small) is None


def test_usage_normalisation_per_backend() -> None:
    details = [{"input_tokens": 100, "output_tokens": 10, "cache_read_tokens": 50}]
    # OpenAI/Google already include cached tokens in input_tokens
    assert usage_from(details, "openai").input_tokens == 100
    # Anthropic/Bedrock report them separately
    assert usage_from(details, "anthropic").input_tokens == 150
