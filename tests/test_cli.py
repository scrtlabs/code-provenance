import json
import os
import tempfile
from unittest.mock import patch
from code_provenance.cli import main
from code_provenance.models import ImageResult


SAMPLE_COMPOSE = """\
version: '3'
services:
  web:
    image: ghcr.io/acme-org/excalidraw:v3.4.12
    ports:
      - "80:80"
  db:
    image: postgres:16.2
"""


class TestCli:
    @patch("code_provenance.cli.resolve_image")
    def test_json_output(self, mock_resolve, capsys):
        mock_resolve.return_value = ImageResult(
            service="web",
            image="ghcr.io/acme-org/excalidraw:v3.4.12",
            registry="ghcr.io",
            repo="https://github.com/acme-org/excalidraw",
            tag="v3.4.12",
            commit="0f769068b3f1",
            commit_url="https://github.com/acme-org/excalidraw/commit/0f769068b3f1",
            status="resolved",
            resolution_method="tag_match",
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(SAMPLE_COMPOSE)
            f.flush()
            try:
                main([f.name, "--json"])
                captured = capsys.readouterr()
                data = json.loads(captured.out)
                assert len(data) == 2
                assert data[0]["status"] == "resolved"
            finally:
                os.unlink(f.name)

    def test_missing_file(self, capsys):
        code = main(["/nonexistent/docker-compose.yml"])
        assert code == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower()
