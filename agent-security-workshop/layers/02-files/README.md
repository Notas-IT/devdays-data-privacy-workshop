# 02 — Files

New boundary: Read-only root filesystem with temporary scratch space and an ephemeral home.

Cumulative layers: Agent process, Files.

## Run From The Repository Root

```bash
python3 agent-security-workshop/layers.py up 2
python3 agent-security-workshop/layers.py test 2
python3 agent-security-workshop/layers.py down 2
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

Block writes to /workspace while allowing temporary work under /tmp.

## What Remains Exposed

The read-only host README is still visible; direct SQL and individual salary access remain.

See [TASK.md](TASK.md) for the learner task and [the stage overview](../../LAYERS.md)
for the full progression. Tests deliberately confirm remaining exposure as
well as protections. A passing early stage does not mean the data is secure.
