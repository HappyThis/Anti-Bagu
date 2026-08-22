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
/opt/anti-bagu                         application release
/etc/anti-bagu/anti-bagu.env          root-only runtime configuration
/var/lib/anti-bagu/logs                daily platform logs
/var/lib/anti-bagu/storage/tasks       task events and audio
```

The backend intentionally runs with one worker. Agent and mobile WebSocket state is
in memory for the beta; adding workers requires Redis-backed connection routing.

Deployment order:

1. Install Python, Nginx, PostgreSQL, Node.js, Certbot 5.4+, and rsync.
2. Create the `antibagu` system user and PostgreSQL database.
3. Copy the release to `/opt/anti-bagu` and create the Python environment.
4. Build the web application and run `alembic upgrade head`.
5. Start with the HTTP Nginx config so ACME HTTP-01 can validate the IP.
6. Request the short-lived IP certificate with Certbot.
7. Switch to the HTTPS config and enable both systemd timers/services.

Never copy `.env.local` to the server. User model keys arrive only over WSS during
task preflight and remain in the task runtime memory until the process or task ends.
