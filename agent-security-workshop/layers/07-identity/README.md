# 07 — Identity

New boundary: Authenticate a random per-actor token and derive company membership inside the protected summary function.

Cumulative layers: Agent process, Files, Host, Network, Database, Aggregates, Identity.

## Run From The Repository Root

```bash
python3 agent-security-workshop/layers.py up 7
python3 agent-security-workshop/layers.py test 7
python3 agent-security-workshop/layers.py down 7
```

This folder has a complete Compose configuration and `security.sql`, and uses
its own database, networks and generated credentials. It does not require a
previous stage to be running. Shared implementation is in `../../layer_runtime`.

After starting, run from this folder:

```bash
docker compose exec -T agent python /opt/agent/client.py api /companies/1/salary-summary
```

## What This Stage Proves

Keep the allowed company average working while rejecting anonymous requests and another company.

## What Remains Exposed

Requests are still not durably audited. A correct authorization decision alone does not leave a record.

See [TASK.md](TASK.md) for the learner task and [the stage overview](../../LAYERS.md)
for the full progression. Tests deliberately confirm remaining exposure as
well as protections. A passing early stage does not mean the data is secure.
