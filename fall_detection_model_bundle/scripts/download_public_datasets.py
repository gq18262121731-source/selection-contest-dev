from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Iterable

import requests
import yaml
from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "datasets.yaml"
CHUNK_SIZE = 1024 * 1024


def load_registry() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)["datasets"]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def download_file(url: str, dest: Path, timeout: int = 120, max_retries: int = 5) -> None:
    ensure_dir(dest.parent)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            headers = {}
            downloaded = 0
            if tmp.exists():
                downloaded = tmp.stat().st_size
                headers["Range"] = f"bytes={downloaded}-"
            with requests.get(url, stream=True, timeout=timeout, headers=headers) as response:
                if response.status_code == 416 and tmp.exists():
                    tmp.rename(dest)
                    print(f"[skip] {dest.name} already complete")
                    return
                response.raise_for_status()
                mode = "ab" if "Range" in headers and response.status_code == 206 else "wb"
                if mode == "wb":
                    downloaded = 0
                total = response.headers.get("Content-Length")
                total_size = downloaded + int(total) if total is not None else None
                with tmp.open(mode) as f:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size:
                            pct = downloaded / total_size * 100
                            print(
                                f"\r[downloading] {dest.name}: {pct:6.2f}% ({downloaded/1e9:.2f} / {total_size/1e9:.2f} GB)",
                                end="",
                            )
                        else:
                            print(f"\r[downloading] {dest.name}: {downloaded/1e9:.2f} GB", end="")
            print()
            tmp.rename(dest)
            print(f"[saved] {dest}")
            return
        except Exception as exc:  # pragma: no cover
            last_error = exc
            print()
            print(f"[warn] download retry {attempt}/{max_retries} for {dest.name}: {exc}")

    raise RuntimeError(f"Failed to download {url}") from last_error


def extract_zip(archive_path: Path, target_dir: Path) -> None:
    marker = target_dir / ".extract_complete"
    if marker.exists():
        print(f"[skip] already extracted: {archive_path.name}")
        return
    ensure_dir(target_dir)
    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(target_dir)
    marker.write_text("ok\n", encoding="utf-8")
    print(f"[extracted] {archive_path.name} -> {target_dir}")


def extract_tar_gz(archive_path: Path, target_dir: Path) -> None:
    marker = target_dir / ".extract_complete"
    if marker.exists():
        print(f"[skip] already extracted: {archive_path.name}")
        return
    ensure_dir(target_dir)
    with tarfile.open(archive_path, "r:gz") as tf:
        tf.extractall(target_dir)
    marker.write_text("ok\n", encoding="utf-8")
    print(f"[extracted] {archive_path.name} -> {target_dir}")


def extract_rar_skeleton_only(archive_path: Path, target_dir: Path) -> None:
    marker = target_dir / ".extract_complete"
    if marker.exists():
        print(f"[skip] already extracted: {archive_path.name}")
        return
    ensure_dir(target_dir)
    proc = subprocess.run(
        ["tar", "-tf", str(archive_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=True,
    )
    files = [line.strip() for line in proc.stdout.splitlines() if line.strip().endswith("skeleton.txt")]
    files.append("readme.pdf")
    batch_size = 20
    for i in range(0, len(files), batch_size):
        batch = files[i : i + batch_size]
        subprocess.run(["tar", "-xf", str(archive_path), "-C", str(target_dir), *batch], check=True)
    marker.write_text("ok\n", encoding="utf-8")
    print(f"[extracted] {archive_path.name} skeletons -> {target_dir}")


def download_hf_dataset(entry: dict, extract: bool) -> None:
    target_dir = ROOT / entry["target_dir"]
    ensure_dir(target_dir)
    snapshot_download(
        repo_id=entry["repo_id"],
        repo_type=entry["repo_type"],
        allow_patterns=entry["allow_patterns"],
        local_dir=str(target_dir),
    )
    print(f"[saved] {entry['repo_id']} -> {target_dir}")
    _ = extract


def parse_urfd_links() -> list[str]:
    url = "https://fenix.ur.edu.pl/~mkepski/ds/uf.html"
    text = requests.get(url, timeout=60).text
    matches = re.findall(r'href=["\'](.*?\.mp4)["\']', text, flags=re.IGNORECASE)
    if not matches:
        raise RuntimeError("No URFD mp4 links were found on the official page.")
    return [f"https://fenix.ur.edu.pl/~mkepski/ds/{m.lstrip('./')}" for m in matches]


def download_urfd(entry: dict, extract: bool) -> None:
    target_dir = ROOT / entry["target_dir"] / "videos"
    ensure_dir(target_dir)
    links = parse_urfd_links()
    for url in links:
        dest = target_dir / Path(url).name
        if dest.exists():
            print(f"[skip] {dest.name}")
            continue
        download_file(url, dest)
    manifest = target_dir.parent / "source_url.txt"
    manifest.write_text(entry["source_url"] + "\n", encoding="utf-8")
    print(f"[done] URFD videos: {len(list(target_dir.glob('*.mp4')))} files")
    _ = extract


def parse_fallpose_archives() -> list[tuple[str, str]]:
    index_url = "https://falldataset.com/data/"
    text = requests.get(index_url, timeout=60).text
    seq_ids = re.findall(r'href="(\d+)/"', text)
    pairs: list[tuple[str, str]] = []
    for seq_id in sorted(set(seq_ids), key=lambda x: int(x)):
        page_url = f"https://falldataset.com/data/{seq_id}/"
        page = requests.get(page_url, timeout=60).text
        archive_matches = re.findall(r'href="([^"]+\.tar\.gz)"', page)
        if not archive_matches:
            raise RuntimeError(f"No archive link found for fallpose sequence {seq_id}.")
        archive_name = archive_matches[0]
        pairs.append((seq_id, page_url + archive_name))
    return pairs


def download_fallpose(entry: dict, extract: bool, limit: int | None) -> None:
    root_dir = ROOT / entry["target_dir"]
    raw_dir = root_dir / "raw"
    extracted_dir = root_dir / "extracted"
    ensure_dir(raw_dir)
    ensure_dir(extracted_dir)
    archives = parse_fallpose_archives()
    if limit:
        archives = archives[:limit]
    for seq_id, url in archives:
        archive_path = raw_dir / f"{seq_id}.tar.gz"
        if not archive_path.exists():
            download_file(url, archive_path)
        else:
            print(f"[skip] {archive_path.name}")
        if extract:
            extract_tar_gz(archive_path, extracted_dir / seq_id)
    print(f"[done] Fall Pose sequences: {len(archives)}")


def download_direct_file(entry: dict, extract: bool) -> None:
    target_dir = ROOT / entry["target_dir"]
    ensure_dir(target_dir)
    archive_path = target_dir / entry["filename"]
    if not archive_path.exists():
        download_file(entry["url"], archive_path)
    else:
        print(f"[skip] {archive_path.name}")
    if extract and archive_path.suffix.lower() == ".zip":
        extract_zip(archive_path, target_dir / "extracted")
    elif extract and archive_path.suffix.lower() == ".rar":
        if entry.get("extract_mode") == "skeleton_only":
            extract_rar_skeleton_only(archive_path, target_dir / "skeleton_only")
        else:
            print(f"[warn] {archive_path.name} is a RAR archive. No extraction mode was configured.")


def run(names: Iterable[str], extract: bool, fallpose_limit: int | None) -> None:
    registry = load_registry()
    for name in names:
        if name not in registry:
            raise KeyError(f"Unknown dataset key: {name}")
        entry = registry[name]
        kind = entry["kind"]
        print(f"\n=== {name} ({kind}) ===")
        print(f"source: {entry.get('source_url', entry.get('url', ''))}")
        if kind == "huggingface":
            download_hf_dataset(entry, extract)
        elif kind == "urfd":
            download_urfd(entry, extract)
        elif kind == "fallpose":
            download_fallpose(entry, extract, fallpose_limit)
        elif kind == "direct_file":
            download_direct_file(entry, extract)
        else:
            raise ValueError(f"Unsupported dataset kind: {kind}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download public fall detection datasets.")
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=["omnifall_labels", "wanfall_splits", "urfd", "gmdcsa24", "fallpose"],
        help="Registry keys from configs/datasets.yaml",
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Extract supported archives after download.",
    )
    parser.add_argument(
        "--fallpose-limit",
        type=int,
        default=None,
        help="Optional limit for the number of Fall Pose sequences to download.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run(args.datasets, args.extract, args.fallpose_limit)
        return 0
    except Exception as exc:  # pragma: no cover
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
