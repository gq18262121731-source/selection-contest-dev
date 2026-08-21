from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SKELETON_ROOT = ROOT / "data_public" / "fall_database" / "skeleton_only"
PROCESSED = ROOT / "data_processed"


SCENARIOS = {
    11: ("backward_fall_end_sitting", 1),
    12: ("backward_fall_end_lying", 1),
    13: ("backward_fall_end_lateral", 1),
    14: ("backward_fall_with_recovery", 0),
    21: ("forward_fall_arm_protection", 1),
    22: ("forward_fall_end_lying_flat", 1),
    23: ("forward_fall_rotation_lateral", 1),
    24: ("forward_fall_with_recovery", 0),
    31: ("lateral_fall_end_lying", 1),
    32: ("lateral_fall_with_recovery", 0),
    41: ("neutral_sit_stand", 0),
    42: ("neutral_lie_stand", 0),
    43: ("neutral_walking", 0),
    44: ("neutral_bend_pick_rise", 0),
    45: ("neutral_cough_sneeze", 0),
    51: ("additional_sit_then_fall", 1),
    52: ("additional_fall_out_of_bed", 1),
    53: ("additional_fall_into_camera", 1),
}


def assign_split(person_name: str) -> str:
    if person_name.endswith("a"):
        return "train"
    if person_name == "person1b":
        return "val"
    return "test"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a manifest for FallDatabase skeleton sequences.")
    parser.add_argument("--output", default=str(PROCESSED / "falldb_manifest.csv"))
    args = parser.parse_args()

    rows = []
    for skeleton_path in sorted(SKELETON_ROOT.rglob("skeleton.txt")):
        scenario_dir = skeleton_path.parent
        person_dir = scenario_dir.parent
        scenario_id = int(scenario_dir.name)
        if scenario_id not in SCENARIOS:
            continue
        scenario_name, binary_label = SCENARIOS[scenario_id]
        rows.append(
            {
                "dataset": "falldb",
                "split": assign_split(person_dir.name),
                "person": person_dir.name,
                "scenario_id": scenario_id,
                "scenario_name": scenario_name,
                "binary_label": binary_label,
                "sequence_path": str(skeleton_path),
            }
        )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_path, index=False)
    print(f"[saved] {out_path}")
    print(df.groupby(['split', 'binary_label']).size().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
