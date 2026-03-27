"""Versioned snapshots of supplier clustering state.

Creates timestamped snapshots of the current clustering results and
can diff between any two versions to show what changed.

Snapshots are stored as YAML in config/review/snapshots/ and can
optionally be ingested into the RAG for queryable history.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from rag.config import REVIEW_DIR

SNAPSHOT_DIR = REVIEW_DIR / "snapshots"


def take_snapshot(
    clusters: dict[str, list[str]],
    review_id: Optional[str] = None,
    note: str = "",
    snapshot_dir: Path = SNAPSHOT_DIR,
    edge_scores: Optional[dict] = None,
) -> Path:
    """Save the current clustering state as a versioned snapshot.

    Args:
        clusters: Current clustering result {canonical: [variants]}.
        review_id: Associated review ID (if triggered by a review).
        note: Optional human-readable note.

    Returns:
        Path to the snapshot file.
    """
    snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "snapshot_id": snapshot_id,
        "created": datetime.now().isoformat(),
        "review_id": review_id,
        "note": note,
        "n_clusters": len(clusters),
        "n_names": sum(len(v) for v in clusters.values()),
        "clusters": {canonical: sorted(members) for canonical, members in sorted(clusters.items())},
        "edge_scores": edge_scores or {},
    }

    path = snapshot_dir / f"snapshot_{snapshot_id}.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return path


def list_snapshots(snapshot_dir: Path = SNAPSHOT_DIR) -> list[dict]:
    """List all snapshots with metadata."""
    if not snapshot_dir.exists():
        return []

    snapshots = []
    for path in sorted(snapshot_dir.glob("snapshot_*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        snapshots.append({
            "snapshot_id": data.get("snapshot_id", path.stem),
            "path": path,
            "created": data.get("created", "unknown"),
            "review_id": data.get("review_id"),
            "note": data.get("note", ""),
            "n_clusters": data.get("n_clusters", 0),
            "n_names": data.get("n_names", 0),
        })
    return snapshots


def load_snapshot(snapshot_id: str, snapshot_dir: Path = SNAPSHOT_DIR) -> dict[str, list[str]]:
    """Load a snapshot's clusters by ID."""
    path = snapshot_dir / f"snapshot_{snapshot_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Snapshot '{snapshot_id}' not found at {path}")
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("clusters", {})


def diff_snapshots(
    old_id: str,
    new_id: str,
    snapshot_dir: Path = SNAPSHOT_DIR,
) -> dict:
    """Compute the diff between two snapshots.

    Returns a dict with:
    - added_clusters: clusters in new but not old
    - removed_clusters: clusters in old but not new
    - changed_clusters: clusters where membership changed
    - moved_names: names that switched clusters
    - unchanged_clusters: clusters identical in both
    """
    old_clusters = load_snapshot(old_id, snapshot_dir)
    new_clusters = load_snapshot(new_id, snapshot_dir)

    # Build name -> canonical lookup for both
    old_lookup = {}
    for canonical, members in old_clusters.items():
        for m in members:
            old_lookup[m] = canonical

    new_lookup = {}
    for canonical, members in new_clusters.items():
        for m in members:
            new_lookup[m] = canonical

    all_names = set(old_lookup.keys()) | set(new_lookup.keys())

    # Find moved names
    moved = []
    for name in sorted(all_names):
        old_canon = old_lookup.get(name)
        new_canon = new_lookup.get(name)
        if old_canon != new_canon:
            moved.append({
                "name": name,
                "old_cluster": old_canon,
                "new_cluster": new_canon,
            })

    # Cluster-level diffs
    old_keys = set(old_clusters.keys())
    new_keys = set(new_clusters.keys())

    added = {k: new_clusters[k] for k in sorted(new_keys - old_keys)}
    removed = {k: old_clusters[k] for k in sorted(old_keys - new_keys)}

    changed = {}
    unchanged = {}
    for k in sorted(old_keys & new_keys):
        if set(old_clusters[k]) != set(new_clusters[k]):
            changed[k] = {
                "old": sorted(old_clusters[k]),
                "new": sorted(new_clusters[k]),
                "added_members": sorted(set(new_clusters[k]) - set(old_clusters[k])),
                "removed_members": sorted(set(old_clusters[k]) - set(new_clusters[k])),
            }
        else:
            unchanged[k] = old_clusters[k]

    return {
        "old_id": old_id,
        "new_id": new_id,
        "added_clusters": added,
        "removed_clusters": removed,
        "changed_clusters": changed,
        "unchanged_clusters": unchanged,
        "moved_names": moved,
        "summary": {
            "clusters_added": len(added),
            "clusters_removed": len(removed),
            "clusters_changed": len(changed),
            "clusters_unchanged": len(unchanged),
            "names_moved": len(moved),
        },
    }


def format_diff(diff: dict) -> str:
    """Format a diff as a human-readable string."""
    lines = []
    s = diff["summary"]
    lines.append(f"Diff: {diff['old_id']} -> {diff['new_id']}")
    lines.append(f"  Clusters: +{s['clusters_added']} -{s['clusters_removed']} ~{s['clusters_changed']} ={s['clusters_unchanged']}")
    lines.append(f"  Names moved: {s['names_moved']}")

    if diff["moved_names"]:
        lines.append("\nMoved names:")
        for m in diff["moved_names"]:
            old = m["old_cluster"] or "(new)"
            new = m["new_cluster"] or "(removed)"
            lines.append(f"  {m['name']}: {old} -> {new}")

    if diff["added_clusters"]:
        lines.append("\nNew clusters:")
        for k, members in diff["added_clusters"].items():
            lines.append(f"  + {k}: {members}")

    if diff["removed_clusters"]:
        lines.append("\nRemoved clusters:")
        for k, members in diff["removed_clusters"].items():
            lines.append(f"  - {k}: {members}")

    if diff["changed_clusters"]:
        lines.append("\nChanged clusters:")
        for k, info in diff["changed_clusters"].items():
            lines.append(f"  ~ {k}:")
            if info["added_members"]:
                lines.append(f"      added:   {info['added_members']}")
            if info["removed_members"]:
                lines.append(f"      removed: {info['removed_members']}")

    return "\n".join(lines)
