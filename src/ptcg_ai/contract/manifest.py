"""Artifact manifest generation."""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SEMANTIC_SPEC_VERSION = "1.11.0"
CATALOG_VERSION = "1.0.0"
ACTION_GRAMMAR_VERSION = "1.0.0"
POLICY_CONTRACT_VERSION = "b0_v1"


@dataclass
class ArtifactManifest:
    artifact_id: str
    build_id: str
    source_commit: str
    source_dirty: bool
    semantic_spec_version: str
    catalog_version: str
    action_grammar_version: str
    policy_contract_version: str
    deck_hash: str
    runtime_profile_id: str
    model_checksum: str | None
    file_manifest_sha256: str
    qualification_report_id: str
    build_timestamp: str
    files: dict[str, str] = field(default_factory=dict)


def _git_commit(root: Path) -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _git_dirty(root: Path) -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=root,
            stderr=subprocess.DEVNULL,
        ).decode()
        return bool(out.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_deck(deck: list[int]) -> str:
    payload = ",".join(str(c) for c in deck)
    return hashlib.sha256(payload.encode()).hexdigest()


def build_manifest(
    artifact_dir: Path,
    *,
    repo_root: Path | None = None,
    deck: list[int] | None = None,
    runtime_profile_id: str = "local_b0_v1",
    qualification_report_id: str = "pending",
) -> ArtifactManifest:
    repo_root = repo_root or artifact_dir
    files: dict[str, str] = {}
    for path in sorted(artifact_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(artifact_dir).as_posix()
        if rel.startswith("__pycache__") or "/__pycache__/" in rel:
            continue
        files[rel] = sha256_file(path)
    manifest_blob = json.dumps(files, sort_keys=True, separators=(",", ":"))
    file_manifest_sha = hashlib.sha256(manifest_blob.encode()).hexdigest()
    build_id = hashlib.sha256(
        f"{file_manifest_sha}:{datetime.now(timezone.utc).isoformat()}".encode()
    ).hexdigest()[:16]
    deck_hash = sha256_deck(deck) if deck else "none"
    return ArtifactManifest(
        artifact_id=f"b0-{build_id}",
        build_id=build_id,
        source_commit=_git_commit(repo_root),
        source_dirty=_git_dirty(repo_root),
        semantic_spec_version=SEMANTIC_SPEC_VERSION,
        catalog_version=CATALOG_VERSION,
        action_grammar_version=ACTION_GRAMMAR_VERSION,
        policy_contract_version=POLICY_CONTRACT_VERSION,
        deck_hash=deck_hash,
        runtime_profile_id=runtime_profile_id,
        model_checksum=None,
        file_manifest_sha256=file_manifest_sha,
        qualification_report_id=qualification_report_id,
        build_timestamp=datetime.now(timezone.utc).isoformat(),
        files=files,
    )


def manifest_to_dict(manifest: ArtifactManifest) -> dict[str, Any]:
    return asdict(manifest)
