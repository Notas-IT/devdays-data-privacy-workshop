# 01 — Agent process

New boundary: Non-root UID 10001, all capabilities dropped, and no-new-privileges.

Cumulative layers: Agent process.

## Run From The Repository Root

```bash
python3 agent-security-workshop/layers.py up 1
python3 agent-security-workshop/layers.py test 1
python3 agent-security-workshop/layers.py down 1
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

Constrain the agent process while keeping the same direct SQL task working.

## What Remains Exposed

The writable container filesystem, host README mount, direct SQL access and individual salary visibility remain.

See [TASK.md](TASK.md) for the learner task and [the stage overview](../../LAYERS.md)
for the full progression. Tests deliberately confirm remaining exposure as
well as protections. A passing early stage does not mean the data is secure.
