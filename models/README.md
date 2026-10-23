# M1 model checkpoints

The M1 worker loads `models/${M1_MODEL_FILE}` (mounted read-only at `/models` in `perception-worker`).

Current checkpoint: `road-damage-yolo26s.pt`, a **public pretrained** YOLO26s fine-tuned on RDD2022 by
dronefreak (Hugging Face, AGPL-3.0). We did not train it. Fetch it with:

```
python scripts/download_m1_model.py
```

The weights are not versioned (`*.pt` is gitignored). The script records size, SHA-256, source and license
below. Model card: `docs/M1_MODEL_CARD.md`.

Training our own checkpoint (`ml/perception/train_detector.py`; YOLO26n / YOLO26s / YOLO11n comparison on
RDD2022, then a Tunisian pilot set) is still a future option. The repository does not ship fabricated
weights or metrics.

<!-- m1-attribution:begin -->
## Attribution — road-damage-yolo26s.pt

| Field | Value |
|---|---|
| File | `models/road-damage-yolo26s.pt` (not versioned) |
| Source | https://huggingface.co/dronefreak/rdd2022-yolo26s/resolve/main/best.pt |
| Model page | https://huggingface.co/dronefreak/rdd2022-yolo26s |
| Author | dronefreak (Hugging Face) |
| Architecture | Ultralytics YOLO26s, fine-tuned on RDD2022 (4 classes) |
| License (weights) | AGPL-3.0 |
| Training images | RDD2022, CC BY-SA 4.0 |
| Size | 20316485 bytes (19.38 MiB) |
| SHA-256 | `b4e45aaacc0a1e14368ddadabeec3edb8694b77a91df163ea46fdb904f29e8c7` |
| Recorded | 2026-10-23 by `scripts/download_m1_model.py` |

Citations: Arya et al., *RDD2022: A multi-national image dataset for automatic road damage detection*,
arXiv:2209.08538 (2022); Ultralytics YOLO26. Metrics and limits: `docs/M1_MODEL_CARD.md`.
<!-- m1-attribution:end -->
