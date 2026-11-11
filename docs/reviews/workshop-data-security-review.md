# Workshop Data Security: Slide Review

Reviewed: 21 October 2026. Source: `/Users/mantasdamijonaitis/Documents/workshop_data_security.pdf` (66 pages).
Slide numbers below are the PDF page numbers, which match the printed slide numbers.

Scope: proofreading, technical consistency with the current repository, exercise
instructions and visual readability. All pages were rendered and visually
inspected; dense diagrams were also inspected individually. This was a
read-only review of the PDF and repository. No database exercises or paid AI
calls were run. Two invalid CLI forms were checked; both fail during argument
parsing, before any deployment starts. The PDF itself is unchanged.

## Overall Assessment

The sequence has a clear teaching purpose: limit access, transform copies,
test surviving links, and redact logs before ordinary ingestion. The strongest
part is the repeated change/check/result pattern in the architecture exercises.

The main issue is consistency between the slides and the runnable material.
Students encounter several independent databases and a mix of implemented
features and proposed architectures. Make those transitions explicit before
polishing individual sentences.

## Fix These Before The Workshop

| Priority | Slides | Issue | Required correction |
| --- | --- | --- | --- |
| Blocking | 23, 25, 27, 29, 31, 33, 37 | A typographic em dash replaces the CLI option's two hyphens. Slide 29 also separates the dash from `practice`. | Use the literal ASCII option `--practice`. Disable smart-dash substitution in code boxes. Slide 35 already has the correct option. |
| Blocking | 39 | `layers.py prepare 9` does not exist. | Remove it. The learner stages are 1-8; model connectivity is a separate existing broker review/test. |
| Blocking | 10, 14, 46 | Repository URL, `[x]` command and database-clone setup are unfinished. | Replace placeholders and supply exact startup instructions, working directory and database names. |
| Major | 43, 46-53 | The slides mix the ten-table private/public dataset with the separate three-table refresh exercise. | Choose which dataset each exercise uses and state the transition. The existing refresh code does not clone the ten-table graph. |
| Major | 47 | Regex non-matches are used as the main proof of pseudonymisation. | Check original-value removal, expected token transformation, consistency and relationships. Email tokens remain email-shaped. |
| Major | 53 | The trace command defaults to original `private_db`, not a masked copy. | Label it as the baseline or supply a compatible target schema explicitly, then compare reports. |
| Major | 30-33 | Stage descriptions contradict the implementation. | Stage 5 still permits approved individual rows. Stage 6 uses an open aggregate function. Verified company membership starts at stage 7. |
| Major | 18 | Setting a company variable is presented as sufficient authority. | Explain that a trusted authentication layer supplies context. An untrusted SQL user must not choose its own identity. |
| Major | 60-65 | Diagrams include Presidio routing, a second forensic Loki and Kubernetes, which are not deployed by the current log demo. | Label these as target architecture/design discussion or add separate implementation work. |
| Visual | 63 | The diagram covers part of the heading. | Move the diagram below the title or give it a dedicated full-slide layout. |

## Exact Command Corrections

### Architecture Exercise Slides

The correct check commands are:

```bash
python3 agent-security-workshop/layers.py check 1 --practice
python3 agent-security-workshop/layers.py check 2 --practice
python3 agent-security-workshop/layers.py check 3 --practice
python3 agent-security-workshop/layers.py check 4 --practice
python3 agent-security-workshop/layers.py check 5 --practice
python3 agent-security-workshop/layers.py check 6 --practice
python3 agent-security-workshop/layers.py check 7 --practice
python3 agent-security-workshop/layers.py check 8 --practice
```

Run each only after preparing and implementing that corresponding stage.
Do not present the whole block as an unconditional batch.

Add this instruction before slide 23:

> Run commands from the repository root. `prepare N` creates an unfinished
> learner configuration under `agent-security-workshop/.practice/`. Ask your
> agent to edit that folder, keeping references, shared runtime and tests
> unchanged. Each exercise starts from the previous completed reference,
> rather than your own earlier solution. `check N --practice` builds, applies
> and tests the learner version. An untouched starter should fail; the
> implemented version should pass. Read the diagnostic: deployment errors
> also produce FAIL.

Show cleanup as well:

```bash
python3 agent-security-workshop/layers.py down 1 --practice
```

Replace `1` with the completed stage number. The services otherwise remain
running for inspection; `down` retains their database volumes. Preparing an
existing learner folder refuses to overwrite work.

On slide 39, remove the prepare command and use this single command box:

```bash
python3 -m unittest discover -s agent-security-workshop -p test_host.py -k BrokerTests -v
```

Expected: eight tests finish with `OK`. The current slide's line wrap before
`-k` should be a visual wrap within one command, or use an explicit shell
continuation. Keep the existing explanation that the upstream is substituted
locally and there are no paid calls. This is a review of a completed broker,
not another unfinished learner stage.

### RLS Exercise: Slide 18

Use the existing integration tests rather than giving only a filename:

```bash
docker compose -f database-workshop/docker-compose.yml build db-security-tools
docker compose -f database-workshop/docker-compose.yml run --rm db-security-tools init
docker compose -f database-workshop/docker-compose.yml run --rm --entrypoint pytest db-security-tools -q test_rls_session.py
```

Prerequisite: the original database schema and data are loaded. `init` resets
demo accounts and permissions, not the source dataset. These are PostgreSQL
integration tests, not isolated unit tests.

Suggested replacement description:

> Calculate a company average using authenticated request context. Run the
> same aggregate query for two accounts and confirm each sees only its own
> company. Missing context must return no salary data. Commit or rollback must
> clear transaction-local context before the connection is reused.

Direct SQL logins in this repository are bound to `session_user`. Only the
trusted API login uses `app.account_id`; a setting supplied by an untrusted
client is not proof of identity. RLS filters rows; it does not by itself stop
an authorised user from selecting the individual rows behind an average.

### Tracing Exercise: Slide 53

As written, the command is a valid **baseline** against the original data:

```bash
python3 database-workshop/trace_data.py trace --person 42 --output-dir database-workshop/reports/before
```

It creates `trace.html` and `trace.json` under that output directory. Show
students where to open the report.

If students have built a same-layout copy in schema `pseudonymised_private`
inside the same database, the corresponding after/compare commands are:

```bash
python3 database-workshop/trace_data.py trace --person 42 --private-schema pseudonymised_private --output-dir database-workshop/reports/after
python3 database-workshop/trace_data.py compare database-workshop/reports/before/trace.json database-workshop/reports/after/trace.json --output-dir database-workshop/reports/comparison
```

That target schema is a prerequisite, not something the tracer creates.
The three-table `schema-refresh-workshop` output is not compatible with this
tracer. The tool also does not join across separate PostgreSQL databases.

Replace “pinpoint easily traceable data” with:

> Inspect candidate links for one public person, then compare which links and
> values remain after transformation. A candidate match is not a confirmed
> identity, and no matches do not prove anonymity.

Put commands in one monospaced block without bullet characters. Keep the
public reference data unchanged between the compared reports.

## Technical Wording To Replace

### Slides 11-15: Instructions And Permissions

For slide 11:

> An AGENTS.md file guides the agent's behaviour. Database permissions enforce
> what the account can actually read or change. A mistaken command can still
> access anything the account permits.

For slide 12:

> Direct database access bypasses the API's audit trail. If direct access is
> allowed, configure database-level auditing as well.

The original “no direct way to tell what data it read” is too absolute.
Statement auditing also should not be presented as a complete record of every
returned row. Replace “Every product owner” with “Some teams”.

For slide 15, the lesson should match the demonstration:

> Prompt instructions are not an access-control boundary. Read-only permissions
> prevent writes; company-scoped database rules restrict which rows can be read.

Delete “a read-only database user is irrelevant”. Read-only access is useful,
and an instruction-override exercise does not itself demonstrate credential
theft. Clarify that different runs may refuse, comply, or avoid the request;
no particular model response is a guaranteed test outcome.

For cross-tool participants, explain that each coding tool has its own
repository-instruction mechanism; AGENTS.md is the Codex example. A refusal
to ignore a file is not evidence that database access is technically blocked.

### Slides 17-18: Table Ownership And RLS

Replace the claim that a table creator bypasses “permissions” with:

> Table owners normally bypass row-level security. FORCE ROW LEVEL SECURITY
> can apply policies to an owner, but that owner can change the configuration.
> Superusers and BYPASSRLS roles remain privileged. Use a non-owner application
> role for the exercise.

This distinction is supported by
[PostgreSQL's row-security documentation](https://www.postgresql.org/docs/16/ddl-rowsecurity.html)
and the repository's `owner-demo`. It is not a claim that all SQL permissions
are ignored for a table creator.

### Slides 28, 30, 32 And 34: Keep The Stage Boundaries Accurate

- **Slide 28:** “The network makes the gateway the required data route.
  Authentication and company restrictions are added in later stages.” The
  stage-4 gateway is not yet authenticated.
- **Slide 30:** “The gateway can no longer query the private table directly.
  It can use an approved function that exposes a limited set of columns.”
  Approved individual salaries remain readable at stage 5, as slide 31
  correctly says.
- **Slide 32:** “Aggregates: return a fixed company summary instead of
  individual salaries. Groups below three are withheld. Identity restrictions
  come next.” Replace “(view)” with “(function)”. Stage 6 accepts a company ID
  without verifying membership.
- **Slide 34:** Use company 1 versus company 2 in the example. The implemented
  dataset has company membership, not team-level permissions.

At the overview, distinguish eight cumulative layers from the optional model
broker extension. There are nine folders because stage 0 is the baseline.

### Slides 43-53: Pick A Dataset And A Validation Contract

The deck currently crosses these two implementations:

| Repository area | Actual data model | Relevant exercise |
| --- | --- | --- |
| `database-workshop` | One `privacy_workshop` database; `private_db` and `public_db` schemas; ten tables, including `person_identity` and `employment_contract` | Private/public reconstruction, API/RLS protection, known-graph tracing |
| `schema-refresh-workshop` | Separate `production` and `preprod` databases; three `business` tables: `people`, `employment`, `companies` | Code-defined target, column rules, schema drift, staging and publication |

The diagram on slide 43 and table names on slide 48 describe the first model.
The ready-made refresh mechanism describes the second. Either adapt the
cloning slides to the existing three-table exercise, or clearly label the
ten-table cloning task as a new student-built extension. Do not imply the
provided refresh command clones the full private/public graph.

On slide 47, replace the regex acceptance strategy with:

> Verify that original emails and national IDs are absent from the transformed
> fields. Verify expected HMAC-token output, stable tokens for the same input
> and scope, shared tokens across related columns, and preserved constraints.

The current email transform returns `person-<token>@example.invalid`. It is
still email-shaped; a generic email regex can match it. Sampling also cannot
prove that no original value remains elsewhere in the database.

On slide 48, do not update constrained parent and child columns independently
without explaining transaction/constraint handling. The current ten-table
foreign keys are not declared deferrable. Prefer the refresh implementation's
approach: transform consistently into staging, load all tables, validate
foreign keys, and publish only after validation. This also avoids first
copying an unmasked production dataset into the final developer-visible target.

On slide 49, align the birth date to **2000-01-01**, matching slide 45 and
`preprod_schema.py`. Use `Person` for first name and `Anonymous` for last name.
Replacing a field with a constant is a masking technique; masking is not a
separate competing concept from fixed-value replacement.

On slide 50, retaining IDs preserves joins but can also preserve links back
to production/public records. State that it is an intentional utility/privacy
trade-off, not proof of anonymisation.

On slide 51, replace “Stop in unknown columns” with **“Stop on unreviewed schema
changes”**. The gate must stop for any unmapped column, not only one a detector
labels sensitive. Compare previous/current **source** snapshots and check the
current source against the reviewed column mapping. Source and target need
not be identical: omissions, renamed target columns and transformations can
be deliberate. If using the existing refresh dataset, its table is
`business.companies`, not `company`.

On slide 52, describe the actual publication sequence:

> Read one consistent source snapshot. Validate the schema contract. Transform
> each column into restricted target staging. Validate counts and constraints.
> Atomically replace the published preprod schema only after success. Preserve
> the previous published version on failure.

The current implementation does not create a new database for every refresh.
It is a code-defined refresh; schema inspection is not a general PII detector.

### Slides 57-59: Describe Detection Methods Precisely

Use this text on slide 57:

> Presidio detects possible personal data using regex patterns, word lists,
> validation rules, context and NLP recognisers. The Analyzer finds spans; the
> Anonymizer transforms the detected spans. It can run as Python code or an
> HTTP service. Detection can miss data.

“Simple NLP” and “Complex NLP” are not product modes. The workshop uses the
large `en_core_web_lg` model, so calling its model “tiny” is inaccurate.
See the [Analyzer documentation](https://presidio.dataprivacystack.org/analyzer/).

For slide 58:

> The default configuration misses several Lithuanian cases in our fixture.
> Custom recognisers improve this fixture's coverage. Test false positives and
> missed entities; passing the fixture does not prove all logs are safe.

The repository still uses `language="en"` with custom recognisers for its log
formats. It does not add a Lithuanian language model. General language support
requires suitable models and recognisers; see
[the language configuration documentation](https://presidio.dataprivacystack.org/analyzer/languages/).

For slide 59:

> Fluent Bit collects, processes and forwards logs. Inputs, filters and outputs
> are configured in YAML or classic configuration files. Lua is one option for
> custom record transformations; this workshop uses a Lua privacy filter.

See [Fluent Bit configuration](https://docs.fluentbit.io/manual/administration/configuring-fluent-bit)
and the [Lua filter](https://docs.fluentbit.io/manual/data-pipeline/filters/lua).

### Slides 60-65: Separate The Running Demo From The Target Design

The current runnable pipeline is:

```text
Two application containers -> Fluent Bit -> Lua privacy filters -> Loki -> Grafana
```

The separate Presidio workshop validates a static annotated log corpus.
The pipeline does not currently deploy Presidio HTTP fallback, a second
forensic Loki/Grafana, four-week forensic retention, or Kubernetes manifests.
The diagrams are expressly documented as proposed additions.

Suggested caption on slides 60, 62-64:

> Target architecture. The current Docker exercise demonstrates the core
> Fluent Bit/Lua path; Presidio routing, forensic storage and Kubernetes are
> extensions discussed here.

For slide 61, replace “Remaining logs” with an explicit fork:

> Archive an untouched original copy in the restricted forensic store. Process
> a separate working copy of every event. Use the fast path only for supported
> structured records, emitting approved redacted fields. Send other records
> to the Presidio path. A regex miss does not mean the event is safe.

The fast path must not merely remove one matching email and retain arbitrary
free text containing other identifiers. Presidio misses are also possible.
The raw archive intentionally retains the removed values; a separate container
alone does not restrict access. Clarify that 28 days is the proposed workshop
retention, not a universal retention requirement or a guarantee of instantaneous
deletion when the period expires.

Add a runnable Presidio exercise before asking students to extend a “first
application” that is not otherwise defined:

```bash
cd presidio-workshop
docker compose build presidio
docker compose run --rm presidio python -m pytest exercises/default_validation.py -q -p no:cacheprovider
docker compose run --rm presidio
```

Expected: the default validation deliberately fails; the customised suite
passes. Run these as separate steps, not a stop-on-error batch.

For the existing Fluent Bit implementation, supply a separate command block:

```bash
cd log-pipeline-workshop
docker compose --profile pipeline up -d --build
docker compose run --rm pipeline-checks
```

The `cd` commands above assume the repository root as their starting point;
use separate terminals or return to the root before switching workshops.

## Slide-By-Slide Proofreading

Use British spelling consistently: **anonymisation, pseudonymisation,
recogniser, behaviour, favourite, synthesise**. Keep identifiers, commands and
product APIs exactly as the code requires. Use **schema** for database
structure, **diagram/architecture** for a drawing, **Fluent Bit**, **PostgreSQL**
and **Kubernetes** for product names.

| Slide | Correction or suggestion |
| --- | --- |
| 1 | Use “Detecting and Anonymising Sensitive Data Across the Stack” to match British spelling elsewhere. Keep the clear title/subtitle hierarchy. |
| 2 | “I lead a team of seven.” “I work on critical IT infrastructure in Lithuania.” Remove the final empty bullet. |
| 3 | “AI is useful, but poorly controlled access can expose sensitive data.” Replace “current-day tools” with “tools we can use today”. |
| 4 | “We will learn how to prepare applications and infrastructure for safer AI access.” Fix `understading` -> `understanding`. Shorten the junior-developer analogy to one sentence. |
| 5 | “Why do we need this workshop?” Replace “have to have solid questions” with “need to know which questions to ask”. |
| 6 | “Detecting unreviewed schema changes”, not “catching unchecked structure”. The promised documents/database Presidio block is broader than the shown log-based material; align the agenda with the actual exercises. Add short breaks and more build/setup time. |
| 7 | Enlarge the roadmap and align its labels with the agenda. Consider “Re-identification testing” instead of “Data reverse-engineering”. |
| 8 | “We have three spare laptops available.” The present wording sounds like students must bring them. “If setup takes more than five minutes, follow along while we help.” |
| 9 | “Basics of safer AI access to data.” Remove the unsupported claim about providers relaying data to China. Say: “Follow the applicable customer and organisational policies. Limit what data tools and services can receive.” Do not present EU hosting or model-training terms as universal requirements. |
| 10 | Replace `(URL)` with the actual link/QR. Add Python 3, the Compose requirement and DBeaver if required later. Mark a provider API key as optional for the live model exercise; deterministic exercises need none. Pre-download large images/models. |
| 11 | “Securing access to the database”; “Why is it important?” Fix “the and agent”, “addresses out”, “for solution” and “I might try it out”. Use “the agent might try those credentials”. |
| 12 | Qualify the audit claim; fix “an AI issue” and “towards that”. Avoid the universal product-owner claim. |
| 13 | “Typical architecture”, “Restricted database account”, “Gateway-mediated access”. Avoid the absolute label “Secure scheme”. The right-hand “Security by architecture” heading has no content: remove it or fill the space. |
| 14 | “Open the `database-workshop` folder.” Replace `[x]` and add the precise connection/account to use. “Ask which companies are in the database” and “Ask for each company's average salary.” |
| 15 | State exactly what the policy should prohibit. Do not promise a particular model response. Replace the read-only-is-irrelevant lesson with the permissions/instructions distinction above. |
| 16 | “Create a restricted application role. Grant access to reviewed views/functions. Apply RLS where row restrictions are needed.” Creating a user alone is not protection. |
| 17 | “Creating a user”, not “an user”. Specify RLS bypass, not all permissions. “SELECT limits writes; row and column policies limit what can be read.” |
| 18 | “Create integration tests that check these rules.” “Companies to which the user belongs.” Explain trusted transaction context, show the runnable test command and distinguish RLS from aggregate-only access. |
| 19 | Use “Protection through architecture” consistently. Mention the optional broker extension so the later ninth topic is unsurprising. |
| 20 | The sequence is too small to read in a room. Split into model request, data retrieval and model answer, or reveal one section at a time. Export without editor selection marks. |
| 21 | “Let's build the security layers one at a time.” Add the shared practice-folder instructions before moving to stage 1. |
| 22 | “Limit what the agent's commands can do.” Prefer “mistaken or unsafe commands” to assuming malicious intent. Explain that container root is not automatically host root. |
| 23 | Replace `—practice` with `--practice`. Use a monospaced command box. Tell students which `.practice` file to edit. |
| 24 | Good explanation. Qualify temporary storage as the configured tmpfs mounts, rather than all container storage. Explain that read-only credentials remain readable. |
| 25 | Fix the CLI dash. Use the same visual weights for commands, task and expected result; currently everything is bold. |
| 26 | Keep the concrete home-folder example. Explain that the real lab demonstrates a harmless README mount, not personal-file exposure. |
| 27 | Fix the CLI dash. Add the missing result line: “PASS: the host README is absent and no host bind mount remains on the agent.” |
| 28 | Explain that stage 4 establishes the route; authentication and company restrictions come later. |
| 29 | Change `— practice` to `--practice`, with no internal space. Reference the gateway service implementation to copy/configure. |
| 30 | Correct the claim that individual salaries are already blocked. Stage 5 still permits them through the approved function. |
| 31 | Fix the CLI dash. The expected result correctly states that individual salaries remain available; retain that qualification. |
| 32 | Replace “Aggregates (view)” with “Aggregates (function)”. Defer verified membership to stage 7. Mention the small-group rule. |
| 33 | Fix the CLI dash. Add “Other companies are still reachable until the identity layer.” |
| 34 | Replace the team-level example with another company's data so it matches the implemented model. |
| 35 | Command syntax is correct. Put function names and parameters in monospace and maintain the code's exact spelling. |
| 36 | “Record allowed and denied requests without logging sensitive values.” The current API is read-only, so distinguish implemented access auditing from hypothetical change auditing. |
| 37 | Fix the CLI dash. Explain that the failure check is temporary and restores the pre-test grant state. |
| 38 | Good explanation. A request/output cap limits usage; it is not a guaranteed currency spending cap. |
| 39 | Delete `prepare 9`. Keep the local-test qualification. Format the long unittest command as a single command box with safe wrapping. |
| 40 | “Some bugs are easiest to reproduce using production-like data.” “PII and other confidential data.” Replace the blanket claim that preprod is usually read-only/unavailable with the actual access scenario you want to teach. |
| 41 | “The refresh must stop when a new column has no reviewed processing rule.” Do not imply the schema check alone detects PII newly stored in an unchanged text/JSON column. |
| 42 | “Generate synthetic data”, not “synthetication”. “Integrated into the refresh code”, not “embedded to the code”. Explain that retained IDs preserve linkage risk. |
| 43 | The large diagram is useful as a reference, but too dense for detailed projection. Split the identity/employment path from payroll/claims. Reconcile its ten-table model with the three-table cloning exercise. |
| 44 | Correct the heading to “Anonymisation vs pseudonymisation”. The table's distinction is useful; enlarge it and add that the clone is not proven anonymous. |
| 45 | “Stable tokens generated with keyed HMAC.” “Preserves joins” for foreign keys. “Stop publication until reviewed” for new columns. Fixed-value replacement is accurately described as masking. |
| 46 | Supply actual setup commands and database/schema names. Do not start by exposing a full raw clone as the final developer-visible copy. |
| 47 | “Create a method that replaces ... with keyed HMAC tokens.” Replace regex-only acceptance with token/value/relationship checks. Use “integration test”. |
| 48 | `employment_contract`, not `employee_contract`. “Exactly one matching person.” “The test must run against preprod.” Use table names from the chosen dataset and address constrained update order. |
| 49 | Fix `psedo-prod` -> `preprod`. Use `Person`/`Anonymous` consistently. Change 2020-01-01 to 2000-01-01. “Replace names because this exercise does not need the originals”, not because the absence of a foreign key proves it is safe. |
| 50 | “Exercise 4: Preserve relational integrity”, not “Unchange”. “Relationships between people, contracts and companies.” Verify full foreign-key integrity rather than only sampled joins. |
| 51 | “Stop on unreviewed schema changes”. Fix `scheme` -> `schema` and `coluns` -> `columns`. Separate the clean-baseline passing test from the intentional failure after adding a column. Use the actual table name. |
| 52 | “Build a reusable refresh pipeline.” Compare source snapshots and validate the explicit contract; do not require identical source/target schemas. Publish into the existing preprod target atomically. |
| 53 | Put the command in a code box without bullets. Identify original versus transformed schemas and provide the after/compare commands. State where to open the report and that matches are candidates. |
| 54 | “The data is partially masked”, not “anonymised”. Prefer a fictional person; do not assert a unique identity without demonstrating the matching evidence. “Several clues may still identify the person.” |
| 55 | “More information than is needed.” Use “Base64”. Explain that retention depends on the use case; the proposed archive is 28 days. The main issue is retained sensitive information, not merely the volume of log storage. |
| 56 | “What will we build?” Fix `exercies` -> `exercises`. “One Kubernetes node / multiple nodes”. State which parts run today and which are architecture discussions. |
| 57 | Replace the unofficial NLP-mode hierarchy with detection methods and deployment choices. Distinguish Analyzer from Anonymizer. Remove “tiny” for the supplied large model. |
| 58 | Replace broad language-accuracy claims with measured fixture results. Remove the empty bullet. Explain the custom English-pipeline recognisers do not provide Lithuanian NER. |
| 59 | “Fluent Bit”. Lua is an optional custom filter; configuration is not generally written only in Lua. |
| 60 | Label the picture as target architecture. Add an actual Exercise 1 startup/check slide; the current Presidio exercise is a static corpus, not this continuous collector/archive app. |
| 61 | “Exercise 2: Log processing with Fluent Bit.” Explain original-copy versus working-copy routing. Mark forensic storage and Presidio fallback as extensions that need implementing. |
| 62 | “Fluent Bit as a log processor.” Enlarge the diagram instead of leaving much of the slide unused. Explain that the Presidio adapter forwards processed events; a normal HTTP output does not splice returned data back into Fluent Bit filters. |
| 63 | The diagram visibly covers the title. Put the title above the diagram. Label it conceptual; define node/cluster briefly and note that a single node has no node redundancy. |
| 64 | Remove visible editor selection handles/grid. Label the two-cluster/two-data-centre design as conceptual. Explain that Presidio replicas run on nodes behind a Service, while Fluent Bit collects per node. |
| 65 | “Optional challenge: deploy the pipeline locally on Kubernetes.” Name the prerequisite environment and provide manifests, starter instructions and acceptance criteria before presenting it as runnable. Otherwise make it a design discussion. |
| 66 | “Thank you for your attention!” Add the repository link and one takeaway: “Guide behaviour with prompts; enforce access and validate outputs with code.” |

## Teaching And Layout Suggestions

1. Put the active repository folder, database/schema and account on every
   exercise slide. The database, agent, refresh and log workshops are isolated
   setups; make the transitions visible.
2. Use the same exercise template: **Prepare / Ask the agent / Check / Expected
   result**. Put copyable full prompts and commands behind a QR/link rather
   than shrinking them onto the slide.
3. Make expected failures explicit: default Presidio validation, new unmapped
   columns, invalid privacy policy and blocked access are successful lessons,
   not unexplained broken environments.
4. Add a small red/green result slide after each main block. Show the actual
   measured output and what it does not establish; do not invent detection
   percentages or promise every model will ignore an instruction file.
5. Use a code font and disable smart punctuation for commands. Avoid bullet
   markers inside multiline commands and ensure visible wrapping remains safe
   to copy from the PDF.
6. Prebuild Docker images/models or ask attendees to do so before 09:00.
   Fifteen minutes for first-time setup is risky given the large model download
   and multiple images. The 09:15-10:15 block is ambitious for instruction-file
   exploration, RLS, and eight implementation/check cycles; choose core layers
   for hands-on work and demonstrate the others if needed.
7. Add short breaks between the 09:15-13:00 blocks. Make the core/optional split
   explicit so students can finish a coherent exercise without Kubernetes.
8. Export diagrams cleanly as SVG/PDF/PNG from draw.io instead of taking editor
   screenshots. Expand dense diagrams across several slides or reveal stages
   progressively. Keep the complete diagram as a handout.
9. Avoid claims of universal security. Name the account, data path, output and
   threat being controlled. RLS, redaction, hashing, cohort thresholds and API
   access controls answer different questions.

## Repository Evidence

The following inspected files ground the implementation-specific findings:

- [Stage runner](/Users/mantasdamijonaitis/programming/devdays-data-privacy-workshop/agent-security-workshop/layers.py): valid stages, prepare/check behavior and practice isolation.
- [Implementation guide](/Users/mantasdamijonaitis/programming/devdays-data-privacy-workshop/agent-security-workshop/IMPLEMENTATION.md): completed references versus learner starters; separate connectivity review.
- [Stage functions](/Users/mantasdamijonaitis/programming/devdays-data-privacy-workshop/agent-security-workshop/layer_runtime/functions.sql) and [stage 5 grants](/Users/mantasdamijonaitis/programming/devdays-data-privacy-workshop/agent-security-workshop/layers/05-database/security.sql): row access versus open aggregates.
- [Protection guide](/Users/mantasdamijonaitis/programming/devdays-data-privacy-workshop/database-workshop/protection/README.md): RLS ownership, trusted transaction context and integration-test commands.
- [Original schema](/Users/mantasdamijonaitis/programming/devdays-data-privacy-workshop/database-workshop/schema.sql): private/public graph and foreign keys.
- [Tracer](/Users/mantasdamijonaitis/programming/devdays-data-privacy-workshop/database-workshop/trace_data.py): original-schema default, candidate semantics and target-layout assumptions.
- [Refresh exercise](/Users/mantasdamijonaitis/programming/devdays-data-privacy-workshop/schema-refresh-workshop/EXERCISE.md), [target definition](/Users/mantasdamijonaitis/programming/devdays-data-privacy-workshop/schema-refresh-workshop/preprod_schema.py) and [transform implementation](/Users/mantasdamijonaitis/programming/devdays-data-privacy-workshop/schema-refresh-workshop/clone.py): actual model, HMAC email format, masking constants and publication process.
- [Presidio guide](/Users/mantasdamijonaitis/programming/devdays-data-privacy-workshop/presidio-workshop/README.md): static corpus, language/model setup and deliberately failing baseline.
- [Running pipeline guide](/Users/mantasdamijonaitis/programming/devdays-data-privacy-workshop/log-pipeline-workshop/README.md): Fluent Bit/Lua implementation and current limits.
- [Diagram guide](/Users/mantasdamijonaitis/programming/devdays-data-privacy-workshop/docs/logging-processes/README.md): target architecture and explicitly undeployed extensions.
