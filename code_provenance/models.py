from dataclasses import dataclass


@dataclass
class ImageRef:
    """A parsed Docker image reference."""
    registry: str          # e.g. "ghcr.io", "docker.io"
    namespace: str         # e.g. "azaidelson", "library"
    name: str              # e.g. "excalidraw", "postgres"
    tag: str               # e.g. "v3.4.12", "latest"
    raw: str               # original string from docker-compose

    @property
    def full_name(self) -> str:
        """Registry/namespace/name without tag."""
        return f"{self.registry}/{self.namespace}/{self.name}"


@dataclass
class ImageResult:
    """Resolution result for a single image."""
    service: str
    image: str             # original image string
    registry: str
    repo: str | None = None
    tag: str = ""
    commit: str | None = None
    commit_url: str | None = None
    status: str = "repo_not_found"
    resolution_method: str | None = None
