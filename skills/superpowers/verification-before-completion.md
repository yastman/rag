***REMOVED*** Skill: verification-before-completion

Use before claiming an issue is complete, opening a PR, merging, or closing an
issue.

Required evidence:

- focused tests for the changed behavior;
- lint/type/build checks when the touched surface requires them;
- command output summary with pass/fail/skipped checks;
- explicit residual risks;
- explanation for any skipped tests.

Do not accept "should pass" or worker self-report as proof. The final PR or
issue comment must include fresh verification evidence from the current run.
