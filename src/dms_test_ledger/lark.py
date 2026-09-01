from __future__ import annotations

import json
import logging
import mimetypes
import os
import secrets
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from datetime import datetime, timezone
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable

from .config import Settings, parse_target_url
from .errors import AuthenticationError, LarkApiError
from .state import StateStore, TokenSet


RETRYABLE_LARK_CODES = {1254036, 1254290, 1255040, 99991400, 99991401, 1061045}


class JsonHttpClient:
    def __init__(
        self,
        *,
        timeout: int = 30,
        max_attempts: int = 5,
        logger: logging.Logger | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.logger = logger or logging.getLogger("dms_test_ledger")
        self.sleep = sleep

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        raw_body: bytes | None = None,
        require_lark_success: bool = True,
    ) -> dict[str, Any]:
        if body is not None and raw_body is not None:
            raise ValueError("body and raw_body are mutually exclusive")
        encoded = (
            raw_body
            if raw_body is not None
            else None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        )
        request_headers = {"Accept": "application/json", **(headers or {})}
        if body is not None:
            request_headers["Content-Type"] = "application/json; charset=utf-8"

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            status: int | None = None
            response_body = b""
            try:
                request = urllib.request.Request(
                    url=url, data=encoded, headers=request_headers, method=method.upper()
                )
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    status = response.status
                    response_body = response.read()
            except urllib.error.HTTPError as exc:
                status = exc.code
                response_body = exc.read()
            except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
                last_error = exc
                if attempt < self.max_attempts:
                    self._backoff(attempt, type(exc).__name__)
                    continue
                raise LarkApiError("Lark network request failed after retries") from exc

            try:
                payload = json.loads(response_body.decode("utf-8")) if response_body else {}
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise LarkApiError("Lark returned a non-JSON response", status=status) from exc
            code = payload.get("code")
            retryable = (
                status == 429
                or (status is not None and status >= 500)
                or code in RETRYABLE_LARK_CODES
            )
            if retryable and attempt < self.max_attempts:
                self._backoff(attempt, f"HTTP {status}, code {code}")
                continue
            if status is None or not 200 <= status < 300:
                raise LarkApiError(
                    f"Lark HTTP request failed: HTTP {status}, {_safe_error(payload)}",
                    code=int(code) if isinstance(code, int) else None,
                    status=status,
                )
            if require_lark_success and code not in (None, 0):
                raise LarkApiError(
                    f"Lark API rejected the request: code {code}, {_safe_error(payload)}",
                    code=int(code) if isinstance(code, int) else None,
                    status=status,
                )
            return payload
        raise LarkApiError("Lark request failed") from last_error

    def _backoff(self, attempt: int, reason: str) -> None:
        delay = min(2 ** (attempt - 1), 16)
        self.logger.warning("Retrying Lark request in %ss (%s)", delay, reason)
        self.sleep(delay)


def _safe_error(payload: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("error", "error_description", "msg", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in values:
            values.append(value.strip())
    return ": ".join(values) if values else "unknown error"


def _encode_multipart(
    boundary: str,
    fields: dict[str, str],
    *,
    file_path: Path,
    file_content_type: str,
) -> bytes:
    delimiter = f"--{boundary}\r\n".encode("ascii")
    body = bytearray()
    for name, value in fields.items():
        body.extend(delimiter)
        body.extend(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii")
        )
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")
    safe_filename = file_path.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
    body.extend(delimiter)
    body.extend(
        (
            'Content-Disposition: form-data; name="file"; '
            f'filename="{safe_filename}"\r\n'
        ).encode("utf-8")
    )
    body.extend(f"Content-Type: {file_content_type}\r\n\r\n".encode("ascii"))
    body.extend(file_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("ascii"))
    return bytes(body)


class OAuthService:
    def __init__(self, settings: Settings, state: StateStore, http: JsonHttpClient):
        self.settings = settings
        self.state = state
        self.http = http

    def authorization_url(self, state_value: str) -> str:
        query = urllib.parse.urlencode(
            {
                "app_id": self.settings.lark_app_id,
                "redirect_uri": self.settings.lark_redirect_uri,
                "scope": self.settings.lark_oauth_scopes,
                "state": state_value,
                "response_type": "code",
            }
        )
        return f"{self.settings.lark_authorize_url}?{query}"

    def authenticate_interactive(self, *, timeout_seconds: int = 180) -> TokenSet:
        redirect = urllib.parse.urlparse(self.settings.lark_redirect_uri)
        if redirect.scheme != "http" or redirect.hostname not in {"127.0.0.1", "localhost"}:
            raise AuthenticationError(
                "Interactive auth requires an http://127.0.0.1 callback; use auth --code for a company callback"
            )
        expected_path = redirect.path or "/"
        state_value = secrets.token_urlsafe(32)
        result: dict[str, str] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != expected_path:
                    self.send_error(404)
                    return
                params = urllib.parse.parse_qs(parsed.query)
                result["state"] = params.get("state", [""])[0]
                result["code"] = params.get("code", [""])[0]
                result["error"] = params.get("error", [""])[0]
                body = b"<html><body><h2>Lark authorization received. You can close this window.</h2></body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        server = HTTPServer((redirect.hostname, redirect.port or 80), Handler)
        server.timeout = timeout_seconds
        url = self.authorization_url(state_value)
        print(f"Open this URL if the browser does not start automatically:\n{url}\n")
        webbrowser.open(url)
        try:
            server.handle_request()
        finally:
            server.server_close()
        if result.get("state") != state_value:
            raise AuthenticationError("Lark OAuth state mismatch or callback timed out")
        if result.get("error"):
            raise AuthenticationError(f"Lark authorization failed: {result['error']}")
        if not result.get("code"):
            raise AuthenticationError("Lark callback did not contain an authorization code")
        return self.exchange_code(result["code"])

    def exchange_code(self, code: str) -> TokenSet:
        payload = self.http.request(
            "POST",
            f"{self.settings.lark_api_base_url}/open-apis/authen/v2/oauth/token",
            body={
                "grant_type": "authorization_code",
                "client_id": self.settings.lark_app_id,
                "client_secret": self.settings.lark_app_secret,
                "code": code,
                "redirect_uri": self.settings.lark_redirect_uri,
            },
        )
        tokens = self._parse_tokens(payload)
        self.state.save_tokens(tokens)
        return tokens

    def refresh(self, refresh_token: str, previous: TokenSet) -> TokenSet:
        payload = self.http.request(
            "POST",
            f"{self.settings.lark_api_base_url}/open-apis/authen/v2/oauth/token",
            body={
                "grant_type": "refresh_token",
                "client_id": self.settings.lark_app_id,
                "client_secret": self.settings.lark_app_secret,
                "refresh_token": refresh_token,
            },
        )
        tokens = self._parse_tokens(payload, previous=previous)
        self.state.save_tokens(tokens)
        return tokens

    @staticmethod
    def _parse_tokens(payload: dict[str, Any], previous: TokenSet | None = None) -> TokenSet:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        access_token = str(data.get("access_token", ""))
        refresh_token = str(data.get("refresh_token", ""))
        if not access_token or not refresh_token:
            raise AuthenticationError("Lark token response omitted access_token or refresh_token")
        now = int(datetime.now(timezone.utc).timestamp())
        access_ttl = int(data.get("expires_in", 0))
        refresh_ttl = int(data.get("refresh_token_expires_in", data.get("refresh_expires_in", 0)))
        if access_ttl <= 0:
            raise AuthenticationError("Invalid Lark access token lifetime")
        if refresh_ttl > 0:
            refresh_expires_at = now + refresh_ttl
        elif previous:
            refresh_expires_at = previous.refresh_expires_at
        else:
            raise AuthenticationError("Invalid Lark refresh token lifetime")
        return TokenSet(
            access_token=access_token,
            access_expires_at=now + access_ttl,
            refresh_token=refresh_token,
            refresh_expires_at=refresh_expires_at,
            scope=str(data.get("scope", previous.scope if previous else "")),
        )


class TokenManager:
    def __init__(
        self,
        oauth: OAuthService,
        state: StateStore,
        lock_path: Path | None = None,
    ):
        self.oauth = oauth
        self.state = state
        self.lock_path = lock_path

    def get_access_token(self) -> str:
        tokens = self.state.load_tokens()
        if tokens is None:
            raise AuthenticationError("No Lark OAuth token found; run auth first")
        now = int(datetime.now(timezone.utc).timestamp())
        if now + 300 < tokens.access_expires_at:
            return tokens.access_token
        with _oauth_refresh_lock(self.state.token_db_path, self.lock_path):
            # Another process may have rotated the token while this process was
            # waiting for the shared lock. Always reload before refreshing.
            tokens = self.state.load_tokens()
            if tokens is None:
                raise AuthenticationError("No Lark OAuth token found; run auth first")
            now = int(datetime.now(timezone.utc).timestamp())
            if now + 300 < tokens.access_expires_at:
                return tokens.access_token
            if now + 60 >= tokens.refresh_expires_at:
                raise AuthenticationError("Lark refresh token has expired; run auth again")
            return self.oauth.refresh(tokens.refresh_token, tokens).access_token


class LarkBaseClient:
    def __init__(self, settings: Settings, token_manager: TokenManager, http: JsonHttpClient):
        self.settings = settings
        self.token_manager = token_manager
        self.http = http

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        suffix = "?" + urllib.parse.urlencode(query) if query else ""
        return self.http.request(
            method,
            f"{self.settings.lark_api_base_url}{path}{suffix}",
            headers={"Authorization": f"Bearer {self.token_manager.get_access_token()}"},
            body=body,
        )

    def create_base(
        self,
        name: str,
        *,
        folder_token: str | None = None,
        time_zone: str = "Australia/Sydney",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name, "time_zone": time_zone}
        if folder_token:
            body["folder_token"] = folder_token
        response = self._request(
            "POST", "/open-apis/bitable/v1/apps", body=body
        )
        app = response.get("data", {}).get("app")
        if not isinstance(app, dict):
            raise LarkApiError("Lark create Base response omitted app metadata")
        required = ("app_token", "default_table_id", "url")
        missing = [key for key in required if not isinstance(app.get(key), str) or not app[key]]
        if missing:
            raise LarkApiError(
                "Lark create Base response omitted: " + ", ".join(missing)
            )
        return dict(app)

    def rename_table(self, app_token: str, table_id: str, name: str) -> None:
        self._request(
            "PATCH",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}",
            body={"name": name},
        )

    def resolve_target(self) -> tuple[str, str]:
        app_token, url_table_id, wiki_token = parse_target_url(self.settings.lark_base_url)
        if wiki_token is not None:
            app_token = self.resolve_wiki_app_token(wiki_token)
        if app_token is None:
            raise LarkApiError("Could not resolve a Base app_token from the configured Lark URL")
        tables = self.list_tables(app_token)
        if url_table_id:
            matches = [item for item in tables if item.get("table_id") == url_table_id]
            if len(matches) != 1:
                raise LarkApiError(f"Table ID from LARK_BASE_URL was not found: {url_table_id}")
            actual_name = str(matches[0].get("name", ""))
            if actual_name != self.settings.lark_table_name:
                raise LarkApiError(
                    f"Configured table name mismatch: expected {self.settings.lark_table_name!r}, got {actual_name!r}"
                )
            return app_token, url_table_id
        matches = [item for item in tables if item.get("name") == self.settings.lark_table_name]
        if len(matches) != 1:
            raise LarkApiError(
                f"Expected exactly one table named {self.settings.lark_table_name!r}; found {len(matches)}"
            )
        return app_token, str(matches[0]["table_id"])

    def resolve_wiki_app_token(self, wiki_token: str) -> str:
        response = self._request(
            "GET",
            "/open-apis/wiki/v2/spaces/get_node",
            query={"token": wiki_token},
        )
        node = response.get("data", {}).get("node", {})
        obj_type = node.get("obj_type")
        obj_token = node.get("obj_token")
        if obj_type != "bitable":
            raise LarkApiError(
                f"Configured Wiki node is {obj_type!r}, not a Lark Base (bitable)"
            )
        if not isinstance(obj_token, str) or not obj_token:
            raise LarkApiError("Wiki node response omitted the Base obj_token")
        return obj_token

    def list_tables(self, app_token: str) -> list[dict[str, Any]]:
        return self._paged(
            f"/open-apis/bitable/v1/apps/{app_token}/tables", page_size=100
        )

    def list_fields(self, app_token: str, table_id: str) -> list[dict[str, Any]]:
        return self._paged(
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
            page_size=100,
        )

    def create_field(
        self, app_token: str, table_id: str, definition: dict[str, Any]
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
            body=definition,
        )
        return dict(response.get("data", {}).get("field", {}))

    def update_field(
        self, app_token: str, table_id: str, field_id: str, definition: dict[str, Any]
    ) -> dict[str, Any]:
        response = self._request(
            "PUT",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{field_id}",
            body=definition,
        )
        return dict(response.get("data", {}).get("field", {}))

    def list_records(self, app_token: str, table_id: str) -> list[dict[str, Any]]:
        return self._paged(
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            page_size=500,
            query_extra={"user_id_type": "open_id"},
        )

    def get_record(
        self, app_token: str, table_id: str, record_id: str
    ) -> dict[str, Any]:
        response = self._request(
            "GET",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            query={"user_id_type": "open_id"},
        )
        record = response.get("data", {}).get("record")
        if not isinstance(record, dict):
            raise LarkApiError("Lark get record response omitted record data")
        return dict(record)

    def upload_bitable_attachment(
        self,
        app_token: str,
        file_path: Path,
        *,
        parent_type: str = "auto",
    ) -> str:
        path = file_path.resolve()
        if not path.is_file():
            raise ValueError(f"Attachment file does not exist: {path}")
        size = path.stat().st_size
        if size <= 0:
            raise ValueError("Attachment file must not be empty")
        if size > 20 * 1024 * 1024:
            raise ValueError("Attachment exceeds Lark's 20 MB single-upload limit")
        if parent_type == "auto":
            mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            parent_type = "bitable_image" if mime_type.startswith("image/") else "bitable_file"
        elif parent_type not in {"bitable_image", "bitable_file"}:
            raise ValueError("parent_type must be auto, bitable_image, or bitable_file")
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        boundary = "----LarkTestLedger" + uuid.uuid4().hex
        raw_body = _encode_multipart(
            boundary,
            {
                "file_name": path.name,
                "parent_type": parent_type,
                "parent_node": app_token,
                "size": str(size),
            },
            file_path=path,
            file_content_type=mime_type,
        )
        response = self.http.request(
            "POST",
            f"{self.settings.lark_api_base_url}/open-apis/drive/v1/medias/upload_all",
            headers={
                "Authorization": f"Bearer {self.token_manager.get_access_token()}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            raw_body=raw_body,
        )
        file_token = response.get("data", {}).get("file_token")
        if not isinstance(file_token, str) or not file_token:
            raise LarkApiError("Lark upload response omitted file_token")
        return file_token

    def append_attachment(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        file_token: str,
        *,
        field_name: str = "Attachment",
    ) -> list[dict[str, str]]:
        if not file_token:
            raise ValueError("file_token must not be empty")
        record = self.get_record(app_token, table_id, record_id)
        current = record.get("fields", {}).get(field_name, [])
        attachments: list[dict[str, str]] = []
        seen: set[str] = set()
        if isinstance(current, list):
            for item in current:
                token = item.get("file_token") if isinstance(item, dict) else None
                if isinstance(token, str) and token and token not in seen:
                    attachments.append({"file_token": token})
                    seen.add(token)
        if file_token not in seen:
            attachments.append({"file_token": file_token})
            self.batch_update(
                app_token,
                table_id,
                [{"record_id": record_id, "fields": {field_name: attachments}}],
            )
        return attachments

    def record_count(self, app_token: str, table_id: str) -> int:
        response = self._request(
            "GET",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            query={"page_size": 1},
        )
        total = response.get("data", {}).get("total")
        if not isinstance(total, int):
            raise LarkApiError("Lark record list response omitted total")
        return total

    def batch_create(
        self,
        app_token: str,
        table_id: str,
        records: list[dict[str, Any]],
        *,
        client_token: str | None = None,
    ) -> list[dict[str, Any]]:
        response = self._request(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
            query={
                "client_token": client_token or str(uuid.uuid4()),
                "ignore_consistency_check": "false",
                "user_id_type": "open_id",
            },
            body={"records": records},
        )
        created = response.get("data", {}).get("records", [])
        if len(created) != len(records):
            raise LarkApiError("Lark batch_create returned an incomplete record list")
        return list(created)

    def batch_update(
        self,
        app_token: str,
        table_id: str,
        records: list[dict[str, Any]],
        *,
        client_token: str | None = None,
    ) -> list[dict[str, Any]]:
        response = self._request(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update",
            query={
                "client_token": client_token or str(uuid.uuid4()),
                "ignore_consistency_check": "false",
                "user_id_type": "open_id",
            },
            body={"records": records},
        )
        updated = response.get("data", {}).get("records", [])
        if len(updated) != len(records):
            raise LarkApiError("Lark batch_update returned an incomplete record list")
        return list(updated)

    def batch_delete(
        self, app_token: str, table_id: str, record_ids: list[str]
    ) -> list[dict[str, Any]]:
        if not record_ids:
            return []
        if len(record_ids) > 500:
            raise ValueError("Lark batch_delete accepts at most 500 record IDs")
        response = self._request(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete",
            query={"ignore_consistency_check": "false"},
            body={"records": record_ids},
        )
        deleted = response.get("data", {}).get("records", [])
        if len(deleted) != len(record_ids):
            raise LarkApiError("Lark batch_delete returned an incomplete record list")
        return list(deleted)

    def _paged(
        self,
        path: str,
        *,
        page_size: int,
        query_extra: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token = ""
        while True:
            query = {"page_size": page_size, **(query_extra or {})}
            if page_token:
                query["page_token"] = page_token
            response = self._request("GET", path, query=query)
            data = response.get("data", {})
            page_items = data.get("items", [])
            if not isinstance(page_items, list):
                raise LarkApiError("Lark paged response items must be an array")
            items.extend(item for item in page_items if isinstance(item, dict))
            if not data.get("has_more"):
                return items
            page_token = str(data.get("page_token", ""))
            if not page_token:
                raise LarkApiError("Lark response set has_more without page_token")


@contextmanager
def _oauth_refresh_lock(token_db_path: Path, override_path: Path | None = None):
    configured_lock = os.environ.get(
        "LARK_OAUTH_LOCK_PATH",
        os.environ.get("DMS_LARK_OAUTH_LOCK_PATH", ""),
    ).strip()
    lock_path = (
        override_path
        if override_path is not None
        else Path(configured_lock).expanduser().resolve()
        if configured_lock
        else token_db_path.with_name(token_db_path.name + ".oauth-refresh.lock")
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    try:
        handle.seek(0)
        if handle.read(1) == b"":
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
