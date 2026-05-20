***REMOVED*** Skill: test-driven-development

Use for features, bug fixes, refactors, and behavior changes.

Required workflow:

1. Write the smallest failing test for the target behavior.
2. Run it and confirm the expected RED failure.
3. Write the minimal implementation to pass.
4. Run the focused test and confirm GREEN.
5. Refactor only after tests are green.
6. Expand tests only where risk or integration boundaries require it.

If a test cannot be written, the agent must explain why in the PR and provide a
manual or command-based verification alternative.
