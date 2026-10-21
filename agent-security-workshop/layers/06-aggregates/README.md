# 06 — Aggregates

New boundary: Revoke the row function; expose a fixed salary summary and suppress cohorts below three.

Cumulative layers: Agent process, Files, Host, Network, Database, Aggregates.

## Run From The Repository Root

```bash
python3 agent-security-workshop/layers.py up 6
python3 agent-security-workshop/layers.py test 6
python3 agent-security-workshop/layers.py down 6
```

This folder has a complete Compose configuration and `security.sql`, and uses
its own database, networks and generated credentials. It does not require a
previous stage to be running. Shared implementation is in `../../layer_runtime`.

After starting, run from this folder:

```bash
docker compose exec -T agent python /opt/agent/client.py api /companies/1/salary-summary
```

## What This Stage Proves

Allow an average while denying the individual-salaries endpoint and the one-person cohort.

## What Remains Exposed

Anonymous callers can still request another company average. Minimum group size is not an anonymity guarantee.

See [TASK.md](TASK.md) for the learner task and [the stage overview](../../LAYERS.md)
for the full progression. Tests deliberately confirm remaining exposure as
well as protections. A passing early stage does not mean the data is secure.
