# Praxiom MCP

External ChatGPT/MCP integration boundary for Praxiom.

Current Phase B surface is intentionally read-only:

- `praxiom_status`
- `praxiom_observe`

The server does **not** expose `Runtime.execute` or any other raw device
mutation path. Future write tools must enter through the existing
`RunSession -> SkillExecutor -> ExecutionCoordinator -> Runtime` authority
chain.

Local endpoint: `http://127.0.0.1:17679/mcp`

Health endpoint: `http://127.0.0.1:17679/healthz`

On Windows the MCP entrypoint forces Uvicorn onto a `SelectorEventLoop`,
matching the pinned pymobiledevice3 CLI. Its Bonjour/RemotePairing stack is
unreliable on the default Proactor loop. The MCP virtualenv also uses Python
3.13+ on Windows so RemotePairing TCP tunnels use the standard-library TLS-PSK
API instead of the legacy native `sslpsk_pmd3` DLL path.

Setup and start on Windows:

```powershell
pwsh -NoProfile -File .\scripts\setup_praxiom_mcp.ps1
pwsh -NoProfile -File .\scripts\start_praxiom_mcp.ps1
```

Stop:

```powershell
pwsh -NoProfile -File .\scripts\stop_praxiom_mcp.ps1
```

If WDA is not already reachable, set `PRAXIOM_WDA_RUNNER_BUNDLE_ID` in the
process environment before starting the MCP. The value is deliberately not
stored in repository evidence.
