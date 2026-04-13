import yaml
from code_provenance.models import ImageRef


def parse_image_ref(image_string: str) -> ImageRef:
    """Parse a Docker image string into an ImageRef."""
    raw = image_string
    digest = None

    # Handle digest references (image@sha256:... or image:tag@sha256:...)
    if "@" in image_string:
        name_part, digest = image_string.split("@", 1)
        # Check if there's a tag before the digest (image:tag@sha256:...)
        last_segment = name_part.split("/")[-1]
        if ":" in last_segment:
            colon_pos = name_part.rfind(":")
            tag = name_part[colon_pos + 1:]
            image_string = name_part[:colon_pos]
        else:
            tag = digest
            image_string = name_part
    elif ":" in image_string.split("/")[-1]:
        colon_pos = image_string.rfind(":")
        tag = image_string[colon_pos + 1:]
        image_string = image_string[:colon_pos]
    else:
        tag = "latest"

    # Determine registry
    parts = image_string.split("/")
    if len(parts) >= 2 and ("." in parts[0] or ":" in parts[0]):
        registry = parts[0]
        remaining = parts[1:]
    else:
        registry = "docker.io"
        remaining = parts

    # Determine namespace and name
    if len(remaining) == 1:
        namespace = "library"
        name = remaining[0]
    elif len(remaining) == 2:
        namespace = remaining[0]
        name = remaining[1]
    else:
        namespace = remaining[0]
        name = "/".join(remaining[1:])

    return ImageRef(
        registry=registry,
        namespace=namespace,
        name=name,
        tag=tag,
        digest=digest,
        raw=raw,
    )


def parse_compose(yaml_content: str) -> list[tuple[str, str]]:
    """Parse docker-compose YAML and return list of (service_name, image_string)."""
    data = yaml.safe_load(yaml_content)
    if not isinstance(data, dict):
        return []
    services = data.get("services", {}) or {}
    results = []
    for service_name, service_config in services.items():
        if isinstance(service_config, dict) and "image" in service_config:
            results.append((service_name, service_config["image"]))
    return results
