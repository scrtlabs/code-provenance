from unittest.mock import patch, MagicMock
from code_provenance.registry import fetch_oci_labels, get_registry_token
from code_provenance.models import ImageRef


class TestGetRegistryToken:
    @patch("code_provenance.registry.requests.get")
    def test_ghcr_token(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"token": "test-token-123"},
        )
        token = get_registry_token("ghcr.io", "azaidelson/excalidraw")
        assert token == "test-token-123"
        mock_get.assert_called_once_with(
            "https://ghcr.io/token",
            params={"scope": "repository:azaidelson/excalidraw:pull"},
            timeout=10,
        )

    @patch("code_provenance.registry.requests.get")
    def test_docker_hub_token(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"token": "hub-token-456"},
        )
        token = get_registry_token("docker.io", "library/postgres")
        assert token == "hub-token-456"
        mock_get.assert_called_once_with(
            "https://auth.docker.io/token",
            params={
                "service": "registry.docker.io",
                "scope": "repository:library/postgres:pull",
            },
            timeout=10,
        )


class TestFetchOciLabels:
    @patch("code_provenance.registry.requests.get")
    @patch("code_provenance.registry.get_registry_token")
    def test_returns_labels_when_present(self, mock_token, mock_get):
        mock_token.return_value = "fake-token"

        manifest_response = MagicMock(
            status_code=200,
            json=lambda: {
                "config": {"digest": "sha256:abc123"},
            },
        )
        config_response = MagicMock(
            status_code=200,
            json=lambda: {
                "config": {
                    "Labels": {
                        "org.opencontainers.image.source": "https://github.com/owner/repo",
                        "org.opencontainers.image.revision": "deadbeef1234",
                    }
                }
            },
        )
        mock_get.side_effect = [manifest_response, config_response]

        ref = ImageRef("ghcr.io", "owner", "repo", "v1.0", "ghcr.io/owner/repo:v1.0")
        labels = fetch_oci_labels(ref)
        assert labels["org.opencontainers.image.source"] == "https://github.com/owner/repo"
        assert labels["org.opencontainers.image.revision"] == "deadbeef1234"

    @patch("code_provenance.registry.requests.get")
    @patch("code_provenance.registry.get_registry_token")
    def test_returns_empty_dict_on_failure(self, mock_token, mock_get):
        mock_token.return_value = "fake-token"
        mock_get.return_value = MagicMock(status_code=404)

        ref = ImageRef("ghcr.io", "owner", "repo", "v1.0", "ghcr.io/owner/repo:v1.0")
        labels = fetch_oci_labels(ref)
        assert labels == {}
