# 2. Related Work

This chapter reviews the literature behind the thesis's central framing: that
data-quality degradation should be traced to its downstream, decision-level cost,
not just to model accuracy. It also covers the literature behind the bounded
agent extension in §4.6, and closes with the gap this thesis fills.

**Data-quality propagation.** Sambasivan et al. (2021, CHI), *"Data Cascades in
High-Stakes AI,"* name and document compounding, downstream consequences of
upstream data-quality issues, the closest precedent for this thesis's
propagation chain (raw data → forecast → decision → cost). Where they document
cascades qualitatively across many deployments, this thesis instruments one
pipeline end to end and quantifies the cascade in monetary terms, under
controlled, repeatable corruption.

**Production data validation.** Breck et al. (2019, SysML/MLSys), *"Data
Validation for Machine Learning"* (TFDV), and Schelter et al. (2018, VLDB),
*"Automating Large-Scale Data Quality Verification"* (Deequ), establish that data
quality can be checked declaratively and continuously at serving time, not only
once at training time. The per-class detectors built for the BikeMi feed
(`src/validation.py`) instantiate the same paradigm for a domain neither paper
addresses.

**Leakage.** Kapoor and Narayanan (2023, *Patterns*), *"Leakage and the
Reproducibility Crisis in ML-based Science,"* show how undetected leakage has
inflated reported performance across empirical ML research. This motivates the
thesis's leakage protocol (§4.2): chronological splits, a model trained once and
frozen, and corruption signals never used as features.

**Production data management.** Polyzotis et al. (2017, SIGMOD), *"Data
Management Challenges in Production Machine Learning,"* frame the broader
collection-to-monitoring problem this thesis's acquisition-to-decision chain sits
inside.

**Bike-sharing decisions vs. forecasts.** Gammelli et al. (2022, *Transp. Res.
Part C* 138), show that predictive and prescriptive performance can diverge in
bike-sharing inventory management: a forecast that scores well can still produce
a poor decision. This supports treating decision- and cost-level outcomes, not
forecast accuracy, as this thesis's primary measure (§1.2), including under
degraded data, which they do not consider.

**Systematic quality perturbation.** Mohammed et al. (2025, *Information Systems*
132; preprint Budach et al., arXiv:2207.14529) perturb data-quality dimensions
systematically and measure the resulting change in model metrics, but stop
there. No work surveyed here continues the chain into an explicit cost function
evaluated under a frozen decision rule; that continuation is this thesis's
specific contribution.

**Quality-aware agents.** SmartFlow (arXiv:2601.00868) and RideAgent
(arXiv:2505.06608) place a grounded LLM downstream of an optimiser in fleet
operations, but neither tests behaviour under degraded input, the condition
this thesis's pre-registered but descoped agent extension (§4.6) targeted. Its
evaluation protocol (groundedness, warning
appropriateness, abstention correctness, recommendation consistency) is adapted
from two abstention benchmarks, AbstentionBench (arXiv:2506.09038) and
AgentAbstain (arXiv:2607.10059), narrowed to one domain and one manipulation
rather than proposed as a new general benchmark.

**The gap.** Data-quality cascades and declarative validation (above) are
established separately from bike-sharing's predictive/prescriptive divide and
from quality-aware agents in fleet operations. No work joins all three: a
per-class fault injection on a live feed's own data, carried through a frozen
decision rule into an explicit cost. Agent quality-awareness was pre-registered
as a bounded final extension (§4.6) but is descoped for this thesis; the
propagation chain itself is this thesis's contribution.
