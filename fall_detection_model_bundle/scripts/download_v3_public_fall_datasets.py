from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"
DATASETS = LAB / "datasets"
REPORTS = LAB / "reports"
MANIFESTS = LAB / "manifests"


@dataclass(frozen=True)
class DownloadItem:
    dataset_key: str
    source_name: str
    url: str
    local_dir: Path
    license: str
    license_action: str
    intended_use: str
    scene_coverage: str
    extract: bool = False
    expected_size_bytes: int | None = None


def urfd_items(max_falls: int, max_adls: int) -> list[DownloadItem]:
    base = "https://fenix.ur.edu.pl/~mkepski/ds/data"
    items: list[DownloadItem] = []
    for i in range(1, max_falls + 1):
        items.append(
            DownloadItem(
                dataset_key="urfd",
                source_name=f"URFD fall {i:02d} cam0 RGB",
                url=f"{base}/fall-{i:02d}-cam0-rgb.zip",
                local_dir=DATASETS / "external_research_only" / "urfd" / "raw",
                license="CC BY-NC-SA 4.0",
                license_action="Research/shadow training only unless commercial permission is obtained from dataset authors.",
                intended_use="positive fall video frames; temporal fall transition/fallen evidence",
                scene_coverage="controlled indoor falls and ADL",
                extract=False,
            )
        )
        items.append(
            DownloadItem(
                dataset_key="urfd",
                source_name=f"URFD fall {i:02d} accelerometer CSV",
                url=f"{base}/fall-{i:02d}-data.csv",
                local_dir=DATASETS / "external_research_only" / "urfd" / "raw",
                license="CC BY-NC-SA 4.0",
                license_action="Research/shadow training only unless commercial permission is obtained from dataset authors.",
                intended_use="temporal alignment metadata",
                scene_coverage="controlled indoor falls",
                extract=False,
            )
        )
    for i in range(1, max_adls + 1):
        items.append(
            DownloadItem(
                dataset_key="urfd",
                source_name=f"URFD ADL {i:02d} cam0 RGB",
                url=f"{base}/adl-{i:02d}-cam0-rgb.zip",
                local_dir=DATASETS / "external_research_only" / "urfd" / "raw",
                license="CC BY-NC-SA 4.0",
                license_action="Research/shadow training only unless commercial permission is obtained from dataset authors.",
                intended_use="hard-negative ADL frames; walking/sitting/bending-like contrast",
                scene_coverage="controlled indoor ADL",
                extract=False,
            )
        )
        items.append(
            DownloadItem(
                dataset_key="urfd",
                source_name=f"URFD ADL {i:02d} accelerometer CSV",
                url=f"{base}/adl-{i:02d}-data.csv",
                local_dir=DATASETS / "external_research_only" / "urfd" / "raw",
                license="CC BY-NC-SA 4.0",
                license_action="Research/shadow training only unless commercial permission is obtained from dataset authors.",
                intended_use="temporal alignment metadata",
                scene_coverage="controlled indoor ADL",
                extract=False,
            )
        )
    return items


def gmdcsa24_item() -> DownloadItem:
    return DownloadItem(
        dataset_key="gmdcsa24",
        source_name="GMDCSA-24 Zenodo v2.0 archive",
        url="https://zenodo.org/api/records/12921216/files/ekramalam/GMDCSA24-A-Dataset-for-Human-Fall-Detection-in-Videos-v2.0.zip/content",
        local_dir=DATASETS / "external_authorized" / "gmdcsa24" / "raw",
        license="CC BY 4.0",
        license_action="Allowed for training with attribution; keep source and DOI in dataset manifest.",
        intended_use="low-resolution/household-style fall and ADL video coverage",
        scene_coverage="videos for human fall detection; useful for low-resolution and broad fall/no-fall contrast",
        extract=False,
        expected_size_bytes=1107543412,
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def target_name_from_url(url: str, fallback: str) -> str:
    clean = url.split("?", 1)[0].rstrip("/")
    name = clean.rsplit("/", 1)[-1]
    if name == "content" or not name:
        return fallback
    return name


def stream_download(item: DownloadItem, session: requests.Session, overwrite: bool) -> dict[str, object]:
    item.local_dir.mkdir(parents=True, exist_ok=True)
    fallback = item.source_name.lower().replace(" ", "_").replace("/", "_") + ".zip"
    filename = target_name_from_url(item.url, fallback)
    if item.dataset_key == "gmdcsa24":
        filename = "GMDCSA24-A-Dataset-for-Human-Fall-Detection-in-Videos-v2.0.zip"
    target = item.local_dir / filename
    meta_target = target.with_suffix(target.suffix + ".source.json")

    status = "downloaded"
    started = time.time()
    if target.exists() and not overwrite:
        status = "exists"
    else:
        with session.get(item.url, stream=True, timeout=60) as response:
            response.raise_for_status()
            tmp = target.with_suffix(target.suffix + ".part")
            with tmp.open("wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            tmp.replace(target)

    size = target.stat().st_size if target.exists() else 0
    digest = sha256_file(target) if target.exists() and size > 0 else ""
    extracted_dir = ""
    if item.extract and target.suffix.lower() == ".zip":
        extracted_dir_path = target.parent.parent / "extracted" / target.stem
        extracted_dir_path.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target) as zf:
            zf.extractall(extracted_dir_path)
        extracted_dir = str(extracted_dir_path.resolve())

    meta = {
        **asdict(item),
        "local_dir": str(item.local_dir.resolve()),
        "local_path": str(target.resolve()),
        "status": status,
        "size_bytes": size,
        "sha256": digest,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.time() - started, 3),
        "extracted_dir": extracted_dir,
    }
    meta_target.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def write_reports(rows: list[dict[str, object]]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS / "public_dataset_downloads.v3.json"
    csv_path = MANIFESTS / "public_dataset_downloads.v3.csv"
    md_path = REPORTS / "public_dataset_downloads.v3.md"
    json_path.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "items": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = [
        "dataset_key",
        "source_name",
        "status",
        "local_path",
        "size_bytes",
        "license",
        "license_action",
        "intended_use",
        "scene_coverage",
        "sha256",
        "url",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    lines = [
        "# Public Dataset Downloads V3",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| Dataset | Source | Status | License | Local Path | Use |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('dataset_key')} | {row.get('source_name')} | {row.get('status')} | "
            f"{row.get('license')} | `{row.get('local_path')}` | {row.get('intended_use')} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def selected_items(args: argparse.Namespace) -> Iterable[DownloadItem]:
    keys = set(args.dataset)
    if "urfd" in keys:
        yield from urfd_items(args.urfd_falls, args.urfd_adls)
    if "gmdcsa24" in keys:
        yield gmdcsa24_item()


def main() -> int:
    parser = argparse.ArgumentParser(description="Download traceable public fall datasets for the V3 lab.")
    parser.add_argument("--dataset", action="append", choices=["urfd", "gmdcsa24"], default=[])
    parser.add_argument("--urfd-falls", type=int, default=5)
    parser.add_argument("--urfd-adls", type=int, default=5)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not args.dataset:
        args.dataset = ["urfd", "gmdcsa24"]

    session = requests.Session()
    session.headers.update({"User-Agent": "health-v3-fall-dataset-downloader/1.0"})
    rows: list[dict[str, object]] = []
    for item in selected_items(args):
        print(f"[download] {item.dataset_key}: {item.source_name}")
        rows.append(stream_download(item, session, args.overwrite))
    write_reports(rows)
    print(json.dumps({"downloaded_or_existing": len(rows), "report": str((REPORTS / "public_dataset_downloads.v3.md").resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
