from __future__ import annotations

import argparse
import shutil
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlretrieve

DEFAULT_OWNER = "THUDM"
DEFAULT_REPO = "ComputerRL"
DEFAULT_REF = "main"
DEFAULT_SOURCE_FOLDER = "evaluation_examples"


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DESTINATION = ROOT_DIR / "environments" / "computer_rl_env" / "tasks" / DEFAULT_SOURCE_FOLDER


def build_tarball_url(owner: str, repo: str, ref: str) -> str:
    return f"https://codeload.github.com/{owner}/{repo}/tar.gz/refs/heads/{ref}"


def extract_folder_from_tarball(
    tarball_path: Path,
    source_folder: str,
    destination: Path,
    force: bool,
) -> None:
    source_folder = source_folder.strip("/")

    with tempfile.TemporaryDirectory(prefix="computer-rl-download-") as temp_dir:
        extract_root = Path(temp_dir) / "extract"
        extract_root.mkdir(parents=True, exist_ok=True)

        with tarfile.open(tarball_path, "r:gz") as archive:
            archive.extractall(extract_root)

        matching_sources = [
            path for path in extract_root.rglob(source_folder) if path.is_dir() and path.name == source_folder
        ]

        if not matching_sources:
            raise FileNotFoundError(f"Could not find folder '{source_folder}' in downloaded archive")

        if len(matching_sources) > 1:
            raise RuntimeError(
                f"Found multiple matching '{source_folder}' folders in archive. "
                "Set a more specific source folder."
            )

        source_path = matching_sources[0]

        if destination.exists():
            if not force:
                raise FileExistsError(
                    f"Destination already exists: {destination}. Use --force to replace it."
                )
            shutil.rmtree(destination)

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_path, destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download a folder from a GitHub repository tarball and copy it to a local destination."
        )
    )
    parser.add_argument("--owner", default=DEFAULT_OWNER, help=f"GitHub owner (default: {DEFAULT_OWNER})")
    parser.add_argument("--repo", default=DEFAULT_REPO, help=f"Repository name (default: {DEFAULT_REPO})")
    parser.add_argument(
        "--ref",
        default=DEFAULT_REF,
        help=f"Branch or ref under refs/heads to fetch (default: {DEFAULT_REF})",
    )
    parser.add_argument(
        "--source-folder",
        default=DEFAULT_SOURCE_FOLDER,
        help=f"Folder path/name in the repository tarball (default: {DEFAULT_SOURCE_FOLDER})",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=DEFAULT_DESTINATION,
        help=f"Destination directory (default: {DEFAULT_DESTINATION})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace destination if it already exists",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    tarball_url = build_tarball_url(args.owner, args.repo, args.ref)

    with tempfile.TemporaryDirectory(prefix="computer-rl-tarball-") as temp_dir:
        tarball_path = Path(temp_dir) / f"{args.repo}-{args.ref}.tar.gz"
        print(f"Downloading {tarball_url}")
        urlretrieve(tarball_url, tarball_path)

        extract_folder_from_tarball(
            tarball_path=tarball_path,
            source_folder=args.source_folder,
            destination=args.destination,
            force=args.force,
        )

    print(f"Synced '{args.source_folder}' to: {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
