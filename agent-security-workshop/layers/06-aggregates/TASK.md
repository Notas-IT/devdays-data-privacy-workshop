# Learner Task: Aggregates

Business task: calculate company 1's average salary. The final answer should
be a summary, without collecting or returning individual salaries unnecessarily.

Starting reference: `05-database`. This folder is the completed reference for
this stage; use it to check your own implementation of the change.

Implement and explain this change:

- Allow an average while denying the individual-salaries endpoint and the one-person cohort.
- Keep every protection from earlier stages working.
- Run `python3 agent-security-workshop/layers.py test 6` from the repository root.
- Explain the remaining exposure: Anonymous callers can still request another company average. Minimum group size is not an anonymity guarantee.

Inspect `docker-compose.yml` for process, files, host and network boundaries;
inspect `security.sql` for database grants and the shared gateway for the API.
No paid model call is needed to verify this stage.
