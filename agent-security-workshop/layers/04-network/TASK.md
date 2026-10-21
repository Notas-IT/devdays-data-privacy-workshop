# Learner Task: Network

Business task: calculate company 1's average salary. The final answer should
be a summary, without collecting or returning individual salaries unnecessarily.

Starting reference: `03-host`. This folder is the completed reference for
this stage; use it to check your own implementation of the change.

Implement and explain this change:

- Move the calculation from direct SQL to the API and block direct TCP by database name and IP.
- Keep every protection from earlier stages working.
- Run `python3 agent-security-workshop/layers.py test 4` from the repository root.
- Explain the remaining exposure: The API still has broad salary-table SELECT permissions and returns individual salaries without authenticating people.

Inspect `docker-compose.yml` for process, files, host and network boundaries;
inspect `security.sql` for database grants and the shared gateway for the API.
No paid model call is needed to verify this stage.
