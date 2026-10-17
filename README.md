# evoca

## Run it locally

Recommended: start the whole demo with one command (Windows, macOS, Linux):

```
python scripts/run_demo.py
```

It seeds `data/demo.db` if it is missing, starts the MCP server (port 8000) and the backend (port 8080) with
`EVOCA_DB_PATH=data/demo.db` and `EVOCA_DEMO_MODE=1` for both, prints the URLs, and stops both on Ctrl+C.
Demo mode turns on the demo controls (`/api/demo/clock`, `/api/demo/advance`, `/api/demo/reset`; see
`docs/api-samples/README.md`). Reset works only on `data/demo.db`.

Start the web client in a second terminal: `cd web && npm run dev` (http://localhost:5173).
The servers need AWS credentials for Bedrock and Polly.

Running the servers by hand (`uvicorn mcp_server.server:app --port 8000` and `uvicorn server.app:app --port 8080`)
uses `data/evoca.db` and no demo controls.
