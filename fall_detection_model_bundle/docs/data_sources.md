# Public Data Sources

This project prioritizes datasets that are accessible from official pages or primary dataset repositories.

## Automated now

| Dataset | Type | Size | Source | Notes |
|---|---|---:|---|---|
| UR Fall Detection (URFD) | RGB fall / ADL videos | ~0.07 GB | https://fenix.ur.edu.pl/~mkepski/ds/uf.html | Small, fast to process, good bootstrap set |
| GMDCSA24 | RGB videos | ~0.98 GB | https://zenodo.org/records/11216408 | Useful supervised video corpus |
| Fall Pose Dataset | RGB image sequences with posture labels | ~7.6 GB | https://falldataset.com/ | Strong for static posture hard negatives |
| OmniFall labels | Unified public labels | small | https://huggingface.co/datasets/simplexsigil2/omnifall | Harmonized labels across multiple fall datasets |
| WanFall splits | Cross-subject / cross-view splits | small | https://huggingface.co/datasets/simplexsigil2/wanfall | Helpful for reproducible evaluation |

## Indexed but not fully automated yet

| Dataset | Source | Status | Reason |
|---|---|---|---|
| UP-Fall | https://sites.google.com/up.edu.mx/har-up/ | Manual / selective | Large Google Drive distribution with many modality files |
| FallDatabase | https://zenodo.org/records/3886586 | Download-only | Distributed as RAR; extractor is not installed yet |
| EDF / OCCU | https://zenodo.org/records/15494102 | Deferred | Large RGB-D / depth-oriented packs; lower priority for first RGB YOLO build |
| Le2i | cited in OmniFall labels | Manual | Commonly redistributed with access restrictions or mirrors |

## Why multiple datasets matter

- `URFD` gives a quick bootstrap for pipeline verification.
- `GMDCSA24` adds more viewpoints and subjects.
- `Fall Pose Dataset` gives strong coverage for standing, sitting, lying, bending, crawling, and empty-room negatives.
- `OmniFall/WanFall` reduces label mismatch across public sources.

## Label harmonization idea

The posture image dataset uses six states:

1. `standing`
2. `sitting`
3. `lying`
4. `bending`
5. `crawling`
6. `other`

OmniFall provides richer video labels such as `fall`, `fallen`, `standing`, `sitting`, `lying`, `crawl`, `kneeling`, and `squatting`. We will keep those richer temporal labels for the sequence model and only collapse them when preparing an auxiliary static posture model.
