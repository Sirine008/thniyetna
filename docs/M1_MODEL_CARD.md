# M1 model card — `yolo26s-rdd2022-dronefreak`

Road-damage detector used by the M1 perception worker since 2026-10-23. It is a **public pretrained model**:
we did not train it or re-measure its accuracy. Sections 3 and 4 (published metrics) come from the author's
model card. Sections 5 and 6 are our own measurements and observations.

## 1. Source and license

| Field | Value |
|---|---|
| Model | Ultralytics YOLO26s fine-tuned on RDD2022, by **dronefreak** |
| Page | https://huggingface.co/dronefreak/rdd2022-yolo26s |
| File | `best.pt` → `models/road-damage-yolo26s.pt` (not versioned; `python scripts/download_m1_model.py`) |
| Size / SHA-256 | 20,316,485 bytes (19.38 MiB) / `b4e45aaacc0a1e14368ddadabeec3edb8694b77a91df163ea46fdb904f29e8c7` |
| License (weights) | **AGPL-3.0** |
| Training images | RDD2022 (Arya et al., arXiv:2209.08538), CC BY-SA 4.0 |
| Load check | `scripts/check_m1_model.py`: task `detect`, 4 classes, all keys of `RDD_CLASS_MAP` |

AGPL-3.0 note: AGPL obligations also apply when the model is offered to users over a network (here, through
the citizen and inspection uploads). The source of the service that uses it must be made available to those
users under AGPL terms. Check this before any public deployment. It is fine for the academic prototype.

## 2. Classes

Model order: `longitudinal_crack`, `transverse_crack`, `alligator_crack`, `pothole` (RDD2022 D00, D10, D20, D40).
They map 1:1 to the THNIYETNA `defect_type` values (`ml/perception/detector.py`).

## 3. Training (as published by the author)

Base YOLO26s, 640 px, batch 16, 50 epochs (early-stopping patience 10), Adam, lr 0.001, seed 0, trained with
DetectionBench. Split: **70/15/15 of the publicly labelled RDD2022 images, chosen by the author**. It is not
the official RDD2022 test set, and the countries are mixed (Japan, India, Czech Republic, Norway, USA, China).
10.0 M parameters, 22.8 GFLOPs at 640 px.

## 4. Published metrics — reported by dronefreak, not re-measured by us

Test slice of the author's own split (above).

| | mAP@50 | mAP@50-95 |
|---|---|---|
| **All classes** | **61.27 %** | **33.3 %** |
| longitudinal_crack | 54.67 % | 29.67 % |
| transverse_crack | 53.81 % | 25.94 % |
| alligator_crack | 62.08 % | 32.12 % |
| pothole | 74.52 % | 45.48 % |

Precision 64.42 %, recall 57.13 %, F1 60.55 %. Because the split differs, these numbers are not directly
comparable with RDD2022 challenge results.

## 5. Our CPU latency

`python -m perception.benchmark --source /data/m1/pilot` inside the `perception-worker` image (2026-10-23),
on a laptop Intel Core i7-1255U (12 logical CPUs, 31.7 GB RAM). Docker Desktop/WSL2, torch 2.14.1+cpu,
6 torch threads. Settings imgsz 640, conf 0.25, iou 0.50. Each time covers one `predict` call
(JPEG decode + resize + inference + NMS), 1 warm-up image not timed.

| Images | Total | Mean | p50 | p95 | Throughput |
|---|---|---|---|---|---|
| 14 | 2.97 s | 212.4 ms | **140.3 ms** | 517.5 ms | **4.71 img/s** |

The first two timed images (788.8 ms and 287.3 ms) are still warming up, so p50 is the most representative
figure. The worker processed the end-to-end citizen photo in 1.9 s (job claimed → completed, including the
first model load in the container). Video at the default 5 FPS sampling would therefore run at about real time on
this CPU, with no margin for larger frames.

## 6. Pilot observations (14 local photos, `data/m1/pilot/`, not versioned)

The pilot set is **unlabelled**, so no mAP can be computed. The "what the photo shows" column is a visual reading
by Claude Code on 2026-10-23, to be reviewed. Most photos are web/stock-style close-ups, `road1` is a 3D render,
and none is known to come from Bizerte. Annotated outputs: `data/m1/pilot_out/`.

| Image | What the photo shows | Detections (conf 0.25) | class · conf · severity proxy |
|---|---|---|---|
| road1 | 3D render, road with faint surface cracking | 1 | alligator_crack · 0.32 · 0.55 |
| road2 | Pothole with broken slabs and muddy water | 0 | — |
| road3 | Large water-filled pothole + crazed asphalt | 1 | alligator_crack · 0.354 · 0.73 |
| road4 | Water-filled pothole | 0 | — |
| road5 | Two water-filled potholes | 0 | — |
| road6 | Gravel-filled potholes | 0 | — |
| road7 | Rural road, several large potholes | 0 | — |
| road8 | Meandering crack, close-up | 2 | longitudinal_crack · 0.385 · 0.60 ; 0.385 · 0.49 |
| road9 | Intact rural road | 1 | transverse_crack · 0.267 · 0.38 (false positive, thin box on the bottom edge) |
| road10 | Intact rural road | 0 | — |
| road11 | Water-filled pothole (same stock photo as the 14/10 test jobs) | 0 | — |
| road12 | Asphalt texture close-up | 0 | — |
| road13 | Fresh asphalt driveway | 0 | — |
| road14 | Fresh asphalt driveway | 0 | — |

Summary (qualitative):
- **Potholes: 0 / 7 detected as `pothole`.** road3 is flagged, but as alligator_crack (the box covers the pothole
  and the cracked area next to it). A diagnostic re-run at conf 0.05 gave at most 0.07 for `pothole` on these 7
  photos, at 640 or 1024 px. The only `pothole` above 0.25 at 1024 px was on road14, a fresh driveway (false positive).
  Lowering the threshold or raising imgsz does not fix this.
- Cracks: road8 is detected (longitudinal, 2 boxes).
- Intact roads: 4 / 5 without detections; 1 low-confidence false positive (road9, 0.267).
- Every confidence is below 0.40, so the model is uncertain on this domain.

Likely cause: **domain shift**. RDD2022 images are taken from a vehicle looking down the road ahead (smartphone
on the dashboard, motorbike or drone), with damage seen at a distance. The pilot photos are pedestrian close-ups,
often with water in the hole. This says nothing yet about Tunisian dashcam footage: a proper pilot needs Bizerte
photos taken from a vehicle, labelled by a person.

## 7. End-to-end check (2026-10-23)

Real API only. A citizen registered, uploaded road3.jpg and submitted a `road_damage` complaint at the midpoint
of OSM-100663969 (RN7 Tunis–Tabarka). The worker completed the job in 1.9 s and created 1 observation + 1 event
`alligator_crack` (conf 0.354, severity 0.7264) on that segment. `equipment.supervisor` validated it. The M2 pass
then moved the segment from low / P3 / no_observed_defect (0.1837) to **medium / P2 / poor (0.3940)**. The
intervention sheet included the defect, but its 3 advice sections came back `uncited` (llama3.2:3b).
This check exposed an M2 issue, since fixed (`segment_cutoff` in `ml/prediction/jobs/score.py`): an event from the same day was
ignored until the next day's pass. See `docs/STATUS.md`.

## 8. Limits

- **Not trained on Tunisian roads.** No Tunisian images in RDD2022; Tunisian surfaces, markings, lighting and
  repair styles are unseen. No local accuracy has been measured.
- **Severity is a visual proxy** (`ml/perception/severity.py`): class prior + box area + confidence. It is not a
  depth or width measurement and must not be presented as engineering severity.
- The **published metrics are the author's**, on the author's own split, and have not been reproduced here.
- Pothole recall on close-up citizen photos is very poor (section 6). Citizen photos taken from a pedestrian
  viewpoint should be treated as weak evidence. A supervisor's validation remains the gate (M2 gives unvalidated
  events a 0.6 weight).
- Thresholds conf 0.25 / iou 0.50 were not tuned for this domain.
- AGPL-3.0 weights (section 1).

## 9. Next steps

1. Collect about 100–200 Bizerte images from a vehicle (dashcam/phone) and label them. Report mAP on this local set,
   kept separate from any training.
2. If pothole recall stays low: fine-tune on RDD2022 plus local images (`ml/perception/train_detector.py`) and
   compare with this checkpoint, using the same benchmark.
