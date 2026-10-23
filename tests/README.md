# Tests

Run repository checks from the project root:

```powershell
ml\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # once: API test dependencies
ml\.venv\Scripts\python.exe -m pytest -q
```

The CI workflow validates the repository contracts and `docker compose config`.
M1 pure unit tests remain under `ml/perception/tests`.
