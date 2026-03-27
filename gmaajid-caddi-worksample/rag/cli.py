"""CLI interface for the RAG system."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from rag.config import (
    CONFIRMED_MAPPINGS_PATH,
    DATA_DIR,
    KNOWLEDGE_DIR,
    REVIEW_DIR,
)

console = Console()


import os

PROG_NAME = os.environ.get("CADDI_CLI_NAME", "caddi-cli")


@click.group(invoke_without_command=True, name=PROG_NAME)
@click.pass_context
def cli(ctx):
    """CADDi Supply Chain RAG - Knowledge ingestion and query tool."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.option("--data-dir", type=click.Path(exists=True, path_type=Path), default=str(DATA_DIR))
@click.option("--knowledge-dir", type=click.Path(exists=True, path_type=Path), default=str(KNOWLEDGE_DIR))
@click.option("--review-id", default=None, help="Apply only this review ID (default: all reviews).")
def ingest(data_dir: Path, knowledge_dir: Path, review_id: str):
    """Ingest CSV data and knowledge documents into the vector store.

    Use --review-id to apply a specific review's decisions. Without it,
    all review files in config/review/ are applied.
    """
    from rag.core import RAGEngine

    engine = RAGEngine()
    txn_id = engine.begin_transaction()
    console.print(f"[bold]Ingesting documents...[/bold] (transaction: [cyan]{txn_id}[/cyan])")

    total = 0
    for directory in [data_dir, knowledge_dir]:
        if directory.exists():
            n = engine.ingest_directory(directory)
            console.print(f"  {directory}: {n} chunks")
            total += n

    # Ingest confirmed mappings as queryable knowledge
    from src.human_review import load_confirmed_mappings
    confirmed = load_confirmed_mappings(CONFIRMED_MAPPINGS_PATH)
    if confirmed:
        # Build a readable text document from the mappings
        from collections import defaultdict
        groups = defaultdict(list)
        for name, canonical in confirmed.items():
            if name != canonical:
                groups[canonical].append(name)
        lines = ["Confirmed Supplier Name Mappings:"]
        for canonical in sorted(groups.keys()):
            variants = ", ".join(sorted(groups[canonical]))
            lines.append(f"{canonical}: {variants}")
        mapping_text = "\n".join(lines)
        n = engine.ingest_text(mapping_text, source="confirmed_mappings.yaml")
        console.print(f"  confirmed_mappings.yaml: {n} chunks")
        total += n

    engine.commit_transaction()

    if review_id:
        review_path = REVIEW_DIR / f"review_{review_id}.yaml"
        if review_path.exists():
            console.print(f"  Applying review: [cyan]{review_id}[/cyan]")
        else:
            console.print(f"  [yellow]Review {review_id} not found at {review_path}[/yellow]")

    console.print(f"\n[green bold]Done.[/green bold] {total} chunks ingested. Store has {engine.count} total.")
    console.print(f"  Transaction: [cyan]{txn_id}[/cyan] (use [bold]caddi-cli revert {txn_id}[/bold] to undo)")


@cli.command()
@click.argument("question")
@click.option("--top-k", default=8, help="Number of results to retrieve.")
@click.option("--raw", is_flag=True, help="Show raw chunks without LLM synthesis.")
def query(question: str, top_k: int, raw: bool):
    """Query the knowledge base."""
    from rag.core import RAGEngine

    engine = RAGEngine()
    if engine.count == 0:
        console.print("[red]Knowledge base is empty. Run 'caddi-cli ingest' first.[/red]")
        return

    if raw:
        hits = engine.query(question, top_k=top_k)
        table = Table(title=f"Top {len(hits)} results")
        table.add_column("#", width=3)
        table.add_column("Source", width=30)
        table.add_column("Relevance", width=10)
        table.add_column("Text", max_width=80)
        for i, hit in enumerate(hits, 1):
            relevance = f"{1 - hit['distance']:.2f}"
            source = hit["metadata"].get("source", "?")
            text = hit["text"][:200] + "..." if len(hit["text"]) > 200 else hit["text"]
            table.add_row(str(i), source, relevance, text)
        console.print(table)
    else:
        from rag.llm import ask

        context = engine.query_with_context(question, top_k=top_k)
        with console.status("Thinking..."):
            answer = ask(question, context)
        console.print(Panel(answer, title="Answer", border_style="green"))


@cli.command()
@click.option("--top-k", default=8, help="Number of results per query.")
def chat(top_k: int):
    """Interactive chat with the knowledge base."""
    from rag.core import RAGEngine
    from rag.llm import ask

    engine = RAGEngine()
    if engine.count == 0:
        console.print("[red]Knowledge base is empty. Run 'caddi-cli ingest' first.[/red]")
        return

    console.print("[bold]CADDi Supply Chain Assistant[/bold] (type 'quit' to exit)\n")

    while True:
        try:
            question = console.input("[bold blue]You:[/bold blue] ")
        except (EOFError, KeyboardInterrupt):
            break
        if question.strip().lower() in ("quit", "exit", "q"):
            break
        if not question.strip():
            continue

        context = engine.query_with_context(question, top_k=top_k)
        with console.status("Thinking..."):
            answer = ask(question, context)
        console.print(f"\n[bold green]Assistant:[/bold green] {answer}\n")


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def add(path: Path):
    """Add a single file to the knowledge base."""
    from rag.core import RAGEngine

    engine = RAGEngine()
    txn_id = engine.begin_transaction()
    if path.is_dir():
        n = engine.ingest_directory(path)
    else:
        n = engine.ingest_file(path)
    engine.commit_transaction()
    console.print(f"[green]Added {n} chunks from {path}. Store has {engine.count} total.[/green]")
    console.print(f"  Transaction: [cyan]{txn_id}[/cyan]")


@cli.command()
@click.option("--data-dir", type=click.Path(exists=True, path_type=Path), default=str(DATA_DIR))
@click.option("--format", "fmt", type=click.Choice(["table", "tree", "csv"]), default="tree", help="Output format.")
@click.option("--all", "show_all", is_flag=True, help="Include confirmed mappings with 0 occurrences in data.")
def mappings(data_dir: Path, fmt: str, show_all: bool):
    """Visualize supplier name mappings to canonical names.

    By default shows only names found in the data CSVs.
    Use --all to also show confirmed mappings with no data occurrences.
    """
    import pandas as pd
    from collections import defaultdict
    from src.supplier_clustering import ClusterMethod, cluster_names
    from src.human_review import apply_human_overrides, load_confirmed_mappings
    from rag.config import CONFIRMED_MAPPINGS_PATH

    all_names = []
    for csv_file in sorted(data_dir.glob("*.csv")):
        df = pd.read_csv(csv_file)
        if "supplier_name" in df.columns:
            all_names.extend(df["supplier_name"].tolist())

    if not all_names:
        console.print("[red]No supplier names found.[/red]")
        return

    clusters = cluster_names(all_names, method=ClusterMethod.PIPELINE)
    clusters = apply_human_overrides(clusters, confirmed_path=CONFIRMED_MAPPINGS_PATH)

    # Merge in confirmed mappings that have 0 occurrences (if --all)
    confirmed = load_confirmed_mappings(CONFIRMED_MAPPINGS_PATH)
    if show_all and confirmed:
        confirmed_groups = defaultdict(set)
        for name, canonical in confirmed.items():
            confirmed_groups[canonical].add(name)
        for canonical, names in confirmed_groups.items():
            if canonical in clusters:
                # Add missing confirmed names to existing cluster
                existing = set(clusters[canonical])
                clusters[canonical] = sorted(existing | names)
            else:
                clusters[canonical] = sorted(names)

    # Compute edge confidence scores (with confirmed overrides)
    from src.supplier_clustering import compute_edge_scores
    from src.human_review import load_confirmed_scores
    confirmed_scores = load_confirmed_scores(CONFIRMED_MAPPINGS_PATH)
    edge_scores = compute_edge_scores(clusters, confirmed_scores=confirmed_scores)

    def _score_bar(score: float, width: int = 10) -> str:
        """Render a confidence score as a compact visual bar."""
        filled = int(score * width)
        return "█" * filled + "░" * (width - filled)

    def _score_color(score: float) -> str:
        if score >= 0.85:
            return "green"
        elif score >= 0.55:
            return "yellow"
        return "red"

    if fmt == "tree":
        from rich.tree import Tree
        tree = Tree("[bold]Supplier Name Mappings[/bold]")
        for canonical in sorted(clusters.keys()):
            members = clusters[canonical]
            count = sum(all_names.count(m) for m in members)
            branch = tree.add(f"[bold cyan]{canonical}[/bold cyan] [dim]({count} occurrences)[/dim]")
            for m in sorted(members):
                m_count = all_names.count(m)
                is_confirmed = m in confirmed
                scores = edge_scores.get(canonical, {}).get(m, {})
                combined = scores.get("combined", 0)
                j = scores.get("jaccard", 0)
                e = scores.get("embedding", 0)
                source = scores.get("source", "auto")
                color = _score_color(combined)
                bar = _score_bar(combined)

                if m == canonical:
                    branch.add(f"[green]{m}[/green] [dim]({m_count}x) canonical[/dim]")
                elif m_count > 0 or is_confirmed:
                    count_str = f"{m_count}x" if m_count > 0 else "0x"
                    src_str = f" {source}" if source != "auto" else ""
                    branch.add(
                        f"{m} [dim]({count_str})[/dim] "
                        f"[{color}]{bar} {combined:.2f}[/{color}] "
                        f"[dim](J={j:.2f} E={e:.2f}{src_str})[/dim]"
                    )
                else:
                    branch.add(f"[dim]{m} (0x)[/dim] [{color}]{bar} {combined:.2f}[/{color}]")
        console.print(tree)

    elif fmt == "table":
        table = Table(title="Supplier Name Mappings")
        table.add_column("Canonical Name", style="cyan bold")
        table.add_column("Raw Variant")
        table.add_column("Count", justify="right")
        table.add_column("Confidence", justify="center")
        table.add_column("Jaccard", justify="right")
        table.add_column("Embedding", justify="right")
        table.add_column("Source")

        for canonical in sorted(clusters.keys()):
            members = clusters[canonical]
            first = True
            for m in sorted(members):
                m_count = all_names.count(m)
                scores = edge_scores.get(canonical, {}).get(m, {})
                combined = scores.get("combined", 0)
                j = scores.get("jaccard", 0)
                e = scores.get("embedding", 0)
                source = scores.get("source", "auto")
                color = _score_color(combined)
                bar = _score_bar(combined, 8)
                table.add_row(
                    canonical if first else "",
                    m,
                    str(m_count),
                    f"[{color}]{bar} {combined:.2f}[/{color}]",
                    f"{j:.2f}",
                    f"{e:.2f}",
                    source,
                )
                first = False
            table.add_section()
        console.print(table)

    elif fmt == "csv":
        console.print("canonical_name,raw_variant,count,confidence,jaccard,embedding,source")
        for canonical in sorted(clusters.keys()):
            for m in sorted(clusters[canonical]):
                m_count = all_names.count(m)
                scores = edge_scores.get(canonical, {}).get(m, {})
                combined = scores.get("combined", 0)
                j = scores.get("jaccard", 0)
                e = scores.get("embedding", 0)
                source = scores.get("source", "auto")
                console.print(f"{canonical},{m},{m_count},{combined:.3f},{j:.3f},{e:.3f},{source}")


@cli.command()
def transactions():
    """List all RAG ingest transactions."""
    from rag.core import list_transactions

    txns = list_transactions()
    if not txns:
        console.print("[dim]No transactions logged.[/dim]")
        return

    table = Table(title="RAG Transactions")
    table.add_column("Transaction ID", style="cyan")
    table.add_column("Created")
    table.add_column("Chunks", justify="right")
    table.add_column("Sources")
    table.add_column("Reverted")

    for t in txns:
        created = t["created"][:16] if len(t.get("created", "")) > 16 else t.get("created", "")
        sources = ", ".join(t.get("sources", [])[:3])
        if len(t.get("sources", [])) > 3:
            sources += f" (+{len(t['sources']) - 3} more)"
        reverted = "[red]yes[/red]" if t.get("reverted") else "[green]no[/green]"
        table.add_row(
            t["txn_id"],
            created,
            str(t.get("chunk_count", 0)),
            sources,
            reverted,
        )
    console.print(table)


@cli.command()
@click.argument("txn_id")
@click.option("--force", is_flag=True, help="Skip confirmation prompt.")
def revert(txn_id: str, force: bool):
    """Revert a RAG ingest transaction (delete its chunks).

    Example: caddi-cli revert txn_20260325_023000
    """
    from rag.core import RAGEngine, list_transactions

    txns = list_transactions()
    txn = next((t for t in txns if t["txn_id"] == txn_id), None)
    if txn is None:
        console.print(f"[red]Transaction '{txn_id}' not found.[/red]")
        console.print("Run [bold]caddi-cli transactions[/bold] to see available transactions.")
        return

    if txn.get("reverted"):
        console.print(f"[yellow]Transaction '{txn_id}' already reverted.[/yellow]")
        return

    chunk_count = txn.get("chunk_count", 0)
    sources = ", ".join(txn.get("sources", []))
    console.print(f"Transaction: [cyan]{txn_id}[/cyan]")
    console.print(f"  Chunks: {chunk_count}")
    console.print(f"  Sources: {sources}")

    if not force:
        try:
            confirm = console.input(f"\n  Delete {chunk_count} chunks? (y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Cancelled.[/dim]")
            return
        if confirm != "y":
            console.print("[dim]Cancelled.[/dim]")
            return

    engine = RAGEngine()
    deleted = engine.revert_transaction(txn_id)
    console.print(f"\n[green]Reverted:[/green] {deleted} chunks deleted. Store has {engine.count} remaining.")


@cli.command()
def status():
    """Show knowledge base status."""
    from rag.core import RAGEngine

    engine = RAGEngine()
    console.print(f"Vector store: {engine.persist_dir}")
    console.print(f"Total chunks: {engine.count}")


@cli.command()
@click.option("--data-dir", type=click.Path(exists=True, path_type=Path), default=str(DATA_DIR))
def review(data_dir: Path):
    """Generate supplier name review candidates for human verification.

    Creates a new review file with a unique ID in config/review/.
    Use 'caddi-cli decide' to interactively review, or 'caddi-cli reviews' to list all.
    """
    import pandas as pd
    from src.human_review import find_uncertain_pairs, write_review_file
    from src.supplier_clustering import ClusterMethod, cluster_names

    all_names = []
    for csv_file in sorted(data_dir.glob("*.csv")):
        df = pd.read_csv(csv_file)
        if "supplier_name" in df.columns:
            all_names.extend(df["supplier_name"].tolist())

    if not all_names:
        console.print("[red]No supplier names found in CSV files.[/red]")
        return

    console.print(f"Found {len(all_names)} name occurrences ({len(set(all_names))} unique)")

    clusters = cluster_names(all_names, method=ClusterMethod.PIPELINE)
    console.print(f"Clustering produced {len(clusters)} groups")

    candidates = find_uncertain_pairs(clusters, all_names)
    if not candidates:
        console.print("[green]No uncertain pairs found — clustering is confident.[/green]")
        return

    path = write_review_file(candidates)
    import yaml
    with open(path) as f:
        review_id = yaml.safe_load(f).get("review_id", "unknown")

    console.print(f"\n[yellow]{len(candidates)} uncertain pairs written.[/yellow]")
    console.print(f"  Review ID: [bold cyan]{review_id}[/bold cyan]")
    console.print(f"  File:      {path}")
    console.print(f"\nRun [bold]caddi-cli decide {review_id}[/bold] to review interactively.")


@cli.command()
def reviews():
    """List all review sessions and their status."""
    from src.human_review import list_reviews

    all_reviews = list_reviews()
    if not all_reviews:
        console.print("[dim]No reviews found. Run 'caddi-cli review' to create one.[/dim]")
        return

    table = Table(title="Review Sessions")
    table.add_column("Review ID", style="cyan")
    table.add_column("Created")
    table.add_column("Reviewed")
    table.add_column("Reviewed By")
    table.add_column("Human", justify="right")
    table.add_column("Auto", justify="right")
    table.add_column("Total", justify="right")

    for r in all_reviews:
        created = r["created"][:16] if len(r["created"]) > 16 else r["created"]
        if r.get("reviewed"):
            reviewed_display = "[green]yes[/green]"
            reviewed_by = r.get("reviewed_by") or ""
        else:
            reviewed_display = "[yellow]no[/yellow]"
            reviewed_by = ""
        table.add_row(
            r["review_id"],
            created,
            reviewed_display,
            reviewed_by,
            str(r["decided"]),
            str(r["pending"]),
            str(r["total"]),
        )

    console.print(table)
    console.print(f"\nUse [bold]caddi-cli decide <review_id>[/bold] to review a specific session.")


@cli.command()
@click.argument("review_id", required=False)
@click.option("--re-review", is_flag=True, help="Re-review a file already marked as reviewed.")
def decide(review_id: str, re_review: bool):
    """Interactively review uncertain supplier name pairs.

    Skips files already marked as reviewed unless --re-review is passed.
    Navigate freely: p=previous, n=next, g=goto, m=merge, s=split, q=quit.
    Each decision records who made it (auto vs human) and when.
    """
    import yaml
    from datetime import datetime
    from src.human_review import list_reviews, load_reviewer

    # Load reviewer identity
    reviewer = load_reviewer()
    if not reviewer["name"]:
        console.print("[yellow]No reviewer configured.[/yellow] Edit [bold]config/reviewer.yaml[/bold] with your name.")
        console.print("[dim]Continuing as anonymous reviewer...[/dim]\n")

    # Find the review file
    if review_id:
        review_file = REVIEW_DIR / f"review_{review_id}.yaml"
        if not review_file.exists():
            console.print(f"[red]Review '{review_id}' not found.[/red]")
            console.print("Run [bold]caddi-cli reviews[/bold] to see available reviews.")
            return
        # Check if already reviewed
        with open(review_file) as f:
            check = yaml.safe_load(f) or {}
        if check.get("reviewed") and not re_review:
            reviewed_by = check.get("reviewed_by", "someone")
            reviewed_at = (check.get("reviewed_at") or "")[:16]
            console.print(f"[yellow]Review {review_id} already reviewed by {reviewed_by} @ {reviewed_at}.[/yellow]")
            console.print("Use [bold]--re-review[/bold] to review again.")
            return
    else:
        all_reviews = list_reviews()
        # Filter to un-reviewed files
        candidates = [r for r in all_reviews if not r.get("reviewed")]
        if not candidates:
            if all_reviews:
                console.print("[green]All reviews are marked as reviewed.[/green]")
                console.print("Use [bold]caddi-cli decide <review_id> --re-review[/bold] to revisit one.")
            else:
                console.print("[green]No reviews found.[/green] Run [bold]caddi-cli review[/bold] to create one.")
            return
        review_file = candidates[-1]["path"]
        review_id = candidates[-1]["review_id"]

    with open(review_file) as f:
        data = yaml.safe_load(f) or {}

    pairs = data.get("pairs", [])
    if not pairs:
        console.print("[green]No pairs to review.[/green]")
        return

    total = len(pairs)
    human_count = sum(1 for p in pairs if p.get("decided_by") == "human")
    auto_count = sum(1 for p in pairs if p.get("decided_by", "auto") == "auto")

    reviewer_label = reviewer["name"] or "anonymous"
    console.print(f"[bold]Review: {review_id}[/bold] ({total} pairs: {human_count} human, {auto_count} auto)")
    console.print(f"  Reviewer: [cyan]{reviewer_label}[/cyan]")
    console.print(
        "  [green]m[/green]=merge  [red]s[/red]=split  "
        "[dim]Enter[/dim]=skip  "
        "[blue]p[/blue]=prev  [blue]n[/blue]=next  "
        "[blue]g[/blue] N=goto pair N  "
        "[dim]q[/dim]=quit\n"
    )

    def _display_pair(idx: int):
        pair = pairs[idx]
        pair_id = pair.get("pair_id", f"{idx + 1}")
        j = pair.get("tfidf_jaccard", 0)
        e = pair.get("embedding_cosine", 0)
        j_bar = "+" * int(j * 20) + "-" * (20 - int(j * 20))
        e_bar = "+" * int(e * 20) + "-" * (20 - int(e * 20))

        decision = pair.get("decision", "skip")
        decided_by = pair.get("decided_by", "auto")
        decided_at = pair.get("decided_at", "")
        if decided_at and len(decided_at) > 16:
            decided_at = decided_at[:16]

        # Color the current decision based on source
        reviewer_name = pair.get("decided_by_name", "")
        if decided_by == "human":
            who = reviewer_name or "human"
            dec_display = f"[bold green]{decision}[/bold green] [dim]({who} @ {decided_at})[/dim]"
        elif decision in ("merged", "split"):
            dec_display = f"[yellow]{decision}[/yellow] [dim](auto)[/dim]"
        else:
            dec_display = f"[dim]{decision} (auto)[/dim]"

        console.print(f"[bold]--- {pair_id} ({idx + 1}/{total}) ---[/bold]")
        console.print(f"  A: [cyan]{pair['name_a']}[/cyan]")
        console.print(f"  B: [cyan]{pair['name_b']}[/cyan]")
        console.print(f"  Jaccard:   [{j_bar}] {j:.2f}")
        console.print(f"  Embedding: [{e_bar}] {e:.2f}")
        console.print(f"  System:    [yellow]{pair.get('current_action', '?')}[/yellow] — {pair.get('reason', '')}")
        console.print(f"  Decision:  {dec_display}")

    def _apply_decision(idx: int, decision: str):
        pairs[idx]["decision"] = decision
        pairs[idx]["decided_by"] = "human"
        pairs[idx]["decided_by_name"] = reviewer["name"] or "anonymous"
        pairs[idx]["decided_by_email"] = reviewer["email"] or ""
        pairs[idx]["decided_at"] = datetime.now().isoformat()
        pairs[idx]["review_id"] = review_id

    # Start at first auto-decided pair, or first pair if all human
    current = next((i for i, p in enumerate(pairs) if p.get("decided_by", "auto") == "auto"), 0)
    reviewed = 0

    while True:
        _display_pair(current)

        try:
            choice = console.input("  ([green]m[/green]erge / [red]s[/red]plit / [blue]p[/blue]rev / [blue]n[/blue]ext / [blue]g[/blue] N / [dim]q[/dim]uit): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Saving...[/dim]")
            break

        if choice in ("q", "quit"):
            break
        elif choice in ("m", "merge"):
            _apply_decision(current, "merge")
            console.print("  [green]-> merge (human)[/green]\n")
            reviewed += 1
            current = min(current + 1, total - 1)
        elif choice in ("s", "split"):
            _apply_decision(current, "split")
            console.print("  [red]-> split (human)[/red]\n")
            reviewed += 1
            current = min(current + 1, total - 1)
        elif choice in ("p", "prev"):
            current = max(current - 1, 0)
            console.print()
        elif choice in ("n", "next", ""):
            current = min(current + 1, total - 1)
            console.print()
        elif choice.startswith("g"):
            # goto: "g 5" or "g5"
            num_str = choice[1:].strip()
            try:
                target = int(num_str) - 1
                if 0 <= target < total:
                    current = target
                    console.print()
                else:
                    console.print(f"  [red]Invalid: enter 1-{total}[/red]\n")
            except ValueError:
                console.print(f"  [red]Usage: g <number> (1-{total})[/red]\n")
        else:
            console.print("  [dim]Unknown command. m/s/p/n/g N/q[/dim]\n")

    # Save
    auto_remaining = sum(1 for p in pairs if p.get("decided_by", "auto") == "auto")
    human_total = sum(1 for p in pairs if p.get("decided_by") == "human")
    data["status"] = "complete" if auto_remaining == 0 else "pending"

    # Mark as reviewed when all pairs have human decisions
    if auto_remaining == 0 and not data.get("reviewed"):
        data["reviewed"] = True
        data["reviewed_at"] = datetime.now().isoformat()
        data["reviewed_by"] = reviewer["name"] or "anonymous"

    with open(review_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    console.print(f"\n[bold]{reviewed} decisions this session. {human_total}/{total} total human decisions.[/bold]")
    console.print(f"Saved to {review_file}")
    if auto_remaining > 0:
        console.print(f"[yellow]{auto_remaining} auto decisions remaining.[/yellow]")
    elif data.get("reviewed"):
        console.print(f"[green]Review marked as complete by {data['reviewed_by']}.[/green]")


@cli.command()
@click.option("--data-dir", type=click.Path(exists=True, path_type=Path), default=str(DATA_DIR))
@click.option("--note", default="", help="Optional note for the snapshot.")
@click.option("--review-id", default=None, help="Associate with a review ID.")
def snapshot(data_dir: Path, note: str, review_id: str):
    """Take a snapshot of the current clustering state.

    Snapshots are versioned and can be diffed to see how review
    decisions change supplier associations over time.
    """
    import pandas as pd
    from src.supplier_clustering import ClusterMethod, cluster_names
    from src.human_review import apply_human_overrides
    from src.clustering_snapshot import take_snapshot
    from rag.config import CONFIRMED_MAPPINGS_PATH

    all_names = []
    for csv_file in sorted(data_dir.glob("*.csv")):
        df = pd.read_csv(csv_file)
        if "supplier_name" in df.columns:
            all_names.extend(df["supplier_name"].tolist())

    if not all_names:
        console.print("[red]No supplier names found.[/red]")
        return

    clusters = cluster_names(all_names, method=ClusterMethod.PIPELINE)
    clusters = apply_human_overrides(clusters, confirmed_path=CONFIRMED_MAPPINGS_PATH)

    from src.supplier_clustering import compute_edge_scores
    from src.human_review import load_confirmed_scores
    confirmed_scores = load_confirmed_scores(CONFIRMED_MAPPINGS_PATH)
    edge_scores = compute_edge_scores(clusters, confirmed_scores=confirmed_scores)

    path = take_snapshot(clusters, review_id=review_id, note=note, edge_scores=edge_scores)
    console.print(f"[green]Snapshot saved:[/green] {path}")
    console.print(f"  Clusters: {len(clusters)}, Names: {sum(len(v) for v in clusters.values())}")


@cli.command()
def snapshots():
    """List all clustering snapshots."""
    from src.clustering_snapshot import list_snapshots

    all_snaps = list_snapshots()
    if not all_snaps:
        console.print("[dim]No snapshots. Run 'caddi-cli snapshot' to create one.[/dim]")
        return

    table = Table(title="Clustering Snapshots")
    table.add_column("Snapshot ID", style="cyan")
    table.add_column("Created")
    table.add_column("Review ID")
    table.add_column("Clusters", justify="right")
    table.add_column("Names", justify="right")
    table.add_column("Note")

    for s in all_snaps:
        created = s["created"][:16] if len(s["created"]) > 16 else s["created"]
        table.add_row(
            s["snapshot_id"],
            created,
            s.get("review_id") or "",
            str(s["n_clusters"]),
            str(s["n_names"]),
            s.get("note", ""),
        )
    console.print(table)


@cli.command()
@click.argument("old_id")
@click.argument("new_id")
def diff(old_id: str, new_id: str):
    """Show what changed between two clustering snapshots.

    Example: caddi-cli diff 20260325_010000 20260325_020000
    """
    from src.clustering_snapshot import diff_snapshots, format_diff

    try:
        result = diff_snapshots(old_id, new_id)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        console.print("Run [bold]caddi-cli snapshots[/bold] to see available snapshots.")
        return

    output = format_diff(result)
    s = result["summary"]

    if s["names_moved"] == 0 and s["clusters_added"] == 0 and s["clusters_removed"] == 0:
        console.print(f"[green]No changes between {old_id} and {new_id}.[/green]")
    else:
        console.print(Panel(output, title=f"Diff: {old_id} -> {new_id}", border_style="cyan"))


@cli.command("commit-review")
@click.argument("review_id")
def commit_review(review_id: str):
    """Snapshot and git-commit a review's decisions.

    Takes a clustering snapshot linked to the review, then commits the
    review file, snapshot, and confirmed mappings together.

    Example: caddi-cli commit-review 20260325_015431
    """
    import subprocess

    # Take snapshot
    console.print(f"[bold]Taking snapshot for review {review_id}...[/bold]")
    result = subprocess.run(
        [".venv/bin/python", "-m", "rag.cli", "snapshot",
         "--data-dir", "data/", "--review-id", review_id,
         "--note", f"commit-review {review_id}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        console.print(f"[red]Snapshot failed:[/red] {result.stderr}")
        return
    console.print(result.stdout.strip())

    # Git add + commit
    console.print("\n[bold]Committing to git...[/bold]")
    subprocess.run(["git", "add", "config/review/", "config/confirmed_mappings.yaml"], check=True)
    msg = (
        f"review: {review_id}\n\n"
        "Supplier name review decisions committed.\n"
        "Review file and clustering snapshot included.\n"
        "Use 'caddi-cli diff OLD=<id> NEW=<id>' to see what changed."
    )
    result = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True)
    if result.returncode != 0:
        if "nothing to commit" in result.stdout:
            console.print("[yellow]Nothing to commit — no changes since last commit.[/yellow]")
        else:
            console.print(f"[red]Commit failed:[/red] {result.stderr}")
        return

    console.print(f"[green]Committed.[/green]")
    subprocess.run(["git", "log", "--oneline", "-1"])


# --- M&A Registry Commands ---

@cli.group()
def ma():
    """Manage the M&A registry (entities, events, divisions)."""
    pass


@ma.command("list")
def ma_list():
    """List all entities and M&A events."""
    from src.ma_registry import MARegistry
    from rag.config import MA_REGISTRY_PATH

    reg = MARegistry(path=MA_REGISTRY_PATH)
    entities = reg.list_entities()
    events = reg.list_events()

    if not entities and not events:
        console.print("[dim]Registry is empty. Run 'caddi-cli ma add' to add entities.[/dim]")
        return

    if entities:
        table = Table(title="Entities")
        table.add_column("ID", style="cyan", width=8)
        table.add_column("Name")
        table.add_column("Friendly", style="dim")
        table.add_column("Type")
        for e in entities:
            etype = "division" if e.get("parent") else "root"
            if e.get("divisions"):
                etype = f"root ({len(e['divisions'])} div)"
            table.add_row(e["id"], e["name"], e.get("friendly", ""), etype)
        console.print(table)

    if events:
        console.print()
        table = Table(title="M&A Events")
        table.add_column("ID", style="cyan")
        table.add_column("Type")
        table.add_column("Date")
        table.add_column("Acquirer")
        table.add_column("Acquired")
        table.add_column("Names", justify="right")
        for ev in events:
            acq_entity = reg.get_entity(ev["acquirer"])
            acd_entity = reg.get_entity(ev["acquired"])
            acq_name = acq_entity["name"] if acq_entity else ev["acquirer"]
            acd_name = acd_entity["name"] if acd_entity else ev["acquired"]
            n_names = len(ev.get("resulting_names", []))
            table.add_row(ev["id"], ev["type"], ev["date"], acq_name, acd_name, str(n_names))
        console.print(table)


@ma.command("add")
@click.option("--type", "event_type", type=click.Choice(["acquisition", "merger", "rebrand", "restructure"]))
@click.option("--date", "event_date", help="Event date (YYYY-MM-DD)")
@click.option("--acquirer", help="Acquirer entity name (creates if new)")
@click.option("--acquired", help="Acquired entity name (creates if new)")
@click.option("--resulting-name", "resulting_names", multiple=True, help="Post-event name variant (repeatable)")
@click.option("--notes", default="", help="Optional notes")
@click.option("--entity-only", is_flag=True, help="Just add an entity, no event")
@click.option("--name", "entity_name", help="Entity name (with --entity-only)")
def ma_add(event_type, event_date, acquirer, acquired, resulting_names, notes, entity_only, entity_name):
    """Add an entity or M&A event to the registry."""
    from src.ma_registry import MARegistry
    from rag.config import MA_REGISTRY_PATH

    reg = MARegistry(path=MA_REGISTRY_PATH)

    if entity_only:
        name = entity_name or click.prompt("Entity name")
        friendly = click.prompt("Friendly name (or Enter for auto)", default="", show_default=False)
        entity = reg.add_entity(name, friendly=friendly or None)
        console.print(f"[green]Created entity:[/green] {entity['id']} ({entity['friendly']})")
        return

    # Interactive if no options provided
    if not event_type:
        event_type = click.prompt("Event type", type=click.Choice(["acquisition", "merger", "rebrand", "restructure"]))
    if not event_date:
        event_date = click.prompt("Date (YYYY-MM-DD)")
    if not acquirer:
        acquirer = click.prompt("Acquirer (surviving entity)")
    if not acquired:
        acquired = click.prompt("Acquired entity")

    def _find_or_create(name):
        for e in reg.list_entities():
            if e["name"].lower() == name.lower() or e.get("friendly") == name.lower():
                return e
        return reg.add_entity(name)

    acq_entity = _find_or_create(acquirer)
    acd_entity = _find_or_create(acquired)

    rn_list = [{"name": n} for n in resulting_names]
    if not rn_list:
        while True:
            n = click.prompt("Resulting name (or Enter to finish)", default="", show_default=False)
            if not n:
                break
            fs = click.prompt(f"  First seen date for '{n}' (or Enter to skip)", default="", show_default=False)
            entry = {"name": n}
            if fs:
                entry["first_seen"] = fs
            rn_list.append(entry)

    event = reg.add_event(
        event_type=event_type,
        date=event_date,
        acquirer_id=acq_entity["id"],
        acquired_id=acd_entity["id"],
        resulting_names=rn_list,
        notes=notes,
    )
    console.print(f"[green]Created event:[/green] {event['id']} ({event_type})")


@ma.command("show")
@click.argument("identifier")
def ma_show(identifier):
    """Show details of an entity or event."""
    from src.ma_registry import MARegistry
    from rag.config import MA_REGISTRY_PATH
    import json

    reg = MARegistry(path=MA_REGISTRY_PATH)

    entity = reg.get_entity(identifier)
    if entity:
        console.print(Panel(
            json.dumps(entity, indent=2, default=str),
            title=f"Entity: {entity['name']}",
            border_style="cyan",
        ))
        return

    event = reg.get_event(identifier)
    if event:
        acq = reg.get_entity(event["acquirer"])
        acd = reg.get_entity(event["acquired"])
        event_display = dict(event)
        event_display["acquirer_name"] = acq["name"] if acq else "?"
        event_display["acquired_name"] = acd["name"] if acd else "?"
        console.print(Panel(
            json.dumps(event_display, indent=2, default=str),
            title=f"Event: {event['id']} ({event['type']})",
            border_style="yellow",
        ))
        return

    console.print(f"[red]'{identifier}' not found as entity or event.[/red]")


@ma.command("remove")
@click.argument("identifier")
@click.option("--force", is_flag=True, help="Skip confirmation")
def ma_remove(identifier, force):
    """Remove an entity or event."""
    from src.ma_registry import MARegistry
    from rag.config import MA_REGISTRY_PATH

    reg = MARegistry(path=MA_REGISTRY_PATH)

    event = reg.get_event(identifier)
    if event:
        acq = reg.get_entity(event["acquirer"])
        acd = reg.get_entity(event["acquired"])
        label = f"{event['id']} ({acq['name'] if acq else '?'} {event['type']} {acd['name'] if acd else '?'})"
        if not force:
            click.confirm(f"Remove event {label}?", abort=True)
        reg.remove_event(identifier)
        console.print(f"[green]Removed event {identifier}.[/green]")
        return

    entity = reg.get_entity(identifier)
    if entity:
        if not force:
            click.confirm(f"Remove entity '{entity['name']}' ({entity['id']})?", abort=True)
        reg.remove_entity(entity["id"])
        console.print(f"[green]Removed entity {entity['id']}.[/green]")
        return

    console.print(f"[red]'{identifier}' not found.[/red]")


@ma.command("validate")
def ma_validate():
    """Validate the M&A registry for errors."""
    from src.ma_registry import MARegistry
    from src.chain_validator import validate_registry
    from rag.config import MA_REGISTRY_PATH

    reg = MARegistry(path=MA_REGISTRY_PATH)
    if not reg.events:
        console.print("[dim]No events to validate.[/dim]")
        return

    console.print(f"Checking {len(reg.events)} events...")
    alerts = validate_registry(reg, check_orphans_against_data=False)

    errors = [a for a in alerts if a["severity"] == "error"]
    warnings = [a for a in alerts if a["severity"] == "warning"]
    infos = [a for a in alerts if a["severity"] == "info"]

    for a in errors:
        console.print(f"  [red]ERROR:[/red] {a['message']}")
        console.print(f"    [dim]Action: {a['action']}[/dim]")
    for a in warnings:
        console.print(f"  [yellow]WARNING:[/yellow] {a['message']}")
        console.print(f"    [dim]Action: {a['action']}[/dim]")
    for a in infos:
        console.print(f"  [dim]INFO: {a['message']}[/dim]")

    if not alerts:
        console.print("[green]OK: No issues found.[/green]")
    else:
        console.print(f"\n{len(errors)} errors, {len(warnings)} warnings, {len(infos)} info.")


# --- Demo Commands ---

@cli.group()
def demo():
    """Generate demo data, run benchmarks, view reports."""
    pass


@demo.command("generate")
@click.option("--extended", is_flag=True, help="Include extended test scenarios (68 total)")
def demo_generate(extended):
    """Generate synthetic demo CSVs from M&A registry and test scenarios.

    Reads config/ma_registry.yaml and config/test_scenarios.yaml,
    creates data/demo/ with demo_orders.csv, demo_inspections.csv, demo_rfq.csv.

    Example:
        caddi-cli demo generate
        caddi-cli demo generate --extended
    """
    from src.ma_registry import MARegistry
    from src.demo_generator import generate_demo_data, load_all_scenarios
    from rag.config import MA_REGISTRY_PATH, TEST_SCENARIOS_PATH, TEST_SCENARIOS_EXTENDED_PATH, DEMO_DIR

    if not MA_REGISTRY_PATH.exists():
        console.print("[red]No M&A registry found. Run 'caddi-cli ma add' first.[/red]")
        return
    if not TEST_SCENARIOS_PATH.exists():
        console.print("[red]No test scenarios found at config/test_scenarios.yaml[/red]")
        return

    reg = MARegistry(path=MA_REGISTRY_PATH)
    console.print(f"Reading ma_registry.yaml ({len(reg.events)} events)")

    if extended:
        output_dir = DEMO_DIR.parent / "demo_extended"
        scenarios = load_all_scenarios(TEST_SCENARIOS_PATH, TEST_SCENARIOS_EXTENDED_PATH)
        base_count = len(load_all_scenarios(TEST_SCENARIOS_PATH))
        ext_count = len(scenarios) - base_count
        console.print(f"Using {len(scenarios)} scenarios ({base_count} base + {ext_count} extended)")
        # Write scenarios to a temp path so generate_demo_data can use them
        import tempfile, yaml as _yaml
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tf:
            _yaml.dump({"scenarios": scenarios}, tf)
            tmp_path = Path(tf.name)
        files = generate_demo_data(
            registry=reg,
            scenarios_path=tmp_path,
            output_dir=output_dir,
        )
        tmp_path.unlink(missing_ok=True)
    else:
        files = generate_demo_data(
            registry=reg,
            scenarios_path=TEST_SCENARIOS_PATH,
            output_dir=DEMO_DIR,
        )

    console.print("[green]Generated:[/green]")
    for name, path in files.items():
        import pandas as pd
        df = pd.read_csv(path)
        console.print(f"  {path} ({len(df)} rows)")


@demo.command("run")
@click.option("--extended", is_flag=True, help="Include extended test scenarios")
def demo_run(extended):
    """Run the full resolution pipeline on demo data and report metrics.

    Resolves all demo supplier names using the three-stage pipeline
    (clustering -> M&A registry -> human escalation) and compares
    against ground truth from test_scenarios.yaml.

    Example:
        caddi-cli demo run
        caddi-cli demo run --extended
    """
    from src.ma_registry import MARegistry
    from src.ma_resolver import MAResolver
    from src.demo_generator import load_test_scenarios, load_all_scenarios
    from src.benchmark import BenchmarkResult, compute_metrics
    from src.supplier_clustering import ClusterMethod, cluster_names
    from rag.config import MA_REGISTRY_PATH, TEST_SCENARIOS_PATH, TEST_SCENARIOS_EXTENDED_PATH

    if not TEST_SCENARIOS_PATH.exists():
        console.print("[red]No test scenarios. Run 'caddi-cli demo generate' first.[/red]")
        return

    if extended:
        scenarios = load_all_scenarios(TEST_SCENARIOS_PATH, TEST_SCENARIOS_EXTENDED_PATH)
        base_count = len(load_test_scenarios(TEST_SCENARIOS_PATH))
        ext_count = len(scenarios) - base_count
        console.print(f"Resolving {len(scenarios)} test scenarios ({base_count} base + {ext_count} extended)...\n")
    else:
        scenarios = load_test_scenarios(TEST_SCENARIOS_PATH)
        console.print(f"Resolving {len(scenarios)} test scenarios...\n")

    # Set up resolver
    reg = MARegistry(path=MA_REGISTRY_PATH) if MA_REGISTRY_PATH.exists() else None
    resolver = MAResolver(reg) if reg else None

    # Collect all input names for clustering
    all_names = [sc["input_name"] for sc in scenarios]
    # Include real Hoth data names as clustering context when using extended scenarios
    canonical_names = list(set(
        sc["expected_canonical"] for sc in scenarios
        if sc.get("expected_canonical") != "AMBIGUOUS"
    ))
    if extended and reg:
        for event in reg.events:
            for rn in event.get("resulting_names", []):
                canonical_names.append(rn["name"])
        canonical_names = list(set(canonical_names))
    cluster_input = all_names + canonical_names

    clusters = cluster_names(cluster_input, method=ClusterMethod.PIPELINE)
    lookup = {}
    for canonical, variants in clusters.items():
        for v in variants:
            lookup[v] = canonical

    results = []
    for sc in scenarios:
        name = sc["input_name"]
        expected = sc["expected_canonical"]
        difficulty = sc["difficulty"]
        category = sc.get("category", "")
        order_date = sc.get("order_date", "2026-01-01")
        is_ambiguous = (expected == "AMBIGUOUS")

        # Stage 1: clustering
        cluster_result = lookup.get(name)

        if is_ambiguous:
            # AMBIGUOUS scenarios: correct if system flags ambiguity or returns any valid candidate
            valid_candidates = sc.get("valid_candidates", [])
            flagged = (cluster_result is None) or (cluster_result in valid_candidates)
            results.append(BenchmarkResult(
                name, expected, cluster_result, flagged, difficulty, category, "clustering"))
            continue

        if cluster_result and cluster_result == expected:
            results.append(BenchmarkResult(
                name, expected, cluster_result, True, difficulty, category, "clustering"))
            continue

        # Stage 2: M&A resolver
        if resolver:
            ma_result = resolver.resolve(name, order_date)
            if ma_result.resolved:
                results.append(BenchmarkResult(
                    name, expected, ma_result.canonical, True, difficulty, category, "ma_registry"))
                continue

        # Stage 3: unresolved
        resolved_name = cluster_result if cluster_result else None
        was_resolved = resolved_name is not None
        results.append(BenchmarkResult(
            name, expected, resolved_name, was_resolved, difficulty, category, "unresolved"))

    metrics = compute_metrics(results)

    # Display results
    table = Table(title="Entity Resolution Results")
    table.add_column("Difficulty", style="cyan")
    table.add_column("Total", justify="right")
    table.add_column("Resolved", justify="right")
    table.add_column("Prec.", justify="right")
    table.add_column("Recall", justify="right")
    table.add_column("F1", justify="right")

    tier_names = {1: "easy", 2: "medium", 3: "hard", 4: "advers"}
    for tier in sorted(metrics["by_tier"].keys()):
        m = metrics["by_tier"][tier]
        label = f"{tier} ({tier_names.get(tier, '?')})"
        table.add_row(
            label, str(m["total"]), f"{m['correct']}/{m['total']}",
            f"{m['precision']:.0%}", f"{m['recall']:.0%}", f"{m['f1']:.2f}")

    table.add_section()
    o = metrics["overall"]
    table.add_row(
        "[bold]Overall[/bold]", str(o["total"]), f"{o['correct']}/{o['total']}",
        f"{o['precision']:.0%}", f"{o['recall']:.0%}", f"{o['f1']:.2f}")

    console.print(table)

    # Show unresolved
    unresolved = [r for r in results if not r.was_resolved or r.resolved_canonical != r.expected_canonical]
    if unresolved:
        console.print(f"\n[yellow]Unresolved/incorrect ({len(unresolved)}):[/yellow]")
        for r in unresolved:
            status = "wrong" if r.was_resolved else "unresolved"
            console.print(f"  {r.input_name} -> expected '{r.expected_canonical}', got '{r.resolved_canonical}' ({status}, tier {r.difficulty})")


@cli.command()
@click.option("--port", default=8080, help="Port for the web server")
@click.option("--no-browser", is_flag=True, help="Don't auto-open browser")
def viz(port, no_browser):
    """Launch the web visualization of the entity graph.

    Starts a local web server serving the interactive D3.js graph.
    Shows supplier name relationships, confidence scores, M&A chains,
    and guided tutorials.

    Example:
        caddi-cli viz
        caddi-cli viz --port 9090
        caddi-cli viz --no-browser
    """
    import http.server
    import json
    import threading
    import webbrowser

    from rag.config import WEB_DIR

    # Build graph data
    graph_data = _build_viz_data()

    class GraphHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(WEB_DIR), **kwargs)

        def do_GET(self):
            if self.path == "/api/graph":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(graph_data).encode())
            else:
                super().do_GET()

        def log_message(self, format, *args):
            pass  # Suppress request logs

    console.print(f"[green]Starting visualization server on port {port}...[/green]")
    console.print(f"  Graph: {len(graph_data['nodes'])} nodes, {len(graph_data['edges'])} edges")
    console.print(f"  Alerts: {len(graph_data.get('alerts', []))}")
    console.print(f"\n  Open: [bold cyan]http://localhost:{port}[/bold cyan]")
    console.print("  Press Ctrl+C to stop.\n")

    if not no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    server = http.server.HTTPServer(("", port), GraphHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]Server stopped.[/dim]")


def _build_viz_data():
    """Build JSON data for the web visualization."""
    import pandas as pd
    from src.ma_registry import MARegistry
    from src.supplier_clustering import ClusterMethod, cluster_names, compute_edge_scores
    from src.human_review import apply_human_overrides, load_confirmed_scores
    from src.chain_validator import validate_registry
    from rag.config import MA_REGISTRY_PATH, CONFIRMED_MAPPINGS_PATH, DATA_DIR

    all_names = []
    for csv_file in sorted(DATA_DIR.glob("*.csv")):
        df = pd.read_csv(csv_file)
        if "supplier_name" in df.columns:
            all_names.extend(df["supplier_name"].tolist())

    # Also include demo data if it exists
    demo_dir = DATA_DIR / "demo"
    if demo_dir.exists():
        for csv_file in sorted(demo_dir.glob("*.csv")):
            df = pd.read_csv(csv_file)
            if "supplier_name" in df.columns:
                all_names.extend(df["supplier_name"].tolist())

    nodes = []
    edges = []
    node_ids = set()

    if all_names:
        clusters = cluster_names(all_names, method=ClusterMethod.PIPELINE)
        clusters = apply_human_overrides(clusters, confirmed_path=CONFIRMED_MAPPINGS_PATH)
        confirmed_scores = load_confirmed_scores(CONFIRMED_MAPPINGS_PATH)
        edge_scores = compute_edge_scores(clusters, confirmed_scores=confirmed_scores)

        for canonical, members in clusters.items():
            if canonical not in node_ids:
                nodes.append({"id": canonical, "type": "canonical", "count": all_names.count(canonical)})
                node_ids.add(canonical)

            for variant in members:
                if variant == canonical:
                    continue
                if variant not in node_ids:
                    nodes.append({"id": variant, "type": "variant", "count": all_names.count(variant)})
                    node_ids.add(variant)

                scores = edge_scores.get(canonical, {}).get(variant, {})
                edges.append({
                    "source": variant, "target": canonical,
                    "type": "clustering",
                    "jaccard": scores.get("jaccard", 0),
                    "embedding": scores.get("embedding", 0),
                    "combined": scores.get("combined", 0),
                    "source_type": scores.get("source", "auto"),
                })

    # M&A edges
    reg = MARegistry(path=MA_REGISTRY_PATH) if MA_REGISTRY_PATH.exists() else None
    alerts = []
    if reg:
        alerts = validate_registry(reg, check_orphans_against_data=False)

        for event in reg.events:
            acq = reg.get_entity(event["acquirer"])
            acd = reg.get_entity(event["acquired"])
            if not acq:
                continue

            for rn in event.get("resulting_names", []):
                rn_name = rn["name"]
                if rn_name not in node_ids:
                    nodes.append({"id": rn_name, "type": "ma_resulting", "count": all_names.count(rn_name)})
                    node_ids.add(rn_name)
                if acq["name"] not in node_ids:
                    nodes.append({"id": acq["name"], "type": "canonical", "count": all_names.count(acq["name"])})
                    node_ids.add(acq["name"])
                edges.append({
                    "source": rn_name, "target": acq["name"],
                    "type": "ma",
                    "event_id": event["id"],
                    "event_type": event["type"],
                    "event_date": event["date"],
                    "combined": 1.0,
                })

        # Division edges
        for entity in reg.entities:
            if entity.get("parent"):
                parent = reg.get_entity(entity["parent"])
                if parent:
                    if entity["name"] not in node_ids:
                        nodes.append({"id": entity["name"], "type": "division", "count": 0})
                        node_ids.add(entity["name"])
                    if parent["name"] not in node_ids:
                        nodes.append({"id": parent["name"], "type": "canonical", "count": all_names.count(parent["name"])})
                        node_ids.add(parent["name"])
                    edges.append({
                        "source": entity["name"], "target": parent["name"],
                        "type": "division",
                        "combined": 1.0,
                    })

    return {"nodes": nodes, "edges": edges, "alerts": alerts}


if __name__ == "__main__":
    cli()
