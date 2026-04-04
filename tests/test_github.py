import os
from unittest.mock import patch, MagicMock
from code_provenance.github import resolve_tag_to_commit, infer_repo_from_dockerhub, github_headers, check_github_repo_exists


class TestGithubHeaders:
    @patch.dict(os.environ, {}, clear=True)
    def test_no_token(self):
        h = github_headers()
        assert "Authorization" not in h
        assert h["Accept"] == "application/vnd.github+json"

    @patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test123"})
    def test_with_token(self):
        h = github_headers()
        assert h["Authorization"] == "Bearer ghp_test123"


class TestResolveTagToCommit:
    @patch("code_provenance.github.requests.get")
    def test_exact_match(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"name": "v3.4.12", "commit": {"sha": "0f769068b3f1abcdef"}},
                {"name": "v3.4.11", "commit": {"sha": "aaa111bbb222"}},
            ],
            links={},
        )
        sha = resolve_tag_to_commit("azaidelson", "excalidraw", "v3.4.12")
        assert sha == "0f769068b3f1abcdef"

    @patch("code_provenance.github.requests.get")
    def test_match_with_v_prefix(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"name": "v3.4.12", "commit": {"sha": "0f769068b3f1abcdef"}},
            ],
            links={},
        )
        sha = resolve_tag_to_commit("azaidelson", "excalidraw", "3.4.12")
        assert sha == "0f769068b3f1abcdef"

    @patch("code_provenance.github.requests.get")
    def test_no_match(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"name": "v1.0.0", "commit": {"sha": "aaa111"}},
            ],
            links={},
        )
        sha = resolve_tag_to_commit("owner", "repo", "v9.9.9")
        assert sha is None

    @patch("code_provenance.github.requests.get")
    def test_paginated_tags(self, mock_get):
        page1 = MagicMock(
            status_code=200,
            json=lambda: [{"name": f"v0.{i}", "commit": {"sha": f"sha{i}"}} for i in range(100)],
            links={"next": {"url": "https://api.github.com/repos/o/r/tags?page=2"}},
        )
        page2 = MagicMock(
            status_code=200,
            json=lambda: [{"name": "v1.0.0", "commit": {"sha": "target_sha"}}],
            links={},
        )
        mock_get.side_effect = [page1, page2]
        sha = resolve_tag_to_commit("o", "r", "v1.0.0")
        assert sha == "target_sha"

    @patch("code_provenance.github.requests.get")
    def test_prefix_match_picks_highest_version(self, mock_get):
        """v2.10 should match the highest v2.10.x tag."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"name": "v2.10.7", "commit": {"sha": "sha_v2107"}},
                {"name": "v2.10.6", "commit": {"sha": "sha_v2106"}},
                {"name": "v2.10.0", "commit": {"sha": "sha_v2100"}},
                {"name": "v2.9.0", "commit": {"sha": "sha_v290"}},
            ],
            links={},
        )
        sha = resolve_tag_to_commit("traefik", "traefik", "v2.10")
        assert sha == "sha_v2107"

    @patch("code_provenance.github.requests.get")
    def test_prefix_match_does_not_match_different_minor(self, mock_get):
        """v2.1 should not match v2.10.x."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"name": "v2.10.7", "commit": {"sha": "sha_v2107"}},
            ],
            links={},
        )
        sha = resolve_tag_to_commit("owner", "repo", "v2.1")
        assert sha is None

    @patch("code_provenance.github.requests.get")
    def test_exact_match_preferred_over_prefix(self, mock_get):
        """If exact match exists, don't use prefix match."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"name": "v2.10", "commit": {"sha": "sha_exact"}},
                {"name": "v2.10.7", "commit": {"sha": "sha_v2107"}},
            ],
            links={},
        )
        sha = resolve_tag_to_commit("owner", "repo", "v2.10")
        assert sha == "sha_exact"


class TestCheckGithubRepoExists:
    @patch("code_provenance.github.requests.get")
    def test_exists(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        assert check_github_repo_exists("traefik", "traefik") is True

    @patch("code_provenance.github.requests.get")
    def test_not_exists(self, mock_get):
        mock_get.return_value = MagicMock(status_code=404)
        assert check_github_repo_exists("nonexistent", "repo") is False


class TestInferRepoFromDockerhub:
    @patch("code_provenance.github.check_github_repo_exists")
    def test_official_image_tries_name_as_org(self, mock_exists):
        """For library/traefik, try traefik/traefik on GitHub first."""
        mock_exists.return_value = True
        owner, repo = infer_repo_from_dockerhub("library", "traefik")
        assert owner == "traefik"
        assert repo == "traefik"
        mock_exists.assert_called_once_with("traefik", "traefik")

    @patch("code_provenance.github.requests.get")
    @patch("code_provenance.github.check_github_repo_exists")
    def test_falls_back_to_description(self, mock_exists, mock_get):
        mock_exists.return_value = False
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "full_description": "Source: https://github.com/docker-library/postgres",
                "description": "The PostgreSQL object-relational database system",
            },
        )
        owner, repo = infer_repo_from_dockerhub("library", "postgres")
        assert owner == "docker-library"
        assert repo == "postgres"

    @patch("code_provenance.github.requests.get")
    @patch("code_provenance.github.check_github_repo_exists")
    def test_no_github_url(self, mock_exists, mock_get):
        mock_exists.return_value = False
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "full_description": "Some image with no GitHub link",
                "description": "",
            },
        )
        result = infer_repo_from_dockerhub("someuser", "someimage")
        assert result is None
