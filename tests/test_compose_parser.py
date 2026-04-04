from code_provenance.compose_parser import parse_compose, parse_image_ref


class TestParseImageRef:
    def test_ghcr_with_tag(self):
        ref = parse_image_ref("ghcr.io/azaidelson/excalidraw:v3.4.12")
        assert ref.registry == "ghcr.io"
        assert ref.namespace == "azaidelson"
        assert ref.name == "excalidraw"
        assert ref.tag == "v3.4.12"

    def test_docker_hub_official(self):
        ref = parse_image_ref("postgres:16.2")
        assert ref.registry == "docker.io"
        assert ref.namespace == "library"
        assert ref.name == "postgres"
        assert ref.tag == "16.2"

    def test_docker_hub_namespaced(self):
        ref = parse_image_ref("bitnami/redis:7.2")
        assert ref.registry == "docker.io"
        assert ref.namespace == "bitnami"
        assert ref.name == "redis"
        assert ref.tag == "7.2"

    def test_no_tag_defaults_to_latest(self):
        ref = parse_image_ref("nginx")
        assert ref.registry == "docker.io"
        assert ref.namespace == "library"
        assert ref.name == "nginx"
        assert ref.tag == "latest"

    def test_ghcr_no_tag(self):
        ref = parse_image_ref("ghcr.io/owner/repo")
        assert ref.tag == "latest"

    def test_digest_reference(self):
        ref = parse_image_ref("nginx@sha256:abc123")
        assert ref.registry == "docker.io"
        assert ref.namespace == "library"
        assert ref.name == "nginx"
        assert ref.tag == "sha256:abc123"


class TestParseCompose:
    def test_extracts_services_and_images(self):
        yaml_content = """
version: '3'
services:
  web:
    image: ghcr.io/azaidelson/excalidraw:v3.4.12
    ports:
      - "80:80"
  db:
    image: postgres:16.2
    environment:
      POSTGRES_PASSWORD: secret
  worker:
    build: ./worker
"""
        services = parse_compose(yaml_content)
        assert len(services) == 2
        assert services[0] == ("web", "ghcr.io/azaidelson/excalidraw:v3.4.12")
        assert services[1] == ("db", "postgres:16.2")

    def test_empty_services(self):
        yaml_content = """
version: '3'
services: {}
"""
        services = parse_compose(yaml_content)
        assert services == []
