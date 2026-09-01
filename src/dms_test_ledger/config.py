from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError


def load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ConfigError(f"Environment file not found: {path}")
    values: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"Invalid .env line {line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            raise ConfigError(f"Invalid .env line {line_number}: empty key")
        values[key] = value
    return values


def parse_base_url(url: str) -> tuple[str, str | None]:
    app_token, table_id, wiki_token = parse_target_url(url)
    if wiki_token is not None or app_token is None:
        raise ConfigError("Lark URL must contain /base/<app_token>")
    return app_token, table_id


def parse_target_url(url: str) -> tuple[str | None, str | None, str | None]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ConfigError("LARK_BASE_URL must be an https:// Lark URL")
    parts = [part for part in parsed.path.split("/") if part]
    table_id = urllib.parse.parse_qs(parsed.query).get("table", [None])[0]
    if "base" in parts:
        index = parts.index("base")
        if index + 1 >= len(parts) or not parts[index + 1]:
            raise ConfigError("Lark Base URL does not contain an app_token")
        return parts[index + 1], table_id, None
    if "wiki" in parts:
        index = parts.index("wiki")
        if index + 1 >= len(parts) or not parts[index + 1]:
            raise ConfigError("Lark Wiki URL does not contain a node token")
        return None, table_id, parts[index + 1]
    raise ConfigError("LARK_BASE_URL must contain /base/<token> or /wiki/<token>")


@dataclass(frozen=True)
class Settings:
    lark_app_id: str
    lark_app_secret: str
    lark_redirect_uri: str
    lark_oauth_scopes: str
    lark_api_base_url: str
    lark_authorize_url: str
    lark_base_url: str
    lark_table_name: str
    state_db_path: Path
    lark_token_db_path: Path
    archive_dir: Path
    batch_size: int
    request_timeout: int
    oauth_lock_path: Path | None = None

    @classmethod
    def from_env_file(
        cls, env_path: Path, *, require_base_url: bool = True
    ) -> "Settings":
        project_values = load_env_file(env_path)
        identity_value = os.environ.get(
            "LARK_IDENTITY_ENV_FILE",
            project_values.get("LARK_IDENTITY_ENV_FILE", ""),
        ).strip()
        identity_values: dict[str, str] = {}
        if identity_value:
            identity_path = _resolve_config_path(identity_value, env_path.parent)
            if identity_path == env_path.resolve():
                raise ConfigError("LARK_IDENTITY_ENV_FILE must not reference itself")
            identity_values = load_env_file(identity_path)
        # Project values intentionally win over shared identity defaults. Process
        # environment variables still have the highest precedence in get().
        file_values = {**identity_values, **project_values}

        def get(name: str, default: str = "") -> str:
            return os.environ.get(name, file_values.get(name, default)).strip()

        required = {
            "LARK_APP_ID": get("LARK_APP_ID"),
            "LARK_APP_SECRET": get("LARK_APP_SECRET"),
            "LARK_REDIRECT_URI": get("LARK_REDIRECT_URI"),
        }
        base_url = get("LARK_BASE_URL")
        if require_base_url:
            required["LARK_BASE_URL"] = base_url
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ConfigError("Missing required settings: " + ", ".join(missing))

        if base_url:
            parse_target_url(base_url)

        state_value = get("LEDGER_STATE_DB")
        if not state_value:
            raise ConfigError("LEDGER_STATE_DB is required")
        _reject_path_placeholder("LEDGER_STATE_DB", state_value)
        state_path = _resolve_config_path(state_value, env_path.parent)

        token_value = get("LARK_TOKEN_DB")
        if not token_value:
            raise ConfigError(
                "LARK_TOKEN_DB is required; when reusing the existing app, point it to the existing DmsLarkSync state.sqlite3"
            )
        _reject_path_placeholder("LARK_TOKEN_DB", token_value)
        token_path = _resolve_config_path(token_value, env_path.parent)

        batch_size = int(get("LARK_BATCH_SIZE", "200"))
        if batch_size < 1 or batch_size > 1000:
            raise ConfigError("LARK_BATCH_SIZE must be between 1 and 1000")

        archive_dir = _resolve_config_path(
            get("LEDGER_ARCHIVE_DIR", str(state_path.parent / "manifests")),
            env_path.parent,
        )
        workspace_root = Path(__file__).resolve().parents[3]

        return cls(
            lark_app_id=required["LARK_APP_ID"],
            lark_app_secret=required["LARK_APP_SECRET"],
            lark_redirect_uri=required["LARK_REDIRECT_URI"],
            lark_oauth_scopes=get(
                "LARK_OAUTH_SCOPES",
                "offline_access bitable:app wiki:node:read auth:user.id:read",
            ),
            lark_api_base_url=get("LARK_API_BASE_URL", "https://open.larksuite.com"),
            lark_authorize_url=get(
                "LARK_AUTHORIZE_URL", "https://open.larksuite.com/open-apis/authen/v1/authorize"
            ),
            lark_base_url=base_url,
            lark_table_name=get("LARK_TABLE_NAME", "测试用例"),
            state_db_path=state_path,
            lark_token_db_path=token_path,
            archive_dir=archive_dir,
            batch_size=batch_size,
            request_timeout=int(get("LARK_REQUEST_TIMEOUT", "30")),
            oauth_lock_path=_resolve_config_path(
                get(
                    "LARK_OAUTH_LOCK_PATH",
                    str(workspace_root / ".local" / "lark-oauth-refresh.lock"),
                ),
                env_path.parent,
            ),
        )


def _reject_path_placeholder(name: str, value: str) -> None:
    lowered = value.lower().replace("/", "\\")
    placeholders = ("\\your-name\\", "\\<you>\\", "\\current-user\\")
    if any(marker in lowered for marker in placeholders):
        raise ConfigError(
            f"{name} still contains a template user-name placeholder; replace it with an existing absolute path"
        )


def _resolve_config_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()
