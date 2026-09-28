# 2. Related Work

This chapter reviews the literature on tracing data-quality degradation to decision-level cost and on the assistant extension of §4.6, and closes with the gap this thesis fills.

**Data-quality propagation.** Sambasivan et al. (2021) name and document *data
cascades*: compounding, downstream consequences of upstream data-quality issues.
This is the closest precedent for the propagation chain studied here (raw data →
forecast → decision → cost). Where they document cascades qualitatively across
many deployments, this thesis instruments one pipeline end to end and quantifies
the cascade in monetary terms, under controlled, repeatable corruption.

**Production data validation.** Breck et al. (2019) and Schelter et al. (2018)
establish that data quality can be checked declaratively and continuously at
serving time, not only once at training time. The per-class detectors built for
the BikeMi feed  apply the same idea to a domain neither
paper addresses. Polyzotis et al. (2017) frame the broader
collection-to-monitoring problem within which this thesis's acquisition-to-decision
chain sits.

**Leakage.** Kapoor and Narayanan (2023) show how undetected leakage has inflated
reported performance across empirical machine-learning research. This motivates
the leakage protocol of §4.2: chronological splits, a model trained once and
frozen, and corruption signals never used as features.

**Bike-sharing decisions versus forecasts.** Gammelli et al. (2022) show that
predictive and prescriptive performance can diverge in bike-sharing inventory
management: a forecast that scores well can still produce a poor decision. This
supports treating decision- and cost-level outcomes, not forecast accuracy, as
the primary measure here (§1.2), including under degraded data, which they do
not consider.

**Systematic quality perturbation.** Mohammed et al. (2025) perturb data-quality
dimensions systematically and measure the resulting change in model metrics, but
stop there. None of the work surveyed here continues the chain into an explicit
cost function evaluated under a frozen decision rule; that continuation is this
thesis's specific contribution.

**Quality-aware assistants.** Sreevatsa K et al. (2025) and Jiang et al. (2025)
place a grounded language model downstream of an optimiser in fleet operations,
but neither tests its behaviour under degraded input, the condition targeted by
the assistant experiment of §4.6. Its evaluation criteria (groundedness, warning
appropriateness, abstention correctness, recommendation consistency) are adapted
from two abstention benchmarks (Kirichenko et al., 2025; Liu et al., 2026),
narrowed to one domain and one manipulation rather than proposed as a new general
benchmark.

**The gap.** Data-quality cascades and declarative validation are established
separately from bike-sharing's predictive/prescriptive divide and from
language-model assistants in fleet operations. None of the work reviewed here
joins them: a
per-class fault injection on a live feed's own data, carried through a frozen
decision rule into an explicit cost, with a bounded test of whether a
quality-aware assistant changes what an operator is told.
