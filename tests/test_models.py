from code_provenance.models import ImageRef, ImageResult


def test_image_ref_full_name():
    ref = ImageRef(
        registry="ghcr.io",
        namespace="azaidelson",
        name="excalidraw",
        tag="v3.4.12",
        raw="ghcr.io/azaidelson/excalidraw:v3.4.12",
    )
    assert ref.full_name == "ghcr.io/azaidelson/excalidraw"


def test_image_result_defaults():
    r = ImageResult(service="web", image="nginx:latest", registry="docker.io")
    assert r.status == "repo_not_found"
    assert r.commit is None
    assert r.resolution_method is None
