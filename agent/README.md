# Agent comparison (SO3/H4)
Bounded final experiment: 8 operator questions x 3 conditions x 2 configurations
(quality-blind vs quality-aware) = 48 calls per run; 4 models x 3 runs, scored with a binary rubric fixed in
advance. Protocol: `PROTOCOL.md`. Code: `h4_agent.py` (`build` -> `run` -> `score`).
Scenarios (`scenarios.json`) are built from the class 5 injection and the frozen model;
results go to `reports/agent_h4_*`.
