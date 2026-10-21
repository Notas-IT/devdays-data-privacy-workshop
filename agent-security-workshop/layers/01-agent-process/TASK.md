# Learner Task: Agent process

Business task: calculate company 1's average salary. The final answer should
be a summary, without collecting or returning individual salaries unnecessarily.

Starting reference: `00-plain-database`. This folder is the completed reference for
this stage; use it to check your own implementation of the change.

Implement and explain this change:

- Constrain the agent process while keeping the same direct SQL task working.
- Keep every protection from earlier stages working.
- Run `python3 agent-security-workshop/layers.py test 1` from the repository root.
- Explain the remaining exposure: The writable container filesystem, host README mount, direct SQL access and individual salary visibility remain.

Inspect `docker-compose.yml` for process, files, host and network boundaries;
inspect `security.sql` for database grants and the shared gateway for the API.
No paid model call is needed to verify this stage.
