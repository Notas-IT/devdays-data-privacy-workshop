# 05 — Database

New boundary: Revoke direct salary SELECT; permit only the approved salary_rows function.

Cumulative layers: Agent process, Files, Host, Network, Database.

## Run From The Repository Root

```bash
python3 agent-security-workshop/layers.py up 5
python3 agent-security-workshop/layers.py test 5
python3 agent-security-workshop/layers.py down 5
```

This folder has a complete Compose configuration and `security.sql`, and uses
its own database, networks and generated credentials. It does not require a
previous stage to be running. Shared implementation is in `../../layer_runtime`.

After starting, run from this folder:

```bash
docker compose exec -T agent python /opt/agent/client.py api /companies/1/salary-summary
```

## What This Stage Proves

Make arbitrary table reads fail even when using the gateway database account.

## What Remains Exposed

Approved per-company individual rows remain readable. The caller can still choose any company because identity has not been added.

See [TASK.md](TASK.md) for the learner task and [the stage overview](../../LAYERS.md)
for the full progression. Tests deliberately confirm remaining exposure as
well as protections. A passing early stage does not mean the data is secure.
