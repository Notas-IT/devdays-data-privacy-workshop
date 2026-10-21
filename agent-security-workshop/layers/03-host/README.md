# 03 — Host

New boundary: Remove the actual host README bind mount from the agent.

Cumulative layers: Agent process, Files, Host.

## Run From The Repository Root

```bash
python3 agent-security-workshop/layers.py up 3
python3 agent-security-workshop/layers.py test 3
python3 agent-security-workshop/layers.py down 3
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

Remove host-file exposure without changing the process or filesystem protections.

## What Remains Exposed

Direct SQL remains possible. Host credentials, SSH keys, Docker socket and host PID access are deliberately never supplied in any stage.

See [TASK.md](TASK.md) for the learner task and [the stage overview](../../LAYERS.md)
for the full progression. Tests deliberately confirm remaining exposure as
well as protections. A passing early stage does not mean the data is secure.
