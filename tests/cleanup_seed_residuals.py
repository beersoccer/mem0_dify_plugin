from __future__ import annotations
# ruff: noqa: I001

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from tests.helpers.dify_cleanup import cleanup_seeded_conversations  # noqa: E402
from tests.helpers.dify_env import (  # noqa: E402
    create_dify_client,
    load_env_config,
)
from tests.helpers.dify_seed import SeedManifest, SeededConversation  # noqa: E402
from utils.dify_client import DifyClient  # noqa: E402


@dataclass(frozen=True)
class CandidateConversation:
    user_id: str
    conversation_id: str
    case_name: str
    source_file: str
    message_ids: list[str]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Clean up residual seeded Dify conversations from manifest artifacts. "
            "Defaults to dry-run; use --execute to delete."
        )
    )
    parser.add_argument(
        "--env-file",
        default="",
        help=(
            "Explicit env file path (e.g. tests/.env.local). "
            "If omitted, loader falls back to profile defaults."
        ),
    )
    parser.add_argument(
        "--artifacts-dir",
        default="",
        help=(
            "Artifact directory override. Defaults to TEST_ARTIFACTS_DIR or "
            "tests/artifacts/<profile>."
        ),
    )
    parser.add_argument(
        "--glob",
        default="*manifest*.json",
        help="Manifest file glob pattern (default: *manifest*.json).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete conversations. Without this flag, script only previews targets.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip post-delete existence verification.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Max pages per scan source for force-all mode (default: 50).",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=3,
        help="Max force-all cleanup rounds with re-scan (default: 3).",
    )
    parser.add_argument(
        "--force-all",
        action="store_true",
        help=(
            "Force full cleanup for this app scope by scanning Dify live data "
            "instead of manifest-only mode."
        ),
    )
    return parser


def _resolve_profile(env: dict[str, str]) -> str:
    profile = (env.get("TEST_PROFILE") or "").strip().lower()
    if profile in {"local", "remote", "ci"}:
        return profile
    return "ci" if os.getenv("GITHUB_ACTIONS") == "true" else "local"


def _expand_artifacts_template(raw: str, profile: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    # Allow .env style placeholders to avoid repeating a hard-coded profile.
    replacements = {
        "${TEST_PROFILE}": profile,
        "$TEST_PROFILE": profile,
    }
    for token, replacement in replacements.items():
        value = value.replace(token, replacement)
    return value


def resolve_artifacts_dir(cli_value: str, env: dict[str, str]) -> Path:
    profile = _resolve_profile(env)
    raw = (cli_value or "").strip() or (env.get("TEST_ARTIFACTS_DIR") or "").strip()
    raw = _expand_artifacts_template(raw, profile)
    if raw:
        candidate = Path(raw)
        tests_dir = Path(__file__).resolve().parent
        if candidate.is_absolute():
            return candidate.resolve()
        if candidate.parts and candidate.parts[0] == "tests":
            return (Path(__file__).resolve().parents[1] / candidate).resolve()
        return (tests_dir / candidate).resolve()

    return (Path(__file__).resolve().parent / "artifacts" / profile).resolve()


def iter_manifest_files(artifacts_dir: Path, pattern: str) -> list[Path]:
    return sorted(path for path in artifacts_dir.rglob(pattern) if path.is_file())


def _to_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _parse_user_list(raw: str) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in re.split(r"[,\s;]+", raw) if item.strip()]


def _extract_explicit_env_users(env: dict[str, str]) -> set[str]:
    users: set[str] = set()
    raw = (env.get("DIFY_CLEANUP_USERS") or "").strip()
    if raw:
        users.update(_parse_user_list(raw))
    return users


def collect_candidates(manifest_files: list[Path]) -> tuple[list[CandidateConversation], list[str]]:
    candidates: dict[tuple[str, str], CandidateConversation] = {}
    skipped: list[str] = []

    for path in manifest_files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{path}: invalid json ({exc})")
            continue

        conversations = raw.get("conversations")
        if not isinstance(conversations, list):
            skipped.append(f"{path}: no conversations list")
            continue

        for item in conversations:
            if not isinstance(item, dict):
                continue
            user_id = str(item.get("user_id") or "").strip()
            conversation_id = str(item.get("conversation_id") or "").strip()
            if not user_id or not conversation_id:
                continue
            key = (user_id, conversation_id)
            candidates[key] = CandidateConversation(
                user_id=user_id,
                conversation_id=conversation_id,
                case_name=str(item.get("case_name") or "recovered"),
                source_file=str(path),
                message_ids=_to_str_list(item.get("message_ids")),
            )

    return sorted(candidates.values(), key=lambda x: (x.user_id, x.conversation_id)), skipped


def _scan_user_conversations(
    client: DifyClient, *, user_id: str, max_pages: int
) -> list[CandidateConversation]:
    items: dict[str, CandidateConversation] = {}
    cursor: str | None = None
    pages = 0
    while pages < max_pages:
        page = client.list_conversations(user_id=user_id, limit=100, last_id=cursor)
        for row in page.items:
            conversation_id = str(row.get("id") or "").strip()
            if not conversation_id:
                continue
            name = str(row.get("name") or "").strip() or "live-scan"
            items[conversation_id] = CandidateConversation(
                user_id=user_id,
                conversation_id=conversation_id,
                case_name=f"live:{name}",
                source_file=f"live-scan:{user_id}",
                message_ids=[],
            )
        if not page.has_more or not page.next_cursor:
            break
        cursor = page.next_cursor
        pages += 1
    return sorted(items.values(), key=lambda x: x.conversation_id)


def _scan_global_conversations(
    client: DifyClient, *, max_pages: int
) -> tuple[list[CandidateConversation], str]:
    """Try global listing without user filter and infer user IDs from response rows."""
    found: dict[tuple[str, str], CandidateConversation] = {}
    cursor: str | None = None
    pages = 0
    scanned_rows = 0
    while pages < max_pages:
        page = client.list_conversations(user_id="", limit=100, last_id=cursor)
        scanned_rows += len(page.items)
        for row in page.items:
            conversation_id = str(row.get("id") or "").strip()
            user_id = str(
                row.get("user")
                or row.get("user_id")
                or row.get("userId")
                or row.get("created_by")
                or ""
            ).strip()
            if not conversation_id or not user_id:
                continue
            name = str(row.get("name") or "").strip() or "live-global"
            item = CandidateConversation(
                user_id=user_id,
                conversation_id=conversation_id,
                case_name=f"live-global:{name}",
                source_file="live-scan:global",
                message_ids=[],
            )
            found[(item.user_id, item.conversation_id)] = item
        if not page.has_more or not page.next_cursor:
            break
        cursor = page.next_cursor
        pages += 1
    note = (
        f"global-scan: {scanned_rows} row(s) scanned, "
        f"{len(found)} candidate(s) inferred"
    )
    return sorted(found.values(), key=lambda x: (x.user_id, x.conversation_id)), note


def collect_live_candidates(
    client: DifyClient,
    *,
    user_ids: list[str],
    max_pages: int,
) -> tuple[list[CandidateConversation], list[str]]:
    collected: dict[tuple[str, str], CandidateConversation] = {}
    notes: list[str] = []
    for user_id in user_ids:
        try:
            scanned = _scan_user_conversations(client, user_id=user_id, max_pages=max_pages)
            for item in scanned:
                collected[(item.user_id, item.conversation_id)] = item
            notes.append(f"{user_id}: {len(scanned)} conversation(s) scanned")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{user_id}: scan failed ({exc})")
    return sorted(collected.values(), key=lambda x: (x.user_id, x.conversation_id)), notes


def resolve_force_all_user_ids(
    env: dict[str, str],
    *,
    manifest_candidates: list[CandidateConversation],
) -> tuple[list[str], list[str]]:
    users: set[str] = set()
    notes: list[str] = []
    manifest_users = {item.user_id for item in manifest_candidates if item.user_id}
    if manifest_users:
        users.update(manifest_users)
        notes.append(f"user source: manifest ({len(manifest_users)})")
    env_users = _extract_explicit_env_users(env)
    if env_users:
        users.update(env_users)
        notes.append(f"user source: explicit env users ({len(env_users)})")
    return sorted(users), notes


def build_manifest(candidates: list[CandidateConversation]) -> SeedManifest:
    return SeedManifest(
        run_id="residual-cleanup-from-manifests",
        started_at="",
        finished_at="",
        conversations=[
            SeededConversation(
                case_name=item.case_name,
                user_id=item.user_id,
                conversation_id=item.conversation_id,
                message_ids=item.message_ids,
            )
            for item in candidates
        ],
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    env = load_env_config(args.env_file)
    artifacts_dir = resolve_artifacts_dir(args.artifacts_dir, env)
    if not artifacts_dir.exists() and not args.force_all:
        print(f"⚠️ artifacts directory does not exist: {artifacts_dir}")
        return 0

    manifest_files = (
        iter_manifest_files(artifacts_dir, args.glob) if artifacts_dir.exists() else []
    )
    candidates: list[CandidateConversation] = []
    skipped: list[str] = []
    if manifest_files:
        candidates, skipped = collect_candidates(manifest_files)

    live_notes: list[str] = []
    if args.force_all:
        user_ids, user_notes = resolve_force_all_user_ids(
            env,
            manifest_candidates=candidates,
        )
        live_notes.extend(user_notes)
        if not user_ids:
            print("❌ --force-all requires cleanup users from manifest or DIFY_CLEANUP_USERS")
            print(
                "Provide users by keeping manifest files under artifacts, "
                "or set DIFY_CLEANUP_USERS (comma/semicolon/space separated), "
                "for example: DIFY_CLEANUP_USERS=\"user_a,user_b\""
            )
            print("No cleanup executed.")
            return 2

        allowed_users = set(user_ids)
        # In force-all mode, cleanup scope is strictly limited to DIFY_CLEANUP_USERS.
        candidates = [item for item in candidates if item.user_id in allowed_users]
        client_for_scan = create_dify_client(env)
        live_candidates, scan_notes = collect_live_candidates(
            client_for_scan,
            user_ids=user_ids,
            max_pages=max(1, args.max_pages),
        )
        live_notes.extend(scan_notes)
        merged: dict[tuple[str, str], CandidateConversation] = {
            (item.user_id, item.conversation_id): item for item in candidates
        }
        for item in live_candidates:
            merged[(item.user_id, item.conversation_id)] = item
        candidates = sorted(merged.values(), key=lambda x: (x.user_id, x.conversation_id))
        live_notes.append(f"resolved users for live scan: {len(user_ids)}")

    print("=" * 80)
    print("Seed residual cleanup")
    print("=" * 80)
    print(f"Artifacts dir : {artifacts_dir}")
    print(f"Manifest glob : {args.glob}")
    print(f"Manifest files: {len(manifest_files)}")
    print(f"Force-all     : {'enabled' if args.force_all else 'disabled'}")
    print(f"Targets       : {len(candidates)}")
    if skipped:
        print(f"Skipped files : {len(skipped)}")
    print("-" * 80)
    for item in candidates:
        print(f"{item.user_id} / {item.conversation_id}  <- {item.source_file}")

    if skipped:
        print("-" * 80)
        print("Skipped details:")
        for line in skipped:
            print(f"- {line}")
    if live_notes:
        print("-" * 80)
        print("Live-scan details:")
        for line in live_notes:
            print(f"- {line}")

    if not args.execute:
        print("-" * 80)
        print("Dry-run only. Re-run with --execute to delete listed conversations.")
        return 0

    if not candidates:
        print("-" * 80)
        print("Nothing to clean.")
        return 0

    client = create_dify_client(env)
    result = cleanup_seeded_conversations(
        client,
        manifest=build_manifest(candidates),
        verify=not args.no_verify,
    )

    if args.force_all:
        force_users, force_notes = resolve_force_all_user_ids(
            env,
            manifest_candidates=candidates,
        )
        if force_notes:
            print("-" * 80)
            print("Force-all round notes:")
            for line in force_notes:
                print(f"- {line}")

        total_rounds = 1
        total_deleted = int(result.get("deleted") or 0)
        total_verified_absent = int(result.get("verified_absent") or 0)
        total_failures: list[str] = list(result.get("failures") or [])
        max_rounds = max(1, int(args.max_rounds))
        while total_rounds < max_rounds:
            round_candidates, round_notes = collect_live_candidates(
                client,
                user_ids=force_users,
                max_pages=max(1, args.max_pages),
            )
            if round_notes:
                print("-" * 80)
                print(f"Force-all re-scan round {total_rounds + 1}:")
                for line in round_notes:
                    print(f"- {line}")
            if not round_candidates:
                break

            round_result = cleanup_seeded_conversations(
                client,
                manifest=build_manifest(round_candidates),
                verify=not args.no_verify,
            )
            total_rounds += 1
            total_deleted += int(round_result.get("deleted") or 0)
            total_verified_absent += int(round_result.get("verified_absent") or 0)
            total_failures.extend(round_result.get("failures") or [])

            if int(round_result.get("deleted") or 0) == 0 and not (
                round_result.get("failures") or []
            ):
                break

        result = {
            "deleted": total_deleted,
            "verified_absent": total_verified_absent,
            "failures": total_failures,
            "force_all_rounds": total_rounds,
        }
    print("-" * 80)
    print("Cleanup result:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    failures = result.get("failures") or []
    if failures:
        print("❌ cleanup completed with failures")
        return 2
    print("✅ cleanup completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
