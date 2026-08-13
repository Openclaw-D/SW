"""Explicit, file-discovery-free replay of the production provider boundary."""

from evals.model_gateway.provider_replay.harness import (
    ProviderReplayEvidence,
    ProviderReplayHarness,
)
from evals.model_gateway.provider_replay.r3_replay import (
    R3_REPLAY_MANIFEST,
    build_r3_formal_request,
    render_r3_replay_markdown,
    run_r3_provider_replay,
)

__all__ = [
    "R3_REPLAY_MANIFEST",
    "ProviderReplayEvidence",
    "ProviderReplayHarness",
    "build_r3_formal_request",
    "render_r3_replay_markdown",
    "run_r3_provider_replay",
]
