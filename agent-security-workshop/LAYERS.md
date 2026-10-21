# Build Security One Layer At A Time

For commands, expected results and slide-sized student prompts, use the
[executable exercises](EXERCISES.md). They distinguish running the completed
references from reconstructing each security change.

Nine independent folders contain a plain-database baseline plus eight
cumulative reference stages, in the requested order. Each folder has a
complete `docker-compose.yml`, explicit database grants in `security.sql`, a
README, and a learner task. A stage does not require its predecessor to run.
The small shared implementation is in `layer_runtime/`.

The business task stays the same: calculate company 1's average salary without
unnecessarily collecting or returning individual salaries. Compare the
previous folder with the next one to see the added boundary. The folders are
completed references; `TASK.md` describes the change learners can rebuild.

| Folder | Adds to every previous layer | Remaining gap to discuss |
| --- | --- | --- |
| [00-plain-database](layers/00-plain-database/README.md) | Baseline: the agent queries PostgreSQL directly | It can read every individual salary |
| [01-agent-process](layers/01-agent-process/README.md) | Non-root UID, dropped capabilities, no-new-privileges | These do not remove SQL access or writable workspace files |
| [02-files](layers/02-files/README.md) | Read-only container filesystem and temporary writable storage | A read-only host mount is still readable |
| [03-host](layers/03-host/README.md) | Remove the host-file bind mount | Direct database connectivity and SQL credentials remain |
| [04-network](layers/04-network/README.md) | Separate agent/database networks, remove agent SQL credentials, add API gateway | Gateway still has broad salary-table permissions |
| [05-database](layers/05-database/README.md) | Revoke direct salary SELECT; grant an approved per-company row function | Individual rows and caller-chosen companies are still available |
| [06-aggregates](layers/06-aggregates/README.md) | Revoke row function; allow a fixed summary and minimum cohort size | A shared/anonymous caller can still choose another company |
| [07-identity](layers/07-identity/README.md) | Verify a per-actor token and derive company membership from it | Allowed/denied requests leave no durable audit trail |
| [08-audit](layers/08-audit/README.md) | Commit append-only audit records before responses; fail closed on audit failure | Presenter, host, Docker administrator and application code remain trusted |

## Run A Stage

From the repository root:

```bash
python3 agent-security-workshop/layers.py list
python3 agent-security-workshop/layers.py up 0
python3 agent-security-workshop/layers.py test 0
python3 agent-security-workshop/layers.py down 0
```

Use `0` through `8`, or a full folder name. Every stage uses a separate Compose
project (`devdays-agent-layer-00`, etc.), database, credentials and networks.
`down` retains its volumes. Starting a stage again refreshes its demo token
expiry and reapplies that stage's permissions without altering another stage.
The original fully hardened lab and other workshop databases are separate.

Run the complete progression, one stage at a time:

```bash
python3 agent-security-workshop/layers.py verify-all
```

This builds the two shared images once, starts/tests/stops each stage, and
retains its data volumes. Run tests serially rather than alongside a live
demonstration or edits to the mounted source files.

The first image build needs internet access. Tests and examples use real
containers, SQL permissions, RLS policies, TCP connections, HTTP requests and
audit writes. No model API key or paid inference is needed. Codex CLI 0.163.0
is installed in the agent image; the existing [fully hardened lab](README.md)
provides the optional live model-broker exercise. Model connectivity is kept
separate from this eight-layer progression.

## Direct SQL In The Baseline

After starting stage 0, run from its folder:

```bash
cd agent-security-workshop/layers/00-plain-database
docker compose exec -T agent python /opt/agent/client.py sql \
  'SELECT company_id, avg(salary_eur) FROM lab_private.employee_salaries GROUP BY company_id;'
docker compose exec -T agent python /opt/agent/client.py sql \
  'SELECT employee_id, employee_name, salary_eur FROM lab_private.employee_salaries;'
```

Both queries succeed. The same direct access remains at stages 1–3 even after
process/files/host restrictions are added. Stage 4 removes both the connection
route and the direct SQL credential. The API then becomes the intended route.
From the repository root, start stage 4 and run:

```bash
python3 agent-security-workshop/layers.py up 4
cd agent-security-workshop/layers/04-network
docker compose exec -T agent python /opt/agent/client.py api /companies/1/salary-summary
docker compose exec -T agent python /opt/agent/client.py api /companies/2/salaries
```

The second request intentionally still succeeds at stages 4 and 5. Stage 6
blocks individual rows but still allows another company's average. Stage 7
adds the missing company-membership check.

## What Is Real, And What Is Not Demonstrated

The data is fictional, as in the original workshop. It contains two
three-person companies and a real one-row cohort in the database, so the
effect of minimum-group suppression is observable. A random marker in a
salary row lets the presenter confirm when raw private data is exposed.
Early-stage tests expect that exposure; they do not call it secure.

For the host layer, stages 0–2 mount exactly one actual workshop README from
the presenter filesystem, read-only. Stage 3 removes that bind mount. A test
compares the visible bytes with the actual source file before the layer, and
confirms the file is no longer present afterward. This demonstrates a real
mount boundary without fabricating credentials or exposing personal files.

No stage mounts the home directory, SSH keys, Docker socket or host PID
namespace. Their risk is explained through the related concept: any mounted
resource becomes reachable from the agent's environment. Kernel exploits and
host compromise are not simulated or claimed to be tested.

Every stage has a constant outer safety envelope: isolated synthetic database,
no published ports, internal Docker networks, no privileged container mode,
and resource limits. Stage 0 has container root/default capabilities and broad
read-only SQL grants on the salary table; it is not a host administrator or a
database superuser. The network lesson concerns the real agent-to-database
route, which remains open until stage 4.

## How The Tests Explain Progress

Each stage checks all earlier boundaries plus the new one. Tests also confirm
what remains open, so a passing test suite at stage 1 does not imply that
salary data is protected. API tests are explicitly skipped at stages 0–3
because no gateway exists yet; audit-failure testing begins only at stage 8.

The suite checks actual process flags, filesystem writes, host mounts,
connections by database name and real IP, direct SQL, approved and forbidden
function execution, individual-row responses, small-cohort suppression,
anonymous/cross-company access, identity headers, unsupported methods, audit events and an actual
audit-insert failure. The presenter observes outputs without printing the
random private marker or privileged credentials.

Relevant implementation references: Docker's [service controls](https://docs.docker.com/reference/compose-file/services/)
and PostgreSQL's [row security](https://www.postgresql.org/docs/16/ddl-rowsecurity.html).
Minimum cohort size reduces an obvious disclosure but does not establish
anonymity or differential privacy.
