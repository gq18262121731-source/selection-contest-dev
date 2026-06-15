from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = ROOT / "data_processed" / "video_manifest.csv"
DEFAULT_PRIVATE = ROOT / "data_processed" / "private_scene_manifest.csv"
DEFAULT_OUTPUT = ROOT / "data_processed" / "video_manifest_adapted.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge the public video manifest with the private scene manifest.")
    parser.add_argument("--base", default=str(DEFAULT_BASE))
    parser.add_argument("--private", default=str(DEFAULT_PRIVATE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    base = pd.read_csv(args.base)
    private = pd.read_csv(args.private)
    merged = pd.concat([base, private], ignore_index=True)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False)
    print(f"[saved] {out_path}")
    print(merged.groupby(["dataset", "split"]).size().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
