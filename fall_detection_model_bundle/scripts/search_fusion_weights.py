from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch

from evaluate_combined_monitor import score_metrics
from train_temporal_gru import GRUFallNet, prepare_splits as prepare_gru
from train_temporal_tcn_transformer import HybridTCNTransformer, prepare_splits as prepare_hybrid
from train_temporal_semantic_mix import SemanticTemporalNet, prepare_splits as prepare_semantic


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data_processed"
WEIGHTS = ROOT / "weights"


def load_gru(path: Path):
    ckpt = torch.load(path, map_location="cpu")
    model = GRUFallNet(ckpt["input_dim"])
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    return model


def load_hybrid(path: Path):
    ckpt = torch.load(path, map_location="cpu")
    model = HybridTCNTransformer(ckpt["input_dim"])
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    return model


def load_semantic(path: Path):
    ckpt = torch.load(path, map_location="cpu")
    model = SemanticTemporalNet(ckpt["input_dim"])
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    return model


def main() -> int:
    parser = argparse.ArgumentParser(description="Search fusion weights over GRU, hybrid, semantic, and posture branches.")
    parser.add_argument("--manifest", default=str(PROCESSED / "video_manifest.csv"))
    parser.add_argument("--falldb-manifest", default=str(PROCESSED / "falldb_manifest.csv"))
    parser.add_argument("--pose-cache-dir", default=str(PROCESSED / "pose_cache"))
    parser.add_argument("--risk-cache-dir", default=str(PROCESSED / "posture_risk_cache"))
    parser.add_argument("--gru-weights", default=str(WEIGHTS / "gru_pose_fall_v1.pt"))
    parser.add_argument("--hybrid-weights", default=str(WEIGHTS / "hybrid_tcn_transformer_v2_matchgru.pt"))
    parser.add_argument("--semantic-weights", default=str(WEIGHTS / "semantic_mix_falldb_v1.pt"))
    args = parser.parse_args()

    manifest = Path(args.manifest)
    falldb_manifest = Path(args.falldb_manifest)
    pose_cache = Path(args.pose_cache_dir)
    risk_cache = Path(args.risk_cache_dir)

    sp_gru = prepare_gru(manifest, pose_cache, 24, 6)
    sp_hybrid = prepare_hybrid(manifest, pose_cache, risk_cache, 24, 6, 0.5, 2.2)
    sp_sem = prepare_semantic(manifest, falldb_manifest, pose_cache, 24, 6, 0.5, 2.2)

    labels = np.array(sp_gru.test_y)
    rgb_count = len(sp_gru.test_x)
    sem_x = sp_sem.test_x[:rgb_count]

    gru_model = load_gru(Path(args.gru_weights))
    hybrid_model = load_hybrid(Path(args.hybrid_weights))
    semantic_model = load_semantic(Path(args.semantic_weights))

    with torch.no_grad():
        gru_probs = np.array([torch.sigmoid(gru_model(torch.from_numpy(x).unsqueeze(0))).item() for x in sp_gru.test_x])
        hybrid_probs = np.array([torch.sigmoid(hybrid_model(torch.from_numpy(x).unsqueeze(0))).item() for x in sp_hybrid.test_x])
        semantic_probs = np.array([torch.sigmoid(semantic_model(torch.from_numpy(x).unsqueeze(0))).item() for x in sem_x])
    posture_probs = np.array([float(x[:, -3].mean()) for x in sp_hybrid.test_x])

    best = None
    for wg in np.arange(0.15, 0.61, 0.05):
        for wh in np.arange(0.15, 0.61, 0.05):
            for ws in np.arange(0.0, 0.31, 0.05):
                wp = 1.0 - wg - wh - ws
                if wp < 0 or wp > 0.35:
                    continue
                scores = gru_probs * wg + hybrid_probs * wh + semantic_probs * ws + posture_probs * wp
                for thr in np.arange(0.3, 0.91, 0.05):
                    metrics = score_metrics(labels, scores, float(thr))
                    if best is None or metrics["f1"] > best["f1"]:
                        best = {
                            "gru_weight": round(float(wg), 2),
                            "hybrid_weight": round(float(wh), 2),
                            "semantic_weight": round(float(ws), 2),
                            "posture_weight": round(float(wp), 2),
                            **metrics,
                        }
    print(best)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
