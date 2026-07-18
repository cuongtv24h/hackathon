from pathlib import Path

import pytest
from fastapi import HTTPException

from apps.api.main import _spa_response, _static_file_or_none, app


def test_static_file_resolver_serves_only_files_inside_build_directory(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    bundle = assets / "app.js"
    bundle.write_text("console.log('ready')", encoding="utf-8")

    assert _static_file_or_none(tmp_path, "assets/app.js") == bundle
    assert _static_file_or_none(tmp_path, "../outside.js") is None
    assert _static_file_or_none(tmp_path, "assets") is None


def test_spa_response_falls_back_to_index_and_caches_hashed_assets(tmp_path):
    (tmp_path / "index.html").write_text("<html>chat</html>", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    bundle = assets / "index-123.js"
    bundle.write_text("console.log('bundle')", encoding="utf-8")

    spa_response = _spa_response(tmp_path, "appointment/confirmation")
    asset_response = _spa_response(tmp_path, "assets/index-123.js")

    assert Path(spa_response.path) == tmp_path / "index.html"
    assert spa_response.headers["cache-control"] == "no-cache"
    assert Path(asset_response.path) == bundle
    assert asset_response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_spa_response_reports_missing_build_directory(tmp_path):
    with pytest.raises(HTTPException) as error:
        _spa_response(tmp_path / "missing", "")

    assert error.value.status_code == 503


def test_static_routes_are_registered_after_capability_routes():
    route_paths = [route.path for route in app.routes if hasattr(route, "path")]
    included_router_indexes = [
        index for index, route in enumerate(app.routes)
        if type(route).__name__ == "_IncludedRouter"
    ]

    assert "/admin/{asset_path:path}" in route_paths
    assert "/{asset_path:path}" in route_paths
    assert included_router_indexes
    assert max(included_router_indexes) < next(
        index for index, route in enumerate(app.routes)
        if getattr(route, "path", None) == "/{asset_path:path}"
    )
