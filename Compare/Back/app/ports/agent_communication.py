from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from app.contracts.agent_communication import (
    AgentChatMessageRequest,
    AgentFocusEvent,
    AgentFocusTransitionRequest,
    AgentMessage,
    AgentProviderContext,
    AgentRole,
    AgentRunRecord,
    AgentThread,
    AgentThreadControlRequest,
    AgentThreadCreateRequest,
    AgentTurnRequest,
    AgentTurnResult,
    GeneratedAgentContent,
)
from app.contracts.conclusion import ProjectConclusionReport


@dataclass(frozen=True, slots=True)
class AgentAssembledInput:
    """Canonical read-only provider input; it intentionally has no authority write handle."""

    payload: Mapping[str, Any]
    input_hash: str
    estimated_input_tokens: int

    def __post_init__(self) -> None:
        if len(self.input_hash) != 64 or any(
            character not in "0123456789abcdef" for character in self.input_hash
        ):
            raise ValueError("input_hash must be a lowercase SHA-256 value")
        if self.estimated_input_tokens < 1:
            raise ValueError("estimated_input_tokens must be positive")


@runtime_checkable
class AgentProviderPort(Protocol):
    provider_id: str
    model_id: str
    prompt_version: str
    is_simulated: bool
    supported_roles: frozenset[AgentRole]

    async def generate(
        self,
        role: AgentRole,
        request: AgentTurnRequest,
        context: AgentProviderContext,
        assembled_input: AgentAssembledInput,
        *,
        max_output_tokens: int,
    ) -> GeneratedAgentContent | Mapping[str, Any]: ...


@runtime_checkable
class AgentCommunicationServicePort(Protocol):
    def get_conclusion_report(self, project_id: str) -> ProjectConclusionReport: ...

    def create_thread(
        self,
        project_id: str,
        principal: AgentRole,
        request: AgentThreadCreateRequest,
        *,
        idempotency_key: str,
    ) -> AgentThread: ...

    def get_thread(self, project_id: str, thread_id: str) -> AgentThread: ...

    def list_messages(
        self,
        project_id: str,
        thread_id: str,
        principal: AgentRole,
        *,
        after_sequence: int = 0,
        limit: int = 200,
    ) -> Sequence[AgentMessage]: ...

    def post_message(
        self,
        project_id: str,
        thread_id: str,
        principal: AgentRole,
        request: AgentChatMessageRequest,
        *,
        idempotency_key: str,
    ) -> AgentMessage: ...

    def transition_focus(
        self,
        project_id: str,
        thread_id: str,
        principal: AgentRole,
        request: AgentFocusTransitionRequest,
        *,
        idempotency_key: str,
    ) -> AgentThread: ...

    def list_focus_events(
        self,
        project_id: str,
        thread_id: str,
        principal: AgentRole,
        *,
        after_sequence: int = 0,
        limit: int = 200,
    ) -> Sequence[AgentFocusEvent]: ...

    def control_thread(
        self,
        project_id: str,
        thread_id: str,
        principal: AgentRole,
        request: AgentThreadControlRequest,
        *,
        idempotency_key: str,
    ) -> AgentThread: ...

    async def execute_turn(
        self,
        project_id: str,
        thread_id: str,
        principal: AgentRole,
        request: AgentTurnRequest,
        *,
        idempotency_key: str,
    ) -> AgentTurnResult: ...

    def get_run(
        self, project_id: str, run_id: str, principal: AgentRole
    ) -> AgentRunRecord: ...

    def close(self) -> None: ...


__all__ = [
    "AgentAssembledInput",
    "AgentCommunicationServicePort",
    "AgentProviderPort",
]
