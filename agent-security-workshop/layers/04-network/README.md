# 04 — Network

New boundary: Detach the database from the agent network, remove agent SQL credentials and introduce the gateway.

Cumulative layers: Agent process, Files, Host, Network.

## Run From The Repository Root

```bash
python3 agent-security-workshop/layers.py up 4
python3 agent-security-workshop/layers.py test 4
python3 agent-security-workshop/layers.py down 4
```

This folder has a complete Compose configuration and `security.sql`, and uses
its own database, networks and generated credentials. It does not require a
previous stage to be running. Shared implementation is in `../../layer_runtime`.

After starting, run from this folder:

```bash
docker compose exec -T agent python /opt/agent/client.py api /companies/1/salary-summary
```

## What This Stage Proves

Move the calculation from direct SQL to the API and block direct TCP by database name and IP.

## What Remains Exposed

The API still has broad salary-table SELECT permissions and returns individual salaries without authenticating people.

See [TASK.md](TASK.md) for the learner task and [the stage overview](../../LAYERS.md)
for the full progression. Tests deliberately confirm remaining exposure as
well as protections. A passing early stage does not mean the data is secure.
