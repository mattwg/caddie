"""Per-model $/token rates, used to turn the token counts every
transcript entry already carries into a dollar figure.

Claude Code's own `costUSD` (written into rare `cost-state` transcript
entries - see `caddie.cost.transcript`) isn't reliably present at the
point `caddie track-update` runs, so this computes cost the same way
community tools like `ccusage` do in "calculate" mode: token counts
(always present) times a maintained pricing table, rather than waiting
for a snapshot that may never come before the next hook fires.

`_BUNDLED_RATES` below are Anthropic's published per-million-token
prices (platform.claude.com/docs/en/about-claude/pricing, checked
2026-09-26) for the models this account uses - the floor this module
always falls back to. `refresh()` (called from `caddie track-start`,
once per episode/step - never from the `Stop` hook itself, which must
stay network-free and fast) fetches LiteLLM's community-maintained
`model_prices_and_context_window.json` and caches whatever it finds
under a *bare* `claude-...` key (no provider prefix like `anthropic.`
or `vertex_ai/`, no `@date`/`-v1:0` suffix) - that's the exact string
shape Claude Code's own transcripts use in `message.model`, confirmed
against a real fetch of the file rather than assumed, so this is an
exact key lookup, not fuzzy matching. A model neither bundled nor in
the cache reports its token counts with `usd=None` rather than a
silently wrong dollar figure.
"""

import json
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_5m_tokens: int = 0
    cache_creation_1h_tokens: int = 0
    cache_read_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_5m_tokens=self.cache_creation_5m_tokens
            + other.cache_creation_5m_tokens,
            cache_creation_1h_tokens=self.cache_creation_1h_tokens
            + other.cache_creation_1h_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_5m_tokens": self.cache_creation_5m_tokens,
            "cache_creation_1h_tokens": self.cache_creation_1h_tokens,
            "cache_read_tokens": self.cache_read_tokens,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "TokenUsage":
        return cls(**{k: raw.get(k, 0) for k in cls.__dataclass_fields__})


@dataclass
class ModelRate:
    """$ per token (not per million) for one model."""

    input: float
    output: float
    cache_creation_5m: float
    cache_creation_1h: float
    cache_read: float


def _per_mtok(input_: float, output: float, write_5m: float, write_1h: float, read: float) -> ModelRate:
    return ModelRate(
        input=input_ / 1_000_000,
        output=output / 1_000_000,
        cache_creation_5m=write_5m / 1_000_000,
        cache_creation_1h=write_1h / 1_000_000,
        cache_read=read / 1_000_000,
    )


# $ per million tokens: (input, output, 5m cache write, 1h cache write, cache read)
_BUNDLED_RATES: dict[str, ModelRate] = {
    "claude-sonnet-5": _per_mtok(2, 10, 2.50, 4, 0.20),
    "claude-opus-5": _per_mtok(5, 25, 6.25, 10, 0.50),
    "claude-haiku-4-5-20251001": _per_mtok(1, 5, 1.25, 2, 0.10),
    # Superseded models that may still appear in older transcripts.
    "claude-sonnet-4-5": _per_mtok(3, 15, 3.75, 6, 0.30),
    "claude-opus-4-5": _per_mtok(5, 25, 6.25, 10, 0.50),
}

LITELLM_PRICES_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)
CACHE_PATH = Path.home() / ".caddie" / "state" / "pricing-cache.json"

_cached_rates: dict[str, ModelRate] | None = None  # process-local memo, see `_rates()`.


def _rate_from_litellm_entry(entry: dict) -> dict[str, float] | None:
    input_ = entry.get("input_cost_per_token")
    output = entry.get("output_cost_per_token")
    if input_ is None or output is None:
        return None
    return {
        "input": input_,
        "output": output,
        # LiteLLM doesn't always carry cache fields (e.g. for models
        # that don't support prompt caching) - Anthropic's own
        # multipliers (1.25x/2x/0.1x of input) are a reasonable
        # fallback rather than leaving cache usage unpriced.
        "cache_creation_5m": entry.get("cache_creation_input_token_cost", input_ * 1.25),
        "cache_creation_1h": entry.get("cache_creation_input_token_cost_above_1hr", input_ * 2),
        "cache_read": entry.get("cache_read_input_token_cost", input_ * 0.1),
    }


def refresh(timeout: float = 5.0) -> bool:
    """Best-effort refresh of the local pricing cache from LiteLLM's
    catalog. Called from `caddie track-start`, not from the `Stop`
    hook - a hook that fires on every turn must stay network-free, but
    `track-start` fires once per episode/step, where a few seconds for
    a quick fetch is an acceptable cost for pricing that stays current
    without a manual edit to `_BUNDLED_RATES`.

    Never raises - any failure (offline, timeout, upstream format
    change) just leaves the existing cache (or, absent one,
    `_BUNDLED_RATES` alone) in effect. Returns whether the cache was
    actually updated."""
    try:
        req = urllib.request.Request(
            LITELLM_PRICES_URL, headers={"User-Agent": "caddie-cost-tracker"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            catalog = json.loads(resp.read())

        rates = {}
        for model, entry in catalog.items():
            # Only bare `claude-...` keys - no provider prefix
            # (`anthropic.`, `vertex_ai/`, `bedrock/...`) or region/
            # version suffix (`@20251001`, `-v1:0`) - since that's the
            # exact string shape Claude Code's own transcripts use in
            # `message.model`. Confirmed against a real fetch of this
            # file rather than assumed: this is an exact lookup, not
            # fuzzy matching.
            if not model.startswith("claude-") or "/" in model or "@" in model:
                continue
            if not isinstance(entry, dict):
                continue
            rate = _rate_from_litellm_entry(entry)
            if rate is not None:
                rates[model] = rate

        if not rates:
            return False

        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps({"fetched_at": time.time(), "source": LITELLM_PRICES_URL, "rates": rates})
        )
        return True
    except Exception:
        return False


def _load_cached_rates() -> dict[str, ModelRate]:
    if not CACHE_PATH.is_file():
        return {}
    try:
        raw = json.loads(CACHE_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}

    result = {}
    for model, r in raw.get("rates", {}).items():
        try:
            result[model] = ModelRate(
                input=r["input"],
                output=r["output"],
                cache_creation_5m=r["cache_creation_5m"],
                cache_creation_1h=r["cache_creation_1h"],
                cache_read=r["cache_read"],
            )
        except KeyError:
            continue
    return result


def _rates() -> dict[str, ModelRate]:
    """Bundled rates, overlaid by whatever `refresh()` last cached -
    memoized per-process (each `caddie` invocation is a fresh process,
    so this never serves data staler than one cache-file read)."""
    global _cached_rates
    if _cached_rates is None:
        _cached_rates = {**_BUNDLED_RATES, **_load_cached_rates()}
    return _cached_rates


@dataclass
class PricedUsage:
    usage: TokenUsage
    usd: float | None  # None when the model isn't priced anywhere.


def price(model: str, usage: TokenUsage) -> PricedUsage:
    rate = _rates().get(model)
    if rate is None:
        return PricedUsage(usage=usage, usd=None)

    usd = (
        usage.input_tokens * rate.input
        + usage.output_tokens * rate.output
        + usage.cache_creation_5m_tokens * rate.cache_creation_5m
        + usage.cache_creation_1h_tokens * rate.cache_creation_1h
        + usage.cache_read_tokens * rate.cache_read
    )
    return PricedUsage(usage=usage, usd=usd)
