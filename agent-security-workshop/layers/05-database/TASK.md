# Learner Task: Database

Business task: calculate company 1's average salary. The final answer should
be a summary, without collecting or returning individual salaries unnecessarily.

Starting reference: `04-network`. This folder is the completed reference for
this stage; use it to check your own implementation of the change.

Implement and explain this change:

- Make arbitrary table reads fail even when using the gateway database account.
- Keep every protection from earlier stages working.
- Run `python3 agent-security-workshop/layers.py test 5` from the repository root.
- Explain the remaining exposure: Approved per-company individual rows remain readable. The caller can still choose any company because identity has not been added.

Inspect `docker-compose.yml` for process, files, host and network boundaries;
inspect `security.sql` for database grants and the shared gateway for the API.
No paid model call is needed to verify this stage.
