# 00 — Plain database

New boundary: No application security layer yet.

Cumulative layers: None: baseline only.

## Run From The Repository Root

```bash
python3 agent-security-workshop/layers.py up 0
python3 agent-security-workshop/layers.py test 0
python3 agent-security-workshop/layers.py down 0
```

This folder has a complete Compose configuration and `security.sql`, and uses
its own database, networks and generated credentials. It does not require a
previous stage to be running. Shared implementation is in `../../layer_runtime`.

After starting, run from this folder:

```bash
docker compose exec -T agent python /opt/agent/client.py sql \
  'SELECT company_id, avg(salary_eur) FROM lab_private.employee_salaries GROUP BY company_id;'
```

## What This Stage Proves

Read the synthetic salary table directly using the agent database credential.

## What Remains Exposed

The process runs as root, the container filesystem is writable, a host README is mounted, and direct SQL exposes individual salaries.

See [TASK.md](TASK.md) for the learner task and [the stage overview](../../LAYERS.md)
for the full progression. Tests deliberately confirm remaining exposure as
well as protections. A passing early stage does not mean the data is secure.
