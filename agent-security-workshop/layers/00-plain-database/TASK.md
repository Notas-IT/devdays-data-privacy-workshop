# Learner Task: Plain database

Business task: calculate company 1's average salary. The final answer should
be a summary, without collecting or returning individual salaries unnecessarily.

Starting reference: `none`. This folder is the completed reference for
this stage; use it to check your own implementation of the change.

Implement and explain this change:

- Read the synthetic salary table directly using the agent database credential.
- Keep every protection from earlier stages working.
- Run `python3 agent-security-workshop/layers.py test 0` from the repository root.
- Explain the remaining exposure: The process runs as root, the container filesystem is writable, a host README is mounted, and direct SQL exposes individual salaries.

Inspect `docker-compose.yml` for process, files, host and network boundaries;
inspect `security.sql` for database grants and the shared gateway for the API.
No paid model call is needed to verify this stage.
