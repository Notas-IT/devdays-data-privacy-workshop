# Implement One Change, Then Check It

Run all commands from the repository root. Requirements: Python 3 and Docker
with Compose v2; internet is needed for the first image build.

The `layers/` folders are completed references. Create a separate learner
folder before asking an agent to implement a change:

```bash
python3 agent-security-workshop/layers.py prepare 1
```

This copies the **previous reference stage's** Compose configuration and SQL
grants into `.practice/01-agent-process/`. It selects stage 1's runtime behavior
but does not add stage 1's missing process protection. Each exercise starts
independently from the previous completed reference, rather than copying your
own earlier solution. Preparing an existing folder refuses to overwrite edits.

The provided shared runtime already implements the API branches and SQL
functions. Students configure container boundaries and database grants; they
are not building an API from scratch. File paths below are relative to the
repository root. The prompts can be pasted into Claude Code or Codex.

After the agent edits the learner files, use the single `check` command. It
rebuilds images, reapplies that learner SQL, recreates changed services, and
tests actual behavior in a **separate practice Docker project and database**.
It prints `PASS` and exits 0 only when deployment and all required checks pass;
otherwise it prints `FAIL` and exits nonzero. A Docker/build failure is also a
FAIL, so read the preceding diagnostic to distinguish it from a failed boundary.
Running `check` on a fresh, unmodified starter should fail.

## 1. Agent Process

Prepare: `python3 agent-security-workshop/layers.py prepare 1`

Paste this prompt:

> Implement the process-security layer in
> `agent-security-workshop/.practice/01-agent-process/docker-compose.yml`.
> Run the agent as UID/GID 10001, drop all Linux capabilities, enable
> no-new-privileges, and keep privileged mode disabled. Preserve the existing
> writable workspace, temporary mounts, host README mount and SQL connectivity:
> those belong to later lessons. Keep STAGE_LEVEL=1. Change only this practice
> configuration; leave the references, shared runtime and tests unchanged.

Run the action/check:

```bash
python3 agent-security-workshop/layers.py check 1 --practice
```

**PASS means:** the running process has UID 10001, zero effective capabilities,
and no-new-privileges enabled. The original direct SQL task still works.

## 2. Files

Prepare: `python3 agent-security-workshop/layers.py prepare 2`

> Implement the filesystem layer in
> `agent-security-workshop/.practice/02-files/docker-compose.yml`.
> Make the agent's root filesystem read-only. Keep `/tmp` and `/home/agent`
> writable through their existing tmpfs mounts, and keep its credential volume
> read-only. Preserve process restrictions and the existing host/network/SQL
> configuration. Keep STAGE_LEVEL=2; do not modify references, runtime or tests.

```bash
python3 agent-security-workshop/layers.py check 2 --practice
```

**PASS means:** an actual write to `/workspace` fails, an actual write to
`/tmp` succeeds, and the earlier process restrictions still hold.

## 3. Host

Prepare: `python3 agent-security-workshop/layers.py prepare 3`

> Implement the host boundary in
> `agent-security-workshop/.practice/03-host/docker-compose.yml`.
> Remove the agent's host README bind mount at `/host-workshop/README.md`.
> Keep only its existing named credential volume and temporary mounts. Do not
> add host directories, devices, Docker socket access or a host PID namespace.
> Preserve prior restrictions and direct SQL connectivity. Keep STAGE_LEVEL=3;
> do not modify references, runtime or tests.

```bash
python3 agent-security-workshop/layers.py check 3 --practice
```

**PASS means:** the real host README is absent inside the agent, no host bind
mount remains on the agent, and earlier restrictions still hold.

## 4. Network

Prepare: `python3 agent-security-workshop/layers.py prepare 4`

> Implement the network boundary in
> `agent-security-workshop/.practice/04-network/docker-compose.yml`.
> Put the database only on db_net and the agent only on agent_net. Add a gateway
> service using the provided layer-runtime image/build and `python gateway.py`
> entrypoint, with STAGE_LEVEL=4. Mount gateway_config read-only at
> `/run/gateway`, attach the gateway to both networks, and wait for the healthy
> database before starting it. Use the existing reference gateway's health
> check and process/resource restrictions. Have the agent wait for a healthy
> gateway. Keep both networks internal, all ports unpublished, and earlier
> restrictions intact. The provided setup already omits the agent's database
> credential at STAGE_LEVEL=4; do not add it back. Leave references, shared
> runtime, SQL grants and tests unchanged.

```bash
python3 agent-security-workshop/layers.py check 4 --practice
```

**PASS means:** direct database connections fail by both DNS name and actual
IP, no direct SQL credential is available, and the API still returns average
4,000 for company 1. Gateway database rights remain broad until the next task.

## 5. Database

Prepare: `python3 agent-security-workshop/layers.py prepare 5`

> Implement the database-grant layer in
> `agent-security-workshop/.practice/05-database/security.sql`.
> Remove gateway_reader's direct salary SELECT, private-schema USAGE and the
> broad layer_direct RLS policy. Revoke access to the other salary/authentication
> functions and grant EXECUTE only on the supplied
> `lab_api.salary_rows(integer)` function. Preserve public-project access and
> the prohibitions on privileged role changes and audit deletion. This lesson
> intentionally still permits approved individual salary rows. Do not change
> the practice Compose file's STAGE_LEVEL=5, shared runtime, references or tests.

```bash
python3 agent-security-workshop/layers.py check 5 --practice
```

**PASS means:** real queries as the gateway account cannot read the table or
assume the admin role; the approved row function and API task still work.

## 6. Aggregates

Prepare: `python3 agent-security-workshop/layers.py prepare 6`

> Implement aggregate-only access in
> `agent-security-workshop/.practice/06-aggregates/security.sql`.
> Revoke gateway_reader's EXECUTE on `lab_api.salary_rows(integer)` and grant
> EXECUTE on the supplied `lab_api.open_salary_summary(integer)` instead.
> Preserve the existing table/role restrictions. The supplied function and
> stage-6 gateway already return a fixed summary and suppress groups below
> three; do not weaken that behavior or add alternate read paths. Identity is
> deliberately deferred to stage 7. Keep STAGE_LEVEL=6, references, shared
> runtime and tests unchanged.

```bash
python3 agent-security-workshop/layers.py check 6 --practice
```

**PASS means:** individual salary requests fail, company 1's three-person
average works, and company 3's one-person average is withheld. Another company
is still accessible at this intermediate stage.

## 7. Identity

Prepare: `python3 agent-security-workshop/layers.py prepare 7`

> Implement identity-bound access in
> `agent-security-workshop/.practice/07-identity/security.sql`.
> Revoke the open summary function from gateway_reader. Grant EXECUTE on the
> supplied `lab_api.authenticate(text)` and
> `lab_api.salary_summary(text,integer)` functions instead. Use their existing
> token-to-company verification and the supplied stage-7 gateway behavior;
> do not grant access based on X-User, X-Account-ID, a query parameter or a
> caller-set company variable. Preserve prior grants/restrictions, keep
> STAGE_LEVEL=7, and leave references, runtime and tests unchanged.

```bash
python3 agent-security-workshop/layers.py check 7 --practice
```

**PASS means:** company 1 works; anonymous requests return 401; requests for
company 2 return 403 even with misleading identity headers.

## 8. Audit

Prepare: `python3 agent-security-workshop/layers.py prepare 8`

> Enable durable auditing in
> `agent-security-workshop/.practice/08-audit/security.sql`.
> Grant gateway_reader INSERT on `lab_audit.events`, without granting UPDATE
> or DELETE. Preserve all earlier protections and keep STAGE_LEVEL=8. The
> provided gateway already commits the audit insert before returning data and
> returns 503 if the insert fails. Do not bypass that transaction, log salary
> values/credentials, or modify references, runtime or tests.

```bash
python3 agent-security-workshop/layers.py check 8 --practice
```

**PASS means:** allowed and denied requests are recorded. The check also
temporarily revokes the audit INSERT grant, makes a real API request, expects
503 without an average, and restores the grant. Run checks serially.

## 9. Model Connectivity: Review And Test The Existing Broker

There is no ninth learner stage. This is a separate existing implementation,
so use it as a review/hardening task rather than claiming it is an unfinished
starter:

> Review `agent-security-workshop/model-broker/broker.py`. Ensure it keeps the
> provider credential outside the agent, accepts only its fixed Responses
> endpoint and configured model, caps output, disables response storage, limits
> calls and rejects unsupported upstream tools. Make any needed fixes without
> weakening the existing tests or placing real credentials in source/agent
> configuration. If these requirements already hold, explain where each is
> enforced rather than making unnecessary changes.

```bash
python3 -m unittest discover -s agent-security-workshop -p test_host.py -k BrokerTests -v
```

**Pass:** eight tests finish with `OK`. **Fail:** `FAILED`, errors, or a nonzero
exit code. These exercise the real broker handler with a substituted local
upstream; they do not make paid AI calls or establish a monetary budget.

## Inspect And Stop A Learner Stage

The `check` command leaves the practice services running for inspection:

```bash
python3 agent-security-workshop/layers.py audit 8 --practice
python3 agent-security-workshop/layers.py down 8 --practice
```

Use the corresponding stage number. `down` retains the learner database. Use
`--practice` consistently: omitting it selects the completed reference project.
For individual manual probes, see [EXERCISES.md](EXERCISES.md); those examples
target references, so select the learner Compose file/project when applying
them to practice. A PASS verifies this workshop's specified checks, not every
possible security property.
