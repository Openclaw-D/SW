from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.contracts.model_gateway import ModelGatewayMode
from app.contracts.agent_communication import AgentMode


BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DISCLAIMER = (
    "本服务仅提供完整脱敏、由确定性业务规则生成的本地演示数据；"
    "不代表真实客户、厂商核验参数、历史统计样本、统计模型或最终审批意见。"
)


def _default_database_path() -> Path:
    local_data = os.getenv("LOCALAPPDATA")
    root = Path(local_data) if local_data else Path(tempfile.gettempdir())
    return (root / "CompareWorkbench" / "signal-council-demo.db").resolve()


def _default_import_root() -> Path:
    return (BACKEND_DIR / "runtime" / "native-material-packs").resolve()


def _optional_material_root(raw_value: str | None) -> tuple[Path | None, bool]:
    """Return a configured archive root without accepting relative paths.

    The bool distinguishes an intentionally unset setting from malformed input
    so the material API can report an honest unavailable state without exposing
    the supplied filesystem value.
    """
    if raw_value is None or not raw_value.strip():
        return None, False
    candidate = Path(raw_value.strip())
    if not candidate.is_absolute():
        return None, True
    return candidate, False


def _default_reconstruction_database_path() -> Path:
    local_data = os.getenv("LOCALAPPDATA")
    root = Path(local_data) if local_data else Path(tempfile.gettempdir())
    return (root / "CompareWorkbench" / "reconstruction.db").resolve()


def _default_reconstruction_asset_root() -> Path:
    local_data = os.getenv("LOCALAPPDATA")
    root = Path(local_data) if local_data else Path(tempfile.gettempdir())
    return (root / "CompareWorkbench" / "reconstruction-assets").resolve()


def _database_path(raw_value: str) -> Path:
    path = Path(raw_value)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path.resolve()


def _cors_origins(raw_value: str) -> tuple[str, ...]:
    values = tuple(item.strip().rstrip("/") for item in raw_value.split(",") if item.strip())
    return values or ("http://127.0.0.1:4317", "http://localhost:4317")


def _agent_provider(raw_value: str) -> str:
    value = raw_value.strip().lower()
    if value not in {"openai", "glm_cli"}:
        raise ValueError("COMPARE_AGENT_PROVIDER must be openai or glm_cli")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "signal-council API"
    app_version: str = "1.0.0"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    session_cookie_secure: bool = False
    session_hours: int = 8
    database_path: Path = field(default_factory=_default_database_path)
    import_root: Path = field(default_factory=_default_import_root)
    # Optional archive root. It must contain native-material-packs/ and is
    # deliberately separate from the controlled-import staging root.
    material_root: Path | None = None
    material_root_config_invalid: bool = False
    reconstruction_database_path: Path = field(
        default_factory=_default_reconstruction_database_path
    )
    reconstruction_asset_root: Path = field(
        default_factory=_default_reconstruction_asset_root
    )
    model_gateway_mode: ModelGatewayMode = ModelGatewayMode.SYNTHETIC
    model_gateway_timeout_seconds: float = 5.0
    # Public, credential-free startup must never reach a provider implicitly.
    agent_mode: AgentMode = AgentMode.SYNTHETIC
    agent_provider: str = "glm_cli"
    agent_timeout_seconds: float = 75.0
    agent_glm_cli_executable: str = "claude.cmd"
    agent_glm_cli_timeout_seconds: float = 60.0
    agent_business_model: str = "glm-5.3[1m]"
    agent_risk_model: str = "glm-5.3[1m]"
    agent_leadership_model: str = "glm-5.3[1m]"
    generator_seed: int = 20260810
    # Direct Settings construction keeps the historical 24-case regression
    # fixture. Normal application startup uses from_environment(), which fixes
    # the public runtime to one de-identified demonstration project.
    demo_project_count: int = 24
    # Direct construction is retained for legacy deterministic test fixtures;
    # normal application startup always goes through from_environment(), whose
    # public default is the standard profile below.
    generator_profile: str = "varied"
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:4317",
        "http://localhost:4317",
    )
    schema_version: str = "1.0"
    data_status: str = "simulated"
    source: str = "deterministic_business_rules"
    disclaimer: str = DEFAULT_DISCLAIMER

    @classmethod
    def from_environment(cls) -> "Settings":
        material_root, material_root_config_invalid = _optional_material_root(
            os.getenv("COMPARE_MATERIAL_ROOT")
        )
        return cls(
            app_name=os.getenv("COMPARE_APP_NAME", "signal-council API"),
            environment=os.getenv("COMPARE_ENVIRONMENT", "development"),
            api_prefix=os.getenv("COMPARE_API_PREFIX", "/api/v1"),
            session_cookie_secure=os.getenv("SIGNAL_COUNCIL_SESSION_COOKIE_SECURE", "false").strip().lower() == "true",
            session_hours=int(os.getenv("SIGNAL_COUNCIL_SESSION_HOURS", "8")),
            database_path=(
                _database_path(os.environ["COMPARE_DATABASE_PATH"])
                if os.getenv("COMPARE_DATABASE_PATH")
                else _default_database_path()
            ),
            import_root=(
                _database_path(os.environ["COMPARE_IMPORT_ROOT"])
                if os.getenv("COMPARE_IMPORT_ROOT")
                else _default_import_root()
            ),
            material_root=material_root,
            material_root_config_invalid=material_root_config_invalid,
            reconstruction_database_path=(
                _database_path(os.environ["COMPARE_RECONSTRUCTION_DATABASE_PATH"])
                if os.getenv("COMPARE_RECONSTRUCTION_DATABASE_PATH")
                else _default_reconstruction_database_path()
            ),
            reconstruction_asset_root=(
                _database_path(os.environ["COMPARE_RECONSTRUCTION_ASSET_ROOT"])
                if os.getenv("COMPARE_RECONSTRUCTION_ASSET_ROOT")
                else _default_reconstruction_asset_root()
            ),
            model_gateway_mode=ModelGatewayMode(
                os.getenv("COMPARE_MODEL_GATEWAY_MODE", "synthetic").lower()
            ),
            model_gateway_timeout_seconds=float(
                os.getenv("COMPARE_MODEL_GATEWAY_TIMEOUT_SECONDS", "5")
            ),
            agent_mode=AgentMode(os.getenv("COMPARE_AGENT_MODE", "synthetic").lower()),
            agent_provider=_agent_provider(
                os.getenv("COMPARE_AGENT_PROVIDER", "glm_cli")
            ),
            agent_timeout_seconds=float(
                os.getenv("COMPARE_AGENT_TIMEOUT_SECONDS", "75")
            ),
            agent_glm_cli_executable=os.getenv(
                "COMPARE_AGENT_GLM_CLI_EXECUTABLE", "claude.cmd"
            ),
            agent_glm_cli_timeout_seconds=float(
                os.getenv("COMPARE_AGENT_GLM_CLI_TIMEOUT_SECONDS", "60")
            ),
            agent_business_model=os.getenv(
                "COMPARE_AGENT_BUSINESS_MODEL",
                os.getenv("COMPARE_AGENT_MODEL", "glm-5.3[1m]"),
            ),
            agent_risk_model=os.getenv(
                "COMPARE_AGENT_RISK_MODEL",
                os.getenv("COMPARE_AGENT_MODEL", "glm-5.3[1m]"),
            ),
            demo_project_count=1,
            agent_leadership_model=os.getenv(
                "COMPARE_AGENT_LEADERSHIP_MODEL",
                os.getenv("COMPARE_AGENT_MODEL", "glm-5.3[1m]"),
            ),
            generator_seed=int(os.getenv("COMPARE_GENERATOR_SEED", "20260810")),
            generator_profile=os.getenv("COMPARE_DEMO_PROFILE", "standard").strip().lower(),
            cors_origins=_cors_origins(
                os.getenv(
                    "COMPARE_CORS_ORIGINS",
                    "http://127.0.0.1:4317,http://localhost:4317",
                )
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()
