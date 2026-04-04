from unittest.mock import patch
from code_provenance.models import ImageRef
from code_provenance.resolver import resolve_image


class TestResolveImage:
    @patch("code_provenance.resolver.fetch_oci_labels")
    def test_oci_labels_resolution(self, mock_labels):
        mock_labels.return_value = {
            "org.opencontainers.image.source": "https://github.com/owner/repo",
            "org.opencontainers.image.revision": "abc123def456",
        }
        ref = ImageRef("ghcr.io", "owner", "repo", "v1.0", "ghcr.io/owner/repo:v1.0")
        result = resolve_image("web", ref)
        assert result.status == "resolved"
        assert result.commit == "abc123def456"
        assert result.repo == "https://github.com/owner/repo"
        assert result.resolution_method == "oci_labels"

    @patch("code_provenance.resolver.resolve_tag_to_commit")
    @patch("code_provenance.resolver.fetch_oci_labels")
    def test_ghcr_tag_match_fallback(self, mock_labels, mock_tag):
        mock_labels.return_value = {}
        mock_tag.return_value = "0f769068b3f1"

        ref = ImageRef("ghcr.io", "azaidelson", "excalidraw", "v3.4.12", "ghcr.io/azaidelson/excalidraw:v3.4.12")
        result = resolve_image("web", ref)
        assert result.status == "resolved"
        assert result.commit == "0f769068b3f1"
        assert result.repo == "https://github.com/azaidelson/excalidraw"
        assert result.resolution_method == "tag_match"
        mock_tag.assert_called_once_with("azaidelson", "excalidraw", "v3.4.12")

    @patch("code_provenance.resolver.resolve_tag_to_commit")
    @patch("code_provenance.resolver.infer_repo_from_dockerhub")
    @patch("code_provenance.resolver.fetch_oci_labels")
    def test_dockerhub_inference_and_tag_match(self, mock_labels, mock_infer, mock_tag):
        mock_labels.return_value = {}
        mock_infer.return_value = ("docker-library", "postgres")
        mock_tag.return_value = "a1b2c3d4"

        ref = ImageRef("docker.io", "library", "postgres", "16.2", "postgres:16.2")
        result = resolve_image("db", ref)
        assert result.status == "resolved"
        assert result.commit == "a1b2c3d4"
        assert result.repo == "https://github.com/docker-library/postgres"

    @patch("code_provenance.resolver.resolve_tag_to_commit")
    @patch("code_provenance.resolver.fetch_oci_labels")
    def test_tag_not_matched(self, mock_labels, mock_tag):
        mock_labels.return_value = {}
        mock_tag.return_value = None

        ref = ImageRef("ghcr.io", "owner", "repo", "v9.9.9", "ghcr.io/owner/repo:v9.9.9")
        result = resolve_image("svc", ref)
        assert result.status == "repo_found_tag_not_matched"
        assert result.commit is None

    def test_commit_sha_as_tag(self):
        sha = "ac99122bcbd69f56a7d6523cbc883df9c4766e4c1046b661b76803087e4f475a"
        ref = ImageRef("ghcr.io", "owner", "repo", sha, f"ghcr.io/owner/repo:{sha}")
        with patch("code_provenance.resolver.fetch_oci_labels", return_value={}):
            result = resolve_image("svc", ref)
        assert result.status == "resolved"
        assert result.commit == sha
        assert result.resolution_method == "commit_sha_tag"

    @patch("code_provenance.resolver.resolve_ghcr_digest_via_packages")
    @patch("code_provenance.resolver.fetch_oci_labels")
    def test_digest_ref_no_packages_api(self, mock_labels, mock_packages):
        """Digest ref with no packages API result reports no_tag."""
        mock_labels.return_value = {}
        mock_packages.return_value = None
        digest = "sha256:1de50018f208c9a93a21d40b1a830670d113d272b53a45d322c50de9b4db1239"
        ref = ImageRef("ghcr.io", "morpheusais", "morpheus-lumerin-node-tee", digest,
                        f"ghcr.io/morpheusais/morpheus-lumerin-node-tee@{digest}")
        result = resolve_image("proxy-router", ref)
        assert result.status == "no_tag"

    @patch("code_provenance.resolver.resolve_ghcr_digest_via_packages")
    @patch("code_provenance.resolver.fetch_oci_labels")
    def test_digest_ref_resolved_via_packages_api(self, mock_labels, mock_packages):
        """Digest ref resolved via packages API."""
        mock_labels.return_value = {}
        mock_packages.return_value = {
            "repo": "MorpheusAIs/Morpheus-Lumerin-Node",
            "commit": "abc123def456",
            "tags": ["v5.0.0"],
        }
        digest = "sha256:1de50018f208c9a93a21d40b1a830670d113d272b53a45d322c50de9b4db1239"
        ref = ImageRef("ghcr.io", "morpheusais", "morpheus-lumerin-node-tee", digest,
                        f"ghcr.io/morpheusais/morpheus-lumerin-node-tee@{digest}")
        result = resolve_image("proxy-router", ref)
        assert result.status == "resolved"
        assert result.commit == "abc123def456"
        assert result.repo == "https://github.com/MorpheusAIs/Morpheus-Lumerin-Node"
        assert result.resolution_method == "packages_api"

    @patch("code_provenance.resolver.resolve_ghcr_digest_via_packages")
    @patch("code_provenance.resolver.fetch_oci_labels")
    def test_digest_ref_packages_api_no_commit(self, mock_labels, mock_packages):
        """Packages API found the version but no resolvable tags."""
        mock_labels.return_value = {}
        mock_packages.return_value = {
            "repo": "MorpheusAIs/Morpheus-Lumerin-Node",
            "commit": None,
            "tags": [],
        }
        digest = "sha256:1de50018f208c9a93a21d40b1a830670d113d272b53a45d322c50de9b4db1239"
        ref = ImageRef("ghcr.io", "morpheusais", "morpheus-lumerin-node-tee", digest,
                        f"ghcr.io/morpheusais/morpheus-lumerin-node-tee@{digest}")
        result = resolve_image("proxy-router", ref)
        assert result.status == "no_tag"
        assert result.repo == "https://github.com/MorpheusAIs/Morpheus-Lumerin-Node"
