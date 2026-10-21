# 08 — Audit

New boundary: Commit append-only audit events before returning data; fail closed when audit insertion fails.

Cumulative layers: Agent process, Files, Host, Network, Database, Aggregates, Identity, Audit.

## Run From The Repository Root

```bash
python3 agent-security-workshop/layers.py up 8
python3 agent-security-workshop/layers.py test 8
python3 agent-security-workshop/layers.py down 8
```

This folder has a complete Compose configuration and `security.sql`, and uses
its own database, networks and generated credentials. It does not require a
previous stage to be running. Shared implementation is in `../../layer_runtime`.

After starting, run from this folder:

```bash
docker compose exec -T agent python /opt/agent/client.py api /companies/1/salary-summary
```

## What This Stage Proves

Record allowed and denied requests and withhold the average during a real audit-write failure.

## What Remains Exposed

The host, Docker administrator, presenter and gateway implementation remain trusted. This is a local synthetic lab, not proof of complete security.

See [TASK.md](TASK.md) for the learner task and [the stage overview](../../LAYERS.md)
for the full progression. Tests deliberately confirm remaining exposure as
well as protections. A passing early stage does not mean the data is secure.
