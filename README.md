# DevDays Data Privacy Workshops

Each workshop has its own folder, documentation, examples, and Docker setup:

| Workshop | Folder | Exercise |
| --- | --- | --- |
| Database anonymisation and access protection | [database-workshop](database-workshop/README.md) | 100,000 synthetic people, reconstruction, SQL-user restrictions/owner bypass, authenticated permissions API and audit |
| Sensitive data in logs | [presidio-workshop](presidio-workshop/README.md) | Lithuanian logs, failing default Presidio validation, and passing customized detection |
| Anonymization before log ingestion | [log-pipeline-workshop](log-pipeline-workshop/README.md) | Simulated pods retain raw logs; a configurable processor ships sanitized records to Loki and Grafana |
| Production-to-preprod refresh | [schema-refresh-workshop](schema-refresh-workshop/README.md) | Detect added columns, analyze sampled data, classify sensitivity, and gate anonymized publication |

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
