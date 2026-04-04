import json
from code_provenance.models import ImageResult
from code_provenance.output import format_json, format_table


def _sample_results():
    return [
        ImageResult(
            service="web",
            image="ghcr.io/owner/repo:v1.0",
            registry="ghcr.io",
            repo="https://github.com/owner/repo",
            tag="v1.0",
            commit="abc123def456",
            commit_url="https://github.com/owner/repo/commit/abc123def456",
            status="resolved",
            resolution_method="tag_match",
        ),
        ImageResult(
            service="cache",
            image="redis:7.2",
            registry="docker.io",
            tag="7.2",
            status="repo_not_found",
        ),
    ]


class TestFormatJson:
    def test_output_is_valid_json(self):
        output = format_json(_sample_results())
        data = json.loads(output)
        assert len(data) == 2
        assert data[0]["service"] == "web"
        assert data[0]["commit"] == "abc123def456"
        assert data[1]["status"] == "repo_not_found"
        assert data[1]["commit"] is None


class TestFormatTable:
    def test_table_contains_service_names(self):
        output = format_table(_sample_results())
        assert "web" in output
        assert "cache" in output

    def test_table_contains_status(self):
        output = format_table(_sample_results())
        assert "resolved" in output
        assert "repo_not_found" in output
