import json
from dataclasses import asdict
from io import StringIO
from rich.console import Console
from rich.table import Table
from code_provenance.models import ImageResult


def format_json(results: list[ImageResult]) -> str:
    """Format results as a JSON array."""
    return json.dumps([asdict(r) for r in results], indent=2)


def format_table(results: list[ImageResult]) -> str:
    """Format results as a rich table, returned as a string."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("SERVICE")
    table.add_column("IMAGE")
    table.add_column("REPO")
    table.add_column("COMMIT")
    table.add_column("STATUS")

    for r in results:
        commit_display = r.commit[:12] if r.commit else "-"
        repo_display = r.repo.replace("https://", "") if r.repo else "-"
        table.add_row(r.service, r.image, repo_display, commit_display, r.status)

    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=160)
    console.print(table)
    return buf.getvalue()
