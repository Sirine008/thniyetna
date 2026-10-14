# M1 model checkpoints

Place the selected validated road-damage checkpoint here as:

`road-damage-yolo26n.pt`

The repository intentionally does **not** ship fabricated weights or metrics.
Train on RDD2022 with `ml/perception/train_detector.py`, evaluate the candidates,
and copy the selected `best.pt` here. The default comparison is YOLO26n,
YOLO26s and YOLO11n.
