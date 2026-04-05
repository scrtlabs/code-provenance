import json
from dataclasses import asdict
from code_provenance.models import ImageResult


def format_json(results: list[ImageResult]) -> str:
    """Format results as a JSON array."""
    return json.dumps([asdict(r) for r in results], indent=2)


def format_text(results: list[ImageResult]) -> str:
    """Format results as plain text, one block per image."""
    blocks = []
    for r in results:
        commit = r.commit[:12] if r.commit else "-"
        repo = r.repo.replace("https://", "") if r.repo else "-"
        confidence = r.confidence or "-"
        lines = [
            f"{r.service}: {r.image}",
            f"  repo:       {repo}",
            f"  commit:     {commit}",
            f"  status:     {r.status}",
            f"  confidence: {confidence}",
        ]
        if r.commit_url:
            lines.append(f"  url:        {r.commit_url}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
