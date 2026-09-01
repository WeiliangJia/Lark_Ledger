from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from .config import Settings
from .diagnostics import run_doctor
from .errors import LedgerError
from .execution import CaseLedger
from .lark import JsonHttpClient, LarkBaseClient, OAuthService, TokenManager
from .manifest import file_sha256, load_manifest, verify_source_documents
from .schema import FIELDS, SchemaManager
from .state import StateStore
from .sync import SyncEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lark-test-ledger",
        description="Validate Codex-generated test cases and synchronize one Lark Base test ledger",
    )
    parser.add_argument("--env-file", type=Path, help="External .env file for Lark commands")
    parser.add_argument("--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="Validate a LedgerManifestV1 JSON file")
    validate.add_argument("manifest", type=Path)
    validate.add_argument("--verify-sources", action="store_true")

    hash_source = commands.add_parser("hash-source", help="Calculate SHA-256 for source documents")
    hash_source.add_argument("paths", type=Path, nargs="+")

    auth = commands.add_parser("auth", help="Authorize the configured Lark user")
    auth.add_argument("--code", help="Authorization code from a company HTTPS callback")

    base = commands.add_parser("base", help="Create an empty Lark Base ledger")
    base.add_argument("action", choices=("create",))
    base.add_argument("--name", default="测试用例账本")
    base.add_argument("--folder-token")
    base.add_argument("--time-zone", default="Australia/Sydney")

    schema = commands.add_parser("schema", help="Inspect or create the simple one-table schema")
    schema.add_argument("action", choices=("plan", "apply", "fields"))

    sync = commands.add_parser("sync", help="Dry-run or commit a manifest to Lark")
    sync.add_argument("manifest", type=Path)
    sync.add_argument("--commit", action="store_true", help="Write changes; omitted means dry-run")

    attachment = commands.add_parser(
        "attachment", help="Append execution evidence to a case's Attachment field"
    )
    attachment.add_argument("action", choices=("add",))
    attachment.add_argument("--case-id", required=True)
    attachment.add_argument("--file", type=Path, required=True)
    attachment.add_argument(
        "--parent-type",
        choices=("auto", "bitable_image", "bitable_file"),
        default="auto",
    )

    case = commands.add_parser("case", help="Read test cases from the configured ledger")
    case.add_argument("action", choices=("list", "get"))
    case.add_argument("--case-id")
    case.add_argument("--module")
    case.add_argument("--result")
    case.add_argument("--submission-only", action="store_true")
    case.add_argument("--limit", type=int, default=100)

    execution = commands.add_parser(
        "execution", help="Select submission cases and write verified execution results"
    )
    execution.add_argument("action", choices=("next", "record"))
    execution.add_argument("--case-id")
    execution.add_argument("--module")
    execution.add_argument("--result")
    execution.add_argument("--notes")
    execution.add_argument("--evidence", type=Path, action="append", default=[])
    execution.add_argument("--evidence-unavailable-reason")

    commands.add_parser("status", help="Show local OAuth and pending batch status")
    commands.add_parser(
        "doctor", help="Verify OAuth, target access and schema without changing Lark records"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows may give redirected Python processes a legacy GBK stdout even
    # when PowerShell and Codex consume UTF-8. Force stable JSON output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        if args.command == "validate":
            manifest = load_manifest(args.manifest)
            if args.verify_sources:
                verify_source_documents(manifest)
            _print({**manifest.summary(), "sources_verified": args.verify_sources})
            return 0
        if args.command == "hash-source":
            _print(
                [
                    {"name": path.name, "path": str(path.resolve()), "sha256": file_sha256(path)}
                    for path in args.paths
                ]
            )
            return 0
        if args.command == "schema" and args.action == "fields":
            _print([field.payload() for field in FIELDS])
            return 0
        settings = _settings(args, parser)
        state, oauth, lark, schema = _runtime(settings)
        if args.command == "auth":
            tokens = oauth.exchange_code(args.code) if args.code else oauth.authenticate_interactive()
            _print({"authorized": True, "scope": tokens.scope, "refresh_expires_at": tokens.refresh_expires_at})
            return 0
        if args.command == "base" and args.action == "create":
            created = lark.create_base(
                args.name,
                folder_token=args.folder_token,
                time_zone=args.time_zone,
            )
            app_token = str(created["app_token"])
            table_id = str(created["default_table_id"])
            base_url = str(created["url"])
            target_url = f"{base_url}?table={table_id}"
            try:
                lark.rename_table(app_token, table_id, settings.lark_table_name)
                default_records = lark.list_records(app_token, table_id)
                default_record_ids = [
                    str(record["record_id"])
                    for record in default_records
                    if record.get("record_id")
                ]
                for start in range(0, len(default_record_ids), 500):
                    lark.batch_delete(
                        app_token,
                        table_id,
                        default_record_ids[start : start + 500],
                    )
                plan = schema.apply(app_token, table_id)
            except LedgerError as exc:
                _print(
                    {
                        "created": True,
                        "name": args.name,
                        "table_name": settings.lark_table_name,
                        "target_url": target_url,
                        "schema_ready": False,
                        "error": str(exc),
                    }
                )
                return 1
            _print(
                {
                    "created": True,
                    "name": args.name,
                    "table_name": settings.lark_table_name,
                    "target_url": target_url,
                    "record_count": lark.record_count(app_token, table_id),
                    "schema_ready": plan.valid,
                }
            )
            return 0
        if args.command == "schema":
            app_token, table_id = lark.resolve_target()
            plan = schema.apply(app_token, table_id) if args.action == "apply" else schema.plan(app_token, table_id)
            _print(plan.to_dict())
            return 0
        if args.command == "sync":
            manifest = load_manifest(args.manifest)
            verify_source_documents(manifest)
            engine = SyncEngine(
                lark=lark,
                schema=schema,
                state=state,
                archive_dir=settings.archive_dir,
                batch_size=settings.batch_size,
            )
            if args.commit:
                result = engine.commit(manifest)
            else:
                _, _, plan = engine.plan(manifest)
                result = {**manifest.summary(), **plan.summary(), "committed": False}
            _print(result)
            return 0
        if args.command == "attachment" and args.action == "add":
            app_token, table_id = lark.resolve_target()
            matches = [
                record
                for record in lark.list_records(app_token, table_id)
                if record.get("fields", {}).get("用例ID") == args.case_id
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"Expected exactly one Lark record for case ID {args.case_id!r}; found {len(matches)}"
                )
            record_id = str(matches[0]["record_id"])
            file_token = lark.upload_bitable_attachment(
                app_token,
                args.file,
                parent_type=args.parent_type,
            )
            attachments = lark.append_attachment(
                app_token,
                table_id,
                record_id,
                file_token,
            )
            verified = lark.get_record(app_token, table_id, record_id)
            verified_tokens = {
                item.get("file_token")
                for item in verified.get("fields", {}).get("Attachment", [])
                if isinstance(item, dict)
            }
            if file_token not in verified_tokens:
                raise LedgerError("Attachment write-back verification failed")
            _print(
                {
                    "attached": True,
                    "case_id": args.case_id,
                    "record_id": record_id,
                    "file": str(args.file.resolve()),
                    "file_token": file_token,
                    "attachment_count": len(attachments),
                    "verified": True,
                }
            )
            return 0
        if args.command == "case":
            ledger = CaseLedger(lark)
            if args.action == "get":
                if not args.case_id:
                    parser.error("case get requires --case-id")
                _print(ledger.get_case(args.case_id))
            else:
                if args.limit < 1:
                    parser.error("--limit must be a positive integer")
                _print(
                    ledger.list_cases(
                        module=args.module,
                        result=args.result,
                        submission_only=args.submission_only,
                        limit=args.limit,
                    )
                )
            return 0
        if args.command == "execution":
            ledger = CaseLedger(lark)
            if args.action == "next":
                _print(
                    ledger.next_submission_case(module=args.module)
                    or {"case": None, "message": "No unexecuted submission case matched"}
                )
            else:
                if not args.case_id or not args.result:
                    parser.error("execution record requires --case-id and --result")
                _print(
                    ledger.record_result(
                        args.case_id,
                        args.result,
                        notes=args.notes,
                        evidence=tuple(args.evidence),
                        evidence_unavailable_reason=args.evidence_unavailable_reason,
                    )
                )
            return 0
        if args.command == "status":
            tokens = state.load_tokens()
            _print(
                {
                    "authorized": tokens is not None,
                    "scope": tokens.scope if tokens else None,
                    "refresh_expires_at": tokens.refresh_expires_at if tokens else None,
                    "pending_batches": len(state.pending()),
                    "state_db": str(settings.state_db_path),
                    "token_db": str(settings.lark_token_db_path),
                    "archive_dir": str(settings.archive_dir),
                }
            )
            return 0
        if args.command == "doctor":
            _print(run_doctor(state=state, lark=lark, schema=schema))
            return 0
        parser.error("unknown command")
        return 2
    except (LedgerError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _settings(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Settings:
    if args.env_file is None:
        parser.error("--env-file is required for this command")
    needs_target = args.command in {
        "schema",
        "sync",
        "attachment",
        "case",
        "execution",
        "doctor",
    }
    return Settings.from_env_file(
        args.env_file.resolve(), require_base_url=needs_target
    )


def _runtime(settings: Settings):
    state = StateStore(
        settings.state_db_path, token_db_path=settings.lark_token_db_path
    )
    http = JsonHttpClient(timeout=settings.request_timeout)
    oauth = OAuthService(settings, state, http)
    token_manager = TokenManager(oauth, state, settings.oauth_lock_path)
    lark = LarkBaseClient(settings, token_manager, http)
    schema = SchemaManager(lark)
    return state, oauth, lark, schema


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
