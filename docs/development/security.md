# Security

See [SECURITY.md](https://github.com/Cepat-Kilat-Teknologi/dawos-agent/blob/main/SECURITY.md) for the full security policy.

## Key Security Features

- **API-key authentication** on all endpoints (except `/health`)
- **Systemd sandboxing** (`ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`)
- **Least-privilege sudo** limited to 6 commands: `nft`, `ip`, `tc`, `vtysh`, `sysctl`, `tee`
- **No shell=True** with untrusted input (list-form subprocess args only)
- **No eval/exec** anywhere in the codebase
