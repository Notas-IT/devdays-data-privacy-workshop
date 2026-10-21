# Learner Task: Audit

Business task: calculate company 1's average salary. The final answer should
be a summary, without collecting or returning individual salaries unnecessarily.

Starting reference: `07-identity`. This folder is the completed reference for
this stage; use it to check your own implementation of the change.

Implement and explain this change:

- Record allowed and denied requests and withhold the average during a real audit-write failure.
- Keep every protection from earlier stages working.
- Run `python3 agent-security-workshop/layers.py test 8` from the repository root.
- Explain the remaining exposure: The host, Docker administrator, presenter and gateway implementation remain trusted. This is a local synthetic lab, not proof of complete security.

Inspect `docker-compose.yml` for process, files, host and network boundaries;
inspect `security.sql` for database grants and the shared gateway for the API.
No paid model call is needed to verify this stage.
