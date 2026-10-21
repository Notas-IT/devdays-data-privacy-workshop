# Executable Tasks For The Database Security Slides

For unfinished learner configurations, copyable implementation prompts and a
single PASS/FAIL command, use [Implement One Change, Then Check It](IMPLEMENTATION.md).
The commands below inspect the completed reference stages.

Use one business question throughout: **What is company 1's average salary?**
Each exercise adds a boundary, demonstrates what it blocks, and checks that the
allowed question still works. These instructions run the completed reference
folders. They are run-and-inspect exercises, not unfinished starter files.
The implementation task in each section identifies the change to reconstruct
if the session also includes coding.
Implementation file paths below are relative to `agent-security-workshop/`;
terminal commands are run from the repository root.

The dataset belongs to `agent-security-workshop`, not the 100,000-person
`database-workshop`. Companies 1 and 2 each have three employees; company 3 has
one. Company 1's average is EUR 4,000. No model API key is needed for exercises
0–8. Every stage has its own database, credentials and Compose project.

## Setup And Command Conventions

Requirements: Python 3, Docker with Compose v2, and internet for the first
image build. Run from the repository root in bash or zsh. Define this helper
once in the terminal; it only selects the current stage's Compose file:

```bash
stage_compose() {
  docker compose -f "agent-security-workshop/layers/$stage_dir/docker-compose.yml" "$@"
}
python3 agent-security-workshop/layers.py list
```

Each section sets `stage_dir` before using the helper. Open a fresh terminal?
Return to the repository root and define the helper again. Commands execute
on the host unless `exec ... agent` explicitly runs them inside the agent.
The `setup` service is a trusted instructor tool; students must distinguish its
privileged inspection from what the agent itself can do.

Start a stage with `layers.py up N`, run the probes below, then run
`layers.py test N`. Stop it with `layers.py down N` before moving on. `down`
keeps data volumes. `up` refreshes demo token expiry and reapplies that stage's
declared grants. A passing test checks the stage's intended behavior, including
its deliberately remaining gaps; it does not label every stage secure.

Submit three items per exercise: the relevant configuration/SQL change, the
observed command output, and one remaining exposure. For a run-and-inspect
session, explain the existing change instead of submitting an implementation.

## 0. Baseline: An Average Task With Access To Individual Salaries

**Student task:** calculate an average, then establish whether the same account
can retrieve the individual values. Use selected columns so the random private
marker is not printed in the classroom.

```bash
python3 agent-security-workshop/layers.py up 0
stage_dir=00-plain-database
stage_compose exec -T agent python /opt/agent/client.py sql \
  'SELECT company_id,count(*) AS employee_count,avg(salary_eur) AS average_salary_eur FROM lab_private.employee_salaries WHERE company_id=1 GROUP BY company_id;'
stage_compose exec -T agent python /opt/agent/client.py sql \
  'SELECT employee_id,company_id,salary_eur FROM lab_private.employee_salaries ORDER BY employee_id;'
python3 agent-security-workshop/layers.py test 0
python3 agent-security-workshop/layers.py down 0
```

**Expected:** the average is 4,000, and the second query returns seven individual
salary rows across all three companies. The problem is unnecessary data access,
even when the agent follows its task correctly.

## 1. Agent Process: Inspect The Actual Privileges

**Implementation task:** in `layers/01-agent-process/docker-compose.yml`, add
`user: "10001:10001"`, `cap_drop: [ALL]`, and
`security_opt: ["no-new-privileges:true"]` to the agent relative to stage 0.
Keep privileged mode disabled. Explain why UID 10001 is a choice, while being
non-root is the relevant property.

```bash
python3 agent-security-workshop/layers.py up 1
stage_dir=01-agent-process
stage_compose exec -T agent id
stage_compose exec -T agent python -c 'from pathlib import Path; print("\n".join(line for line in Path("/proc/self/status").read_text().splitlines() if line.startswith(("CapEff:","NoNewPrivs:"))))'
stage_compose exec -T agent python /opt/agent/client.py sql \
  'SELECT count(*) AS visible_salary_rows FROM lab_private.employee_salaries;'
python3 agent-security-workshop/layers.py test 1
python3 agent-security-workshop/layers.py down 1
```

**Expected:** UID/GID 10001, `CapEff: 0000000000000000`, `NoNewPrivs: 1`, and
seven salary rows remain visible. The tests also inspect actual privileged-mode
settings. **Explain:** process restrictions do not replace SQL permissions.

## 2. Files: Try A Persistent Write And A Temporary Write

**Implementation task:** change the agent to `read_only: true` relative to
stage 1. Retain writable `tmpfs` mounts for `/tmp` and `/home/agent`, and the
read-only `/run/agent` credential volume. This volume contains only this agent's
limited credentials; a read-only mount still allows reads.

```bash
python3 agent-security-workshop/layers.py up 2
stage_dir=02-files
stage_compose exec -T agent python -c 'open("/workspace/lesson-marker", "w").write("workshop")'
stage_compose exec -T agent python -c 'open("/tmp/lesson-marker", "w").write("workshop")'
stage_compose up -d --force-recreate agent
stage_compose exec -T agent python -c 'from pathlib import Path; print(Path("/tmp/lesson-marker").exists())'
python3 agent-security-workshop/layers.py test 2
python3 agent-security-workshop/layers.py down 2
```

**Expected:** the `/workspace` write fails with a read-only-filesystem error;
the `/tmp` write succeeds; after agent recreation the temporary marker is absent
(`False`). The first command intentionally exits nonzero: run these lines
individually, not in a script that stops on the first error. The same workspace
write succeeds at stage 1 because `/workspace` is writable there.

**Explain:** approved credentials remain readable, and SQL access remains broad.

## 3. Host: Remove A Real Host Mount

**Student task:** inspect an actual, harmless host file before removing its
mount. Do not mount a home folder or invent a fake SSH-key example.

```bash
python3 agent-security-workshop/layers.py up 2
stage_dir=02-files
stage_compose exec -T agent python -c 'from pathlib import Path; p=Path("/host-workshop/README.md"); print(p.exists()); print(p.read_text().splitlines()[0])'
python3 agent-security-workshop/layers.py down 2

python3 agent-security-workshop/layers.py up 3
stage_dir=03-host
stage_compose exec -T agent python -c 'from pathlib import Path; print(Path("/host-workshop/README.md").exists()); print(Path("/var/run/docker.sock").exists())'
python3 agent-security-workshop/layers.py test 3
python3 agent-security-workshop/layers.py down 3
```

**Implementation task:** remove
`../../README.md:/host-workshop/README.md:ro` from the agent's volumes in stage
3 relative to stage 2. Retain only its named credential volume.

**Expected:** stage 2 can read the real workshop README; stage 3 prints `False`
for that path. The Docker socket is absent in both stages; this is an existing
safety boundary, not a newly demonstrated host takeover. The tests compare
the mounted file's bytes against the real source before the mount is removed.

**Explain:** filesystem read-only settings do not hide mounted host files.

## 4. Network: Make The API The Only Data Route

**Implementation task:** relative to stage 3, put the database only on `db_net`,
the agent only on `agent_net`, and the gateway on both. Keep networks internal
and ports unpublished. Stage setup must also stop placing the SQL credential
in `/run/agent/access.json`; see `layer_runtime/stage_setup.py`.

First observe the earlier connection:

```bash
python3 agent-security-workshop/layers.py up 3
stage_dir=03-host
stage_compose exec -T agent python -c 'import socket; socket.create_connection(("db",5432),timeout=2).close(); print("connected")'
python3 agent-security-workshop/layers.py down 3

python3 agent-security-workshop/layers.py up 4
stage_dir=04-network
stage_compose exec -T agent python -c 'import socket; socket.create_connection(("db",5432),timeout=2).close(); print("connected")'
stage_compose exec -T agent python /opt/agent/client.py sql 'SELECT 1;'
stage_compose exec -T agent python /opt/agent/client.py api /companies/1/salary-summary
python3 agent-security-workshop/layers.py test 4
python3 agent-security-workshop/layers.py down 4
```

**Expected:** stage 3 connects; stage 4's TCP attempt fails, its SQL client
reports missing direct database credentials, and its API request returns 200
with average 4,000. The first two stage-4 probes intentionally exit nonzero.
The tests also try the actual database IP, not just its Docker DNS name.

**Explain:** the gateway still has broad salary-table access at this stage.

## 5. Database: Restrict The Gateway's SQL Account

**Implementation task:** compare stage 4 and stage 5 `security.sql`. Revoke
the gateway's direct salary-table SELECT and private-schema USAGE; remove
its broad RLS policy. Grant only the approved `lab_api.salary_rows(integer)`
function at this intermediate stage. Keep role assumption and audit deletion
forbidden. Do not test these rights as `lab_admin` and call that an agent test.

```bash
python3 agent-security-workshop/layers.py up 5
stage_dir=05-database
stage_compose run --rm --no-deps -T setup queries
stage_compose exec -T agent python /opt/agent/client.py api /companies/1/salaries
stage_compose exec -T agent python /opt/agent/client.py api /companies/1/salary-summary
python3 agent-security-workshop/layers.py test 5
python3 agent-security-workshop/layers.py down 5
```

**Expected:** `queries` executes real statements as `gateway_reader` and reports
`raw_select: false`, `row_function: true`, `open_summary: false`,
`identity_summary: false`, `role_change: false`, `audit_delete: false`.
Both API calls still return 200, including three individual salary rows.

**Slide correction:** stage 5 limits *how* rows are read and which columns the
approved function exposes. It does **not** yet prohibit individual salary
access. That is the next exercise.

## 6. Aggregates: Return A Summary Instead Of Salary Rows

**Implementation task:** revoke the row function and grant
`lab_api.open_salary_summary(integer)` in stage 6 `security.sql`. Inspect its
implementation in `layer_runtime/functions.sql`: fixed output fields, a
restricted non-owner function role, RLS company filtering, and
`HAVING count(*) >= 3`. The gateway must reject individual-row endpoints.
The shared implementation already contains the stage-specific branch.

```bash
python3 agent-security-workshop/layers.py up 6
stage_dir=06-aggregates
stage_compose run --rm --no-deps -T setup queries
stage_compose exec -T agent python /opt/agent/client.py api /companies/1/salaries
stage_compose exec -T agent python /opt/agent/client.py api /companies/1/salary-summary
stage_compose exec -T agent python /opt/agent/client.py api /companies/3/salary-summary
stage_compose exec -T agent python /opt/agent/client.py api /companies/2/salary-summary
python3 agent-security-workshop/layers.py test 6
python3 agent-security-workshop/layers.py down 6
```

**Expected:** only `open_summary` is true among the four data-query probes;
individual rows return 403; company 1 returns 200 with exactly
`company_id`, `employee_count`, `average_salary_eur`; company 3 returns 403
because it has one employee. Company 2 still returns 200: membership is not
enforced until stage 7.

**Slide correction:** this is a PostgreSQL function, not a view. Verified
identity also belongs to stage 7. A three-person threshold reduces one obvious
disclosure; it is not an anonymity guarantee.

## 7. Identity: Use The Verified Account, Not Request Hints

**Implementation task:** in stage 7 grant `lab_api.authenticate(text)` and
`lab_api.salary_summary(text,integer)` instead of the open summary. Inspect
`tools/schema.sql`: the token maps to an actor/company, the requested company
must agree, and caller-supplied SQL context is overwritten. In
`layer_runtime/gateway.py`, inspect the authentication branch for stage 7+.

```bash
python3 agent-security-workshop/layers.py up 7
stage_dir=07-identity
stage_compose exec -T agent python /opt/agent/client.py api /me
stage_compose exec -T agent python /opt/agent/client.py api /companies/1/salary-summary
stage_compose exec -T agent python /opt/agent/client.py api /companies/1/salary-summary --anonymous
stage_compose exec -T agent python /opt/agent/client.py api /companies/2/salary-summary
stage_compose exec -T agent python /opt/agent/client.py api /companies/2/salary-summary --header X-User=admin --header X-Account-ID=admin
stage_compose exec -T agent python /opt/agent/client.py api '/companies/2/salary-summary?user_id=admin'
python3 agent-security-workshop/layers.py test 7
python3 agent-security-workshop/layers.py down 7
```

**Expected:** `/me` identifies `workshop-agent`, company 1; its own summary
returns 200; anonymous access returns 401; company 2 returns 403, including
with the added headers; unsupported query parameters return 400. The API client
prints HTTP status in JSON and exits zero after receiving an HTTP error, so
students must inspect `status`, not only the shell exit code.

**Explain:** a company ID in a request selects the desired resource; it does
not prove membership. There is no team-level model in this dataset: use
cross-company access for the executable example on the slide.

## 8. Audit: Trace Requests And Withhold Data When Auditing Fails

**Implementation task:** stage 8 grants INSERT on `lab_audit.events` to the
gateway, without UPDATE/DELETE. Inspect the gateway's stage-8 branch: record
the request's ID, verified actor when available, action, requested company,
status and outcome; commit before replying. Avoid recording tokens, salary
values or raw request URLs. Database/audit failures return 503 without data.

```bash
python3 agent-security-workshop/layers.py up 8
stage_dir=08-audit
stage_compose exec -T agent python /opt/agent/client.py api /companies/1/salary-summary
stage_compose exec -T agent python /opt/agent/client.py api /companies/2/salary-summary
python3 agent-security-workshop/layers.py audit 8
stage_compose exec -T db psql -X -U lab_admin -d agent_lab -c \
  'SELECT request_id,actor,action,company_id,status,outcome FROM lab_audit.events ORDER BY event_id DESC LIMIT 10;'
stage_compose run --rm --no-deps -T setup audit-failure
stage_compose exec -T agent python /opt/agent/client.py api /companies/1/salary-summary
python3 agent-security-workshop/layers.py test 8
python3 agent-security-workshop/layers.py down 8
```

**Expected:** allowed and denied requests appear in the audit summary. Match
each API response's `request_id` to the corresponding row using the instructor
SQL command. That SQL runs as a trusted database administrator, not the agent.
The stored `company_id` is the *requested* company; a denied request for company
2 does not mean the actor belongs to company 2.

`audit-failure` temporarily revokes the gateway's audit INSERT grant, makes a
real request, and restores the grant in `finally`. Expect
`{"status": 503, "contains_average": false}`; the following normal request
succeeds again. Run this serially, without another class demonstration using
the same stage. Earlier stages produce no audit records.

**Discuss:** a failed audit write cannot record itself in the same broken sink.
Independent failure monitoring is a related production requirement; this lab
does not pretend to implement it. Health checks are not included in this audit.

## 9. Model Connectivity: A Separate Broker Exercise

This slide has no `09-connectivity` folder. Keep it as a separate exercise
against the existing broker in the fully hardened lab; do not imply that
stage 8 has a broker attached.

**Student task:** inspect `model-broker/broker.py`, locate the fixed endpoint,
allowed model, request budget, output-token cap and injected provider key.
Then run its local contract tests from the repository root:

```bash
python3 -m unittest discover -s agent-security-workshop -p test_host.py -k BrokerTests -v
```

**Expected:** eight tests pass. They exercise the real broker's HTTP handler:
wrong credentials → 401; unsupported endpoint → 404; other model or upstream
web tool → 400; a one-call test budget allows the first call and rejects the
second with 429. A successful forwarded request uses the broker's upstream
credential, disables response storage and caps output at 4096 tokens.

These tests deliberately substitute a local upstream response. They verify
request handling without provider credentials or paid inference; they do not
demonstrate a live AI call, provider billing or production key security.
For an actual optional live Codex run, follow the existing
[Live Codex Exercise](README.md#live-codex-exercise), using its separate lab and
presenter-supplied development credentials. Do not mount a personal CLI login
or paste a provider key into the agent container.

**Implementation task:** keep provider credentials in the broker, give the
agent only its limited broker token, and reject model requests outside the
fixed policy. Lowering a test request budget demonstrates a limit, not a
currency-denominated spending cap.

## Short Prompts To Put On The Slides

| Slide | Student instruction | Observable success |
| --- | --- | --- |
| Agent process | Run `id` and inspect `/proc/self/status` inside the agent. | Non-root UID, zero effective capabilities, no-new-privileges enabled; SQL is still broad. |
| Files | Try writing in `/workspace` and `/tmp`; recreate the agent. | Workspace write denied; temporary write works and disappears. |
| Host | Read the mounted workshop README at stage 2, then try at stage 3. | The real host file is no longer mounted. |
| Network | Try TCP/SQL access to Postgres, then request the average through the API. | Direct access fails; API returns the approved average. |
| Database | Run actual queries as `gateway_reader`. | Direct SELECT and role change fail; the approved row function still works. |
| Aggregates | Request salary rows, a three-person average, and a one-person average. | Rows denied; three-person summary allowed; one-person summary denied. |
| Identity | Request another company with the normal token, no token, and extra identity headers. | Own summary works; absent/incorrect authority never grants access. |
| Audit | Match request IDs to audit rows, then trigger a real audit-write failure. | Requests are traceable; audit failure withholds the average. |
| Connectivity | Run broker tests and inspect the fixed policy. | Disallowed requests and excess calls are rejected; no paid inference in this test. |

For an instructor regression check of all nine reference folders:

```bash
python3 agent-security-workshop/layers.py verify-all
```

This checks and stops one stage at a time, retaining data volumes. It is not
a substitute for students inspecting the outputs and explaining the remaining
gap at each stage.
