# Learner Task: Host

Business task: calculate company 1's average salary. The final answer should
be a summary, without collecting or returning individual salaries unnecessarily.

Starting reference: `02-files`. This folder is the completed reference for
this stage; use it to check your own implementation of the change.

Implement and explain this change:

- Remove host-file exposure without changing the process or filesystem protections.
- Keep every protection from earlier stages working.
- Run `python3 agent-security-workshop/layers.py test 3` from the repository root.
- Explain the remaining exposure: Direct SQL remains possible. Host credentials, SSH keys, Docker socket and host PID access are deliberately never supplied in any stage.

Inspect `docker-compose.yml` for process, files, host and network boundaries;
inspect `security.sql` for database grants and the shared gateway for the API.
No paid model call is needed to verify this stage.
