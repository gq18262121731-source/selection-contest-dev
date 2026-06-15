# Fall Detection

YOLO-based fall detection workspace for collecting public datasets, building training manifests, and training a real-time fall detection pipeline on Windows with the local GPU.

Current strategy:

- Use public fall datasets to cover real falls, post-fall lying states, and hard negatives.
- Use YOLO pose or person detection as the front-end perception model.
- Train a temporal classifier on top of pose sequences for event-level fall detection.
- Optionally train a static posture model from `falldataset.com` as an auxiliary signal.

Quick start:

```powershell
C:\Users\YANG\.conda\envs\AI\python.exe .\scripts\download_public_datasets.py --datasets omnifall_labels wanfall_splits urfd gmdcsa24 fallpose --extract
```

Main folders:

- `data_public`: raw public downloads and label packs
- `data_processed`: extracted features, manifests, and prepared training sets
- `weights`: trained models and exported checkpoints
- `scripts`: download, preparation, training, and inference scripts
- `docs`: dataset notes and training decisions

Optimized workflow entrypoints:

- Model registry: `configs/model_registry.yaml`
- Alert rules: `configs/alert_rules.yaml`
- Injury grading rules: `configs/injury_rules.yaml`
- Unified inference: `scripts/infer_fall.py`
- YOLO fall detector training: `scripts/train_yolo_fall_detector.py`
- YOLO detection evaluation: `scripts/evaluate_yolo_detect.py`
- Full optimization notes: `docs/optimized_system_plan.md`
- Current model system guide: `docs/current_model_system_guide.md`
- GitHub upload guide: `docs/github-upload-guide.md`

Important note:

Some public fall datasets are released for research or non-commercial use only. Before using a trained model in a production or commercial setting, re-check the original dataset license for every source and prioritize collecting site-specific footage from the real deployment environment.
