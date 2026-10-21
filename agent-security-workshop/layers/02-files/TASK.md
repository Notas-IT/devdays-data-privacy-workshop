# Learner Task: Files

Business task: calculate company 1's average salary. The final answer should
be a summary, without collecting or returning individual salaries unnecessarily.

Starting reference: `01-agent-process`. This folder is the completed reference for
this stage; use it to check your own implementation of the change.

Implement and explain this change:

- Block writes to /workspace while allowing temporary work under /tmp.
- Keep every protection from earlier stages working.
- Run `python3 agent-security-workshop/layers.py test 2` from the repository root.
- Explain the remaining exposure: The read-only host README is still visible; direct SQL and individual salary access remain.

Inspect `docker-compose.yml` for process, files, host and network boundaries;
inspect `security.sql` for database grants and the shared gateway for the API.
No paid model call is needed to verify this stage.
