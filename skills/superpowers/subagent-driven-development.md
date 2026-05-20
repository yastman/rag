***REMOVED*** Skill: subagent-driven-development

Use when an approved plan has independent slices that can be delegated without
overlapping files or responsibilities.

Required workflow:

- reserve disjoint files or subsystems for each worker;
- give each worker the relevant issue number, skill list, safety boundaries,
  expected tests, and report path;
- verify every worker report before accepting it;
- integrate only after focused checks pass.

Do not use this for tightly coupled changes where one worker's next step depends
on another worker's unfinished result.
