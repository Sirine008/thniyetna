# THNIYETNA frontend

React/Vite frontend for citizen, driver, Equipment and Transport workflows.

The browser talks to `/api/*`; Nginx proxies those requests to the FastAPI
`api` service. Authentication uses the shared `/auth/login` and
`/auth/register` backend endpoints and stores the JWT in local storage.

Run through Docker from the repository root:

```bash
docker compose up -d --build
```
