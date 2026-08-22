# Anti-Bagu deployment

The internal beta runs as a modular monolith on one Ubuntu host:

- Nginx serves the React build and terminates HTTPS/WSS.
- One Uvicorn worker owns Agent, mobile, and task-runtime in-memory connections.
- PostgreSQL stores users, sessions, task metadata, events, and platform audits.
- `/var/lib/anti-bagu` stores per-task JSONL logs and raw dual-channel PCM audio.
- A daily local backup keeps PostgreSQL, task events, logs, and audio for seven days.
- Certbot renews the six-day Let's Encrypt IP certificate twice daily.

Server paths:

```text
/opt/anti-bagu                         symlink to the active immutable release
/opt/anti-bagu-deploy/repository       server-side clone of the GitHub repository
/opt/anti-bagu-deploy/releases/<sha>   application releases identified by commit
/opt/anti-bagu-deploy/artifacts        web and macOS Agent build artifacts
/opt/anti-bagu-deploy/legacy           pre-Git deployment kept for recovery
/etc/anti-bagu/anti-bagu.env          root-only runtime configuration
/var/lib/anti-bagu/logs                daily platform logs
/var/lib/anti-bagu/storage/tasks       task events and audio
```

The backend intentionally runs with one worker. Agent and mobile WebSocket state is
in memory for the beta; adding workers requires Redis-backed connection routing.

Initial host setup:

1. Install Git, Python, Nginx, PostgreSQL, and Certbot 5.4+. Node.js is not
   required on the server.
2. Create the `antibagu` system user and PostgreSQL database.
3. Install the systemd and Nginx configuration from this directory.
4. Start with the HTTP Nginx config so ACME HTTP-01 can validate the IP.
5. Request the short-lived IP certificate with Certbot.
6. Switch to the HTTPS config and enable both systemd timers/services.

Release workflow:

1. Commit and push all changes. The deploy script refuses a dirty worktree or a
   commit that is not the current remote branch head.
2. Run `deploy/scripts/deploy-release.sh anti-bagu` from the developer Mac.
3. The Mac builds the React application and macOS Agent. Only the generated web
   artifact is uploaded; application source is never copied from the worktree.
4. The server fetches the exact commit from GitHub and exports it into
   `/opt/anti-bagu-deploy/releases/<sha>`.
5. The server verifies the artifact checksum, creates the release-local Python
   environment, and runs `alembic upgrade head`.
6. `/opt/anti-bagu` is atomically switched to the new release. A failed service
   start or health check automatically restores the previous target.

To switch back to an already deployed commit:

```bash
deploy/scripts/rollback-release.sh anti-bagu <full-40-character-commit>
```

Rollback changes the application release only. Database migrations are not
automatically downgraded, so schema changes must remain backward compatible.

Never copy `.env.local` to the server. User model keys arrive only over WSS during
task preflight and remain in the task runtime memory until the process or task ends.
