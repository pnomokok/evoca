# Evoca web client

React + Vite app with two views: the simulated Alexa+ device screen for the elder, and the family panel.
It talks to the backend REST API through the Vite dev server, which proxies `/api` to `http://localhost:8080`.
Set `VITE_API_BASE_URL` (for example in `.env.local`) only to call a backend directly; its CORS settings allow that.
Start the servers first (`python scripts/run_demo.py` from the repo root), then: `npm install && npm run dev`.
Open http://localhost:5173 (Node 20.19+ or 22.12+).
