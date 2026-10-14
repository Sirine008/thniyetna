# RDD2022 local data

Place an extracted, team-approved RDD2022 copy under this folder or another local
path. The raw dataset is intentionally not committed to Git.

Convert it with:

```bash
python ml/perception/prepare_rdd2022.py --src data/external/rdd2022/RDD2022 --out data/processed/rdd2022-yolo
```
