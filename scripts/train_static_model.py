from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import get_settings
from backend.ml.trainer import StaticHealthTrainer, TrainingError


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the static health monitoring model.")
    parser.add_argument("--data", default=None, help="Path to the Excel data file.")
    parser.add_argument("--sheet", default=None, help="Sheet name or sheet index.")
    args = parser.parse_args()

    settings = get_settings()
    trainer = StaticHealthTrainer(settings=settings)
    try:
        summary = trainer.train_from_excel(path=args.data, sheet_name=args.sheet)
    except TrainingError as exc:
        print(f"[train_static_model] failed: {exc}")
        return 1

    print("[train_static_model] success")
    print(f"train_size={summary.train_size}")
    print(f"val_size={summary.val_size}")
    print(f"best_val_loss={summary.best_val_loss:.6f}")
    print(f"feature_count={summary.feature_count}")
    print(f"class_weights={summary.class_weights}")
    print(f"artifacts_dir={settings.static_model_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
