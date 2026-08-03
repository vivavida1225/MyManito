"""Create a Docker deployment ZIP without local dependencies or databases."""

from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_PREFIX = "MyManito-docker-"
EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    "dist",
    "docs",
    "node_modules",
    "venv",
}
EXCLUDED_DATABASE_SUFFIXES = (".sqlite3", ".sqlite3-journal", ".sqlite3-shm", ".sqlite3-wal")
EXCLUDED_POSTGRES_DUMP_SUFFIXES = (".dump", ".backup")
EXCLUDED_LOCAL_ENV_SUFFIX = ".local"
EXCLUDED_RELATIVE_DIRECTORIES = {
    Path("data/migration-backups"),
    Path("data/postgres"),
}


def should_exclude(path: Path, archive_path: Path) -> bool:
    relative_path = path.relative_to(PROJECT_ROOT)
    if path == archive_path:
        return True
    if any(part in EXCLUDED_DIRECTORIES for part in relative_path.parts):
        return True
    if any(
        relative_path == directory or directory in relative_path.parents
        for directory in EXCLUDED_RELATIVE_DIRECTORIES
    ):
        return True
    if path.is_file() and path.name.endswith(EXCLUDED_DATABASE_SUFFIXES):
        return True
    if path.is_file() and path.name.endswith(EXCLUDED_POSTGRES_DUMP_SUFFIXES):
        return True
    if (
        path.name.startswith(".env")
        and path.name.endswith(EXCLUDED_LOCAL_ENV_SUFFIX)
    ):
        return True
    return (
        path.parent == PROJECT_ROOT
        and path.name.startswith(ARCHIVE_PREFIX)
        and path.suffix == ".zip"
    )


def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = PROJECT_ROOT / f"{ARCHIVE_PREFIX}{timestamp}.zip"
    files = sorted(
        (
            path
            for path in PROJECT_ROOT.rglob("*")
            if path.is_file() and not should_exclude(path, archive_path)
        ),
        key=lambda path: path.as_posix(),
    )

    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(PROJECT_ROOT).as_posix())

    size_megabytes = archive_path.stat().st_size / 1024 / 1024
    print(f"Created {archive_path.name} with {len(files)} files ({size_megabytes:.1f} MB).")


if __name__ == "__main__":
    main()
