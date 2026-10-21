# Learner Task: Identity

Business task: calculate company 1's average salary. The final answer should
be a summary, without collecting or returning individual salaries unnecessarily.

Starting reference: `06-aggregates`. This folder is the completed reference for
this stage; use it to check your own implementation of the change.

Implement and explain this change:

- Keep the allowed company average working while rejecting anonymous requests and another company.
- Keep every protection from earlier stages working.
- Run `python3 agent-security-workshop/layers.py test 7` from the repository root.
- Explain the remaining exposure: Requests are still not durably audited. A correct authorization decision alone does not leave a record.

Inspect `docker-compose.yml` for process, files, host and network boundaries;
inspect `security.sql` for database grants and the shared gateway for the API.
No paid model call is needed to verify this stage.
