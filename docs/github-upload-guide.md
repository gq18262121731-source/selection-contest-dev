# GitHub Upload Guide

This repository is intended to be the latest pullable system snapshot for new collaborators.

## Quick Start
- Clone repository root.
- Backend Python env: `health`
- Frontend: `frontend/vue-dashboard`
- Static health model artifacts are generated locally and are not committed under `data/`.

## Important Local-Only Assets
Some large datasets, generated runtime outputs, local databases, and external bundles are intentionally not committed.
See:
- `F:\health（5-12test）\UPLOAD_AND_ARCHIVE_GUIDE.md`
- `F:\health（5-12test）\upload_constraints.json`

## Environment Notes
- Main backend should use `health` conda env.
- `.env.example` now reflects `health` defaults.
- `MODEL_DEVICE=cpu` is the safe default on this machine because current local GPU + torch build is not compatible.

## Known Risks
- `qianfan` and `tenacity` currently have a pip metadata conflict.
- Some model-tuning / dataset-export subflows depend on packages that are not part of the safest backend runtime path.
- Previous remote LFS pointers were incomplete; if large manual bundles are needed, keep them outside Git or repair LFS storage first.
