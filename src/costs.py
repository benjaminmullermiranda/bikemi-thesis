"""Cost model and propagation metrics.

C_penalty = sum(critical station-hours) * C_miss,  C_miss = failed_pickups * (1-sigma) * revenue
C_transit = sum(preventive dispatches) * C_dispatch
Headline metrics: decision_flip_rate, delta_cost (per class x intensity), recovery_rate."""

def policy_cost(decisions, outcomes, params):
    raise NotImplementedError

def decision_flip_rate(decisions_clean, decisions_corrupted):
    raise NotImplementedError
