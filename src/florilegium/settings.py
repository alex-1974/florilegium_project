from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    src_root: Path
    package_root: Path

    config_dir: Path
    seeds_dir: Path

    var_dir: Path
    cache_dir: Path
    cache_http_dir: Path
    cache_pages_dir: Path
    cache_search_dir: Path

    data_dir: Path
    downloads_dir: Path
    logs_dir: Path


def detect_project_root() -> Path:
    here = Path(__file__).resolve()
    # .../florilegium_project/src/florilegium/settings.py
    # parents[0] = florilegium
    # parents[1] = src
    # parents[2] = florilegium_project
    return here.parents[2]


def get_paths() -> ProjectPaths:
    project_root = detect_project_root()
    src_root = project_root / "src"
    package_root = src_root / "florilegium"

    var_dir = project_root / "var"
    cache_dir = var_dir / "cache"

    return ProjectPaths(
        project_root=project_root,
        src_root=src_root,
        package_root=package_root,
        config_dir=project_root / "config",
        seeds_dir=project_root / "seeds",
        var_dir=var_dir,
        cache_dir=cache_dir,
        cache_http_dir=cache_dir / "http",
        cache_pages_dir=cache_dir / "pages",
        cache_search_dir=cache_dir / "search",
        data_dir=var_dir / "data",
        downloads_dir=var_dir / "downloads",
        logs_dir=var_dir / "logs",
    )


def ensure_runtime_dirs(paths: ProjectPaths | None = None) -> ProjectPaths:
    paths = paths or get_paths()

    for p in (
        paths.var_dir,
        paths.cache_dir,
        paths.cache_http_dir,
        paths.cache_pages_dir,
        paths.cache_search_dir,
        paths.data_dir,
        paths.downloads_dir,
        paths.logs_dir,
    ):
        p.mkdir(parents=True, exist_ok=True)

    return paths
