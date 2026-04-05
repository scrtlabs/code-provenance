"""Integration tests that hit real registries and GitHub API.

Skip with: pytest -m 'not integration'
"""
import pytest
from code_provenance.compose_parser import parse_image_ref
from code_provenance.resolver import resolve_image


@pytest.mark.integration
def test_dockerhub_tag_resolution():
    """Test against real traefik:v3.6.0 on Docker Hub."""
    ref = parse_image_ref("traefik:v3.6.0")
    result = resolve_image("web", ref)
    assert result.repo == "https://github.com/traefik/traefik"
    assert result.commit is not None
    assert len(result.commit) >= 12
    assert result.status == "resolved"
    assert result.confidence == "exact"


@pytest.mark.integration
def test_commit_sha_tag():
    """Test that a commit-SHA tag is detected directly."""
    sha = "ac99122bcbd69f56a7d6523cbc883df9c4766e4c1046b661b76803087e4f475a"
    ref = parse_image_ref(f"ghcr.io/someorg/somerepo:{sha}")
    result = resolve_image("svc", ref)
    assert result.status == "resolved"
    assert result.resolution_method == "commit_sha_tag"
    assert result.commit == sha
