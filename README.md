# DevDays Data Privacy Workshops

Each workshop has its own folder, documentation, examples, and Docker setup:

| Workshop | Folder | Exercise |
| --- | --- | --- |
| Database anonymisation and access protection | [database-workshop](database-workshop/README.md) | 100,000 synthetic people, reconstruction, SQL-user restrictions/owner bypass, authenticated permissions API and audit |
| Sensitive data in logs | [presidio-workshop](presidio-workshop/README.md) | Lithuanian logs, failing default Presidio validation, and passing customized detection |
| Anonymization before log ingestion | [log-pipeline-workshop](log-pipeline-workshop/README.md) | Simulated pods retain raw logs; Fluent Bit applies configurable privacy filters before shipping to Loki and Grafana |
| Production-to-preprod refresh | [schema-refresh-workshop](schema-refresh-workshop/README.md) | Compare sorted schema files, define preprod and column rules in code, and validate pseudonymised publication; includes a separate detection exercise |
| Restricted AI agent | [agent-security-workshop](agent-security-workshop/README.md) | Isolated Codex CLI, authenticated aggregate-only gateway, privilege-escalation tests and private-canary evaluation |

Editable [logging process diagrams](docs/logging-processes/README.md) cover a
script/Presidio flow, Fluent Bit regex/Lua routing, Kubernetes deployment options
and a restricted four-week raw archive, with PNG/SVG presentation exports.

## Run A Workshop

Database workshop:

```bash
cd database-workshop
docker compose up -d
```

Presidio workshop, starting from the repository root:

```bash
cd presidio-workshop
docker compose build presidio
docker compose run --rm presidio
```

See each workshop's README for generation, loading, and validation commands.

## Repository-Level Commands

The root Docker setup includes all workshop configurations. Existing commands
continue to work from the repository root:

```bash
docker compose up -d
docker compose build presidio
docker compose run --rm presidio
```

Presidio uses the `logs` profile and runs when explicitly targeted. These
commands use the existing Postgres project and volume. Docker Compose 2.20 or
newer is required for the root configuration's `include` support.

The log-ingestion simulation uses the separate `pipeline` profile. Its README
includes the presenter walkthrough, live configuration changes, and checks
against the actual Loki store.

## Restricted Agent Workshop

The agent lab uses its own Compose project and synthetic database so its
network-isolation tests have no dependency on the other workshops' published
ports or credentials:

```bash
python3 agent-security-workshop/lab.py up
python3 agent-security-workshop/lab.py test
```

See the [agent workshop walkthrough](agent-security-workshop/README.md) for
the optional live Codex exercise, model-broker configuration and audit checks.

The [nine cumulative stages](agent-security-workshop/LAYERS.md) start with
direct database access and add one security layer at a time:

```bash
python3 agent-security-workshop/layers.py up 0
python3 agent-security-workshop/layers.py test 0
```
