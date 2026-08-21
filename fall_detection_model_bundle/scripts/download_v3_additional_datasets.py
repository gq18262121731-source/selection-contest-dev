#!/usr/bin/env python
"""Download additional fall-detection datasets into the V3 lab.

The script only downloads sources that are publicly reachable without manual
login. Datasets that require credentials or have unclear production rights are
recorded as pending in the generated manifest instead of being mixed into the
training pool.
"""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "v3_upgrade_lab"
DATASETS = LAB / "datasets"
REPORTS = LAB / "reports"
MANIFESTS = LAB / "manifests"


@dataclass
class DatasetRecord:
    name: str
    modality: str
    scene_coverage: str
    license: str
    status: str
    source_url: str
    local_path: str
    notes: str
    size_bytes: int = 0
    file_count: int = 0


def dir_stats(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    files = [p for p in path.rglob("*") if p.is_file()]
    return len(files), sum(p.stat().st_size for p in files)


def ensure_dirs() -> None:
    for path in [
        DATASETS / "external_authorized",
        DATASETS / "external_research_only",
        DATASETS / "external_candidates",
        DATASETS / "external_restricted_pending",
        REPORTS,
        MANIFESTS,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def write_source_json(path: Path, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def download_hf_dataset(
    *,
    repo_id: str,
    dest: Path,
    allow_patterns: Iterable[str] | None,
    license_name: str,
    modality: str,
    scene_coverage: str,
    notes: str,
    status: str = "downloaded",
) -> DatasetRecord:
    dest.mkdir(parents=True, exist_ok=True)
    local = snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        local_dir=str(dest),
        local_dir_use_symlinks=False,
        allow_patterns=list(allow_patterns) if allow_patterns else None,
        resume_download=True,
    )
    source = {
        "repo_id": repo_id,
        "source_url": f"https://huggingface.co/datasets/{repo_id}",
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "license": license_name,
        "allow_patterns": list(allow_patterns) if allow_patterns else None,
        "notes": notes,
    }
    write_source_json(dest / ".source.json", source)
    count, size = dir_stats(Path(local))
    return DatasetRecord(
        name=repo_id.replace("/", "__"),
        modality=modality,
        scene_coverage=scene_coverage,
        license=license_name,
        status=status,
        source_url=source["source_url"],
        local_path=str(Path(local)),
        notes=notes,
        file_count=count,
        size_bytes=size,
    )


def try_download_url(
    *,
    name: str,
    url: str,
    dest_file: Path,
    license_name: str,
    modality: str,
    scene_coverage: str,
    notes: str,
) -> DatasetRecord:
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    status = "downloaded"
    error = ""
    if not dest_file.exists() or dest_file.stat().st_size == 0:
        try:
            with requests.get(url, stream=True, timeout=60, headers={"User-Agent": "Mozilla/5.0"}) as r:
                if r.status_code >= 400:
                    status = f"blocked_http_{r.status_code}"
                    error = r.text[:300]
                else:
                    with dest_file.open("wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
        except Exception as exc:  # noqa: BLE001
            status = "download_failed"
            error = repr(exc)
    meta = {
        "name": name,
        "source_url": url,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "license": license_name,
        "status": status,
        "error": error,
        "notes": notes,
    }
    write_source_json(dest_file.with_suffix(dest_file.suffix + ".source.json"), meta)
    return DatasetRecord(
        name=name,
        modality=modality,
        scene_coverage=scene_coverage,
        license=license_name,
        status=status,
        source_url=url,
        local_path=str(dest_file),
        notes=notes if not error else f"{notes} | error={error}",
        file_count=1 if dest_file.exists() else 0,
        size_bytes=dest_file.stat().st_size if dest_file.exists() else 0,
    )


def copy_existing_inventory(records: list[DatasetRecord]) -> None:
    existing = [
        (
            "gmdcsa24",
            DATASETS / "external_authorized" / "gmdcsa24",
            "RGB video + CSV",
            "living room/far view fall and ADL; 79 fall, 81 ADL videos",
            "CC BY 4.0 / project-recorded source metadata",
            "downloaded_preexisting",
            "Already downloaded earlier and used to build YOLO autolabel dataset.",
        ),
        (
            "fallvision_keypoints",
            DATASETS / "external_authorized" / "fallvision_keypoints",
            "keypoint CSV archives",
            "fall/non-fall skeleton keypoints, useful for pose/temporal branch",
            "CC0 / project-recorded source metadata",
            "downloaded_preexisting",
            "Already downloaded earlier; 16 RAR keypoint archives.",
        ),
        (
            "urfd_subset",
            DATASETS / "external_research_only" / "urfd",
            "RGB frame zips + CSV",
            "indoor fall and ADL; useful for research validation",
            "CC BY-NC-SA 4.0",
            "downloaded_research_only",
            "Research/non-commercial only; keep out of production-training mix unless license is cleared.",
        ),
    ]
    for name, path, modality, scene, lic, status, notes in existing:
        count, size = dir_stats(path)
        records.append(
            DatasetRecord(
                name=name,
                modality=modality,
                scene_coverage=scene,
                license=lic,
                status=status,
                source_url="see local .source.json / prior report",
                local_path=str(path),
                notes=notes,
                file_count=count,
                size_bytes=size,
            )
        )


def add_pending(records: list[DatasetRecord]) -> None:
    pending = [
        (
            "UP-Fall",
            "multimodal video + wearable + ambient sensors",
            "large multimodal fall/ADL benchmark; excellent for temporal fusion but huge",
            "academic/research, large download",
            "pending_manual_or_large_download",
            "https://sites.google.com/up.edu.mx/har-up/",
            "Often hundreds of GB. Need explicit storage budget before full download.",
        ),
        (
            "NTU RGB+D 120",
            "RGB + depth + IR + skeleton",
            "large ADL/action corpus; useful for night/IR hard negatives and fall-down class",
            "research license/application",
            "pending_application_or_large_download",
            "https://rose1.ntu.edu.sg/dataset/actionRecognition/",
            "Requires application/account and is very large.",
        ),
        (
            "MIPT",
            "thermal + depth + tracking boxes",
            "privacy-preserving tracking, AAL-adjacent; good for low-light/multi-person tracking",
            "non-commercial research",
            "pending_large_download",
            "https://zenodo.org/records/5585012",
            "Zenodo file is about 9.8GB; not auto-downloaded to avoid sudden storage pressure.",
        ),
        (
            "MDPI eHomeSeniors supplementary",
            "thermal/infrared CSV",
            "home elderly fall detection; low-light thermal CSV",
            "MDPI supplementary",
            "blocked_http_403",
            "https://www.mdpi.com/1424-8220/19/20/4565/s1",
            "MDPI blocked direct script access from this environment; browser/manual download needed.",
        ),
        (
            "Kaggle fall-detection-dataset",
            "images/video-derived frames",
            "broad fall situations; detector training",
            "Kaggle dataset terms",
            "pending_kaggle_credentials",
            "https://www.kaggle.com/datasets/uttejkumarkandagatla/fall-detection-dataset",
            "Requires Kaggle credentials/API token.",
        ),
        (
            "Roboflow fall-detection-ca3o8",
            "YOLO images/labels",
            "detector fall frames",
            "Roboflow terms/export token may be required",
            "pending_roboflow_access",
            "https://universe.roboflow.com/roboflow-universe-projects/fall-detection-ca3o8",
            "May require Roboflow export/API key.",
        ),
        (
            "Bilibili/YouTube scene videos",
            "public web videos",
            "bedside fall, caregiver assist, occlusion, corridor multi-person, elderly real scenes",
            "copyright varies",
            "candidate_urls_only_until_rights_cleared",
            "manual search list",
            "Do not mix into final training until license/permission is recorded.",
        ),
    ]
    for name, modality, scene, lic, status, url, notes in pending:
        records.append(
            DatasetRecord(
                name=name,
                modality=modality,
                scene_coverage=scene,
                license=lic,
                status=status,
                source_url=url,
                local_path=str(DATASETS / "external_restricted_pending" / name.replace(" ", "_")),
                notes=notes,
            )
        )


def write_reports(records: list[DatasetRecord]) -> None:
    csv_path = MANIFESTS / "additional_dataset_acquisition.v3.csv"
    json_path = REPORTS / "additional_dataset_acquisition.v3.json"
    md_path = REPORTS / "additional_dataset_acquisition.v3.md"

    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(records[0]).keys()))
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))

    json_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "records": [asdict(r) for r in records],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        "# Fall Detection V3 Additional Dataset Acquisition",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary",
        "",
        "| Dataset | Status | Modality | Scene Coverage | Local Path |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in records:
        lines.append(
            f"| {r.name} | {r.status} | {r.modality} | {r.scene_coverage} | `{r.local_path}` |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `external_authorized` can be used for training after QA.",
            "- `external_research_only` is for experiments/research validation unless rights are cleared.",
            "- `external_restricted_pending` records useful sources that need credentials, storage approval, or license confirmation.",
            "- Web videos from Bilibili/YouTube should be kept as candidate URLs until permission/license is clear.",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    records: list[DatasetRecord] = []
    copy_existing_inventory(records)

    hf_jobs = [
        dict(
            repo_id="Simuletic/CCTV_Incident_Dataset_Fall_Lying_Down_Detection",
            dest=DATASETS / "external_authorized" / "simuletic_cctv_fall_pose",
            allow_patterns=None,
            license_name="CC BY 4.0",
            modality="synthetic CCTV images + YOLO pose labels",
            scene_coverage="overhead CCTV fall/lying/standing, privacy-safe pose hard cases",
            notes="Good for pose detector and fallen/standing posture separation; synthetic sample.",
        ),
        dict(
            repo_id="seanphan/le2i-sentinel-frames",
            dest=DATASETS / "external_research_only" / "le2i_sentinel_frames",
            allow_patterns=None,
            license_name="dataset card / source terms need final review",
            modality="RGB image frames",
            scene_coverage="classic Le2i fall/ADL frame benchmark for detector smoke tests",
            notes="Use as research/validation until source rights are fully verified.",
        ),
        dict(
            repo_id="DeZan/fall-detection",
            dest=DATASETS / "external_authorized" / "dezan_fall_detection_images",
            allow_patterns=None,
            license_name="MIT",
            modality="images + labels/zip",
            scene_coverage="small fall image dataset for detector augmentation",
            notes="Small MIT-licensed image dataset; inspect labels before mixing.",
        ),
        dict(
            repo_id="simplexsigil2/omnifall",
            dest=DATASETS / "external_research_only" / "omnifall_sensor",
            allow_patterns=None,
            license_name="dataset card/source terms need final review",
            modality="tabular/sensor data",
            scene_coverage="fall and ADL sensor sequences for temporal logic reference",
            notes="Useful for temporal patterns, not detector bbox training.",
        ),
        dict(
            repo_id="simplexsigil2/wanfall",
            dest=DATASETS / "external_research_only" / "wanfall_sensor",
            allow_patterns=None,
            license_name="dataset card/source terms need final review",
            modality="tabular/sensor labels",
            scene_coverage="fall/ADL temporal sensor examples",
            notes="Useful for temporal branch ideas, not detector bbox training.",
        ),
    ]

    for job in hf_jobs:
        try:
            records.append(download_hf_dataset(**job))
        except Exception as exc:  # noqa: BLE001
            records.append(
                DatasetRecord(
                    name=job["repo_id"].replace("/", "__"),
                    modality=job["modality"],
                    scene_coverage=job["scene_coverage"],
                    license=job["license_name"],
                    status="download_failed",
                    source_url=f"https://huggingface.co/datasets/{job['repo_id']}",
                    local_path=str(job["dest"]),
                    notes=f"{job['notes']} | error={exc!r}",
                )
            )

    # MDPI direct access is attempted and logged. If blocked, the pending row
    # below explains the manual action.
    records.append(
        try_download_url(
            name="ehomeseniors_mdpi_supplement_attempt",
            url="https://www.mdpi.com/1424-8220/19/20/4565/sensors-19-04565-s001.zip",
            dest_file=DATASETS / "external_authorized" / "ehomeseniors" / "raw" / "sensors-19-04565-s001.zip",
            license_name="MDPI supplementary / verify before production use",
            modality="infrared CSV zip",
            scene_coverage="home elderly low-light/thermal fall detection",
            notes="Direct script download attempt for eHomeSeniors supplementary files.",
        )
    )

    add_pending(records)
    write_reports(records)


if __name__ == "__main__":
    main()
