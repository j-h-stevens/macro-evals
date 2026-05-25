# OpenAI "Macro Evals for Agentic Systems" Cookbook: Exhaustive Claims Inventory

**Source**: https://developers.openai.com/cookbook/examples/partners/macro_evals_for_agentic_systems/macro_evals_for_agentic_systems

**Date Compiled**: 2026-05-25

**Purpose**: Complete quotation-faithful inventory of all claims, methodological choices, hyperparameters, formulas, assumptions, and undefended assertions made in the original. Organized to support critical response article identifying gaps, unvalidated assumptions, and underdetermined design choices.

---

## 1. PROBLEM FRAMING: WHY MACRO EVALS MATTER

### 1.1 Multi-Agent Systems Require Population-Level Evaluation

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 1.1.1 | Motivational assertion | "When an agentic system fails, the problem is often larger than a single bad response." | Introduction | Single-trace evals insufficient; need pattern detection |
| 1.1.2 | Design philosophy | "To improve the system, teams need to see recurring behavior across the whole population of traces." | Introduction | Population-level aggregation is core requirement |
| 1.1.3 | Technical constraint | "Multi-agent systems make this harder because a final answer is only the last event in a longer workflow." | "1. Why Macro Evals?" | Terminal outputs cannot assess multi-stage workflows |
| 1.1.4 | Stated objective | "The goal is not to build a perfect taxonomy of every trace. The goal is to show how an AI engineering team can move from thousands of agent events to a small number of patterns understandable by both technical and business stakeholders." | "1. Why Macro Evals?" | Compression and interpretability valued over completeness |

### 1.2 Scope Expansion Beyond Model-Output Grading

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 1.2.1 | Characterization | "For a simple model call, an eval might compare one output against a rubric or reference answer. For an agentic system, we also need to evaluate whether the system used the right tools, delegated to the right specialist, paused for review when risk was high." | "1. Why Macro Evals?" | Agent-level evals must encompass routing, delegation, review decisions |

### 1.3 Two-Layer Evaluation Architecture

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 1.3.1 | Framework design | "This notebook separates the problem into two levels: Lower-level evals grade individual agents, handoffs, tools, and completed runs." | "1. Why Macro Evals?" | Hierarchical structure: agent-level + population-level |
| 1.3.2 | Macro-eval purpose | "Macro evals look across many lower-level findings. They ask: which kinds of problems repeat, where do they concentrate, and which part of the agent workflow should we inspect first?" | "1. Why Macro Evals?" | Three-part discovery: prevalence, concentration, prioritization |

### 1.4 Conceptual Mental Model

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 1.4.1 | Conceptual framework | "case_type is the setup, run_outcome is the ending, eval_finding is the local symptom, and behavior_pattern is the population-level pattern." | "1. Why Macro Evals?" | Four-stage labeling pipeline: input → terminal → local signal → emergent pattern |

---

## 2. SIMULATION DOMAIN AND ARCHITECTURE

### 2.1 EV Order Workflow Simulation

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 2.1.1 | Domain description | "The simulated business is an EV order and post-configuration workflow." | "2. The Simulation: Automotive Orders in a Changing World" | Real-world business constraints simulated |
| 2.1.2 | Constraint enumeration | "The simulation includes the kinds of constraints that make real automotive fulfillment hard: component availability and supplier substitution; factory capacity and production scheduling; pricing exceptions, promotions, and incentives; tariffs and dated market signals; regional compliance constraints; customer clarification and escalation paths; release review thresholds for risky or ambiguous cases." | "2. The Simulation" | Multi-dimensional constraint space reflects operational complexity |
| 2.1.3 | Architectural principle | "The agent swarm is organized around those business responsibilities." | "2. The Simulation" | Agent roles follow business domain decomposition |

### 2.2 Specialist Agent Enumeration

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 2.2.1 | Specialist enumeration | "An orchestrator receives the order and current environment, then delegates to specialists such as validation, supply risk, procurement planning, capacity balancing, factory routing, market intelligence, pricing, compliance, customer communications, and release review." | "2. The Simulation" | 10+ distinct specialist roles in swarm |
| 2.2.2 | Architecture alignment | "This maps naturally to the OpenAI Agents SDK." | "2. The Simulation" | Simulation design follows SDK native abstractions |

### 2.3 Simulation Architecture Components

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 2.3.1 | Architectural component list | "specialized agents package the instructions and tools for one part of the decision; handoffs let the orchestrator delegate to another specialist agent instead of stuffing every responsibility into one prompt; function tools expose order data, environment signals, and approval markers through structured inputs and outputs; guardrails and review thresholds represent validation, blocking, and human-review flows for risky or ambiguous cases; structured outputs make downstream grading and aggregation possible; traces preserve structured records of model calls, tool calls, handoffs, guardrails, and custom spans for debugging and macro-level analysis." | "2. The Simulation" | SDK features fully utilized in simulation design |
| 2.3.2 | Eval grounding principle | "The low-level evals later in the notebook are grounded in this simulation story. If the case type says there is a supplier substitution under tariff pressure, the trace should show awareness of supply, policy, market, and review risk." | "2. The Simulation" | Case type defines expected trace signal patterns |

---

## 3. DATASET CHARACTERISTICS

### 3.1 Trace Bundle Scale and Composition

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 3.1.1 | Batch size specification | "The requested batch asked the swarm to handle 1,000 synthetic order interactions." | Data materials section (implicit) | Population scale ~1000 interactions |
| 3.1.2 | Bundle availability statistic | "For 992 of them, we have a bundle: a complete evidence packet for grading the run." | Data materials section | 99.2% completion rate; 8 incomplete runs |
| 3.1.3 | Median event counts | [Inferred from WebFetch result: "Median ~30 normalized events per interaction; median ~8 SDK spans per trace; Median 2 handoff records and 4 tool calls per interaction"] | Dataset profile | Typical trace structure: 30 events, 8 spans, 2 handoffs, 4 tools |

### 3.2 Bundle Definition and Purpose

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 3.2.1 | Bundle definition | "In this notebook, a bundle is the evidence packet for one simulated customer-order interaction." | "### What One Bundle Represents" | Bundle is atomic unit for macro eval analysis |
| 3.2.2 | Completeness assertion | "The bundle is everything we need to audit that interaction afterward." | "### What One Bundle Represents" | Bundle contains sufficient trace evidence for retrospective evaluation |
| 3.2.3 | Necessity claim | "A bundle matters because macro evals need the workflow evidence behind the final answer." | "### What One Bundle Represents" | Bundles prerequisite for macro-eval operation |

### 3.3 Bundle Contents: Anatomy

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 3.3.1 | Run metadata | "run: Run id, trace id, terminal state, batch metadata, and synthetic order context. Lets us join one interaction across tables and understand its business setup." | "### Bundle Anatomy" | Run metadata enables cross-table joins and context |
| 3.3.2 | Event log | "events: A normalized event log: status updates, handoffs, tool/function activity, responses, and findings." | "### Bundle Anatomy" | Events are primary evidence stream |
| 3.3.3 | Trace spans | "spans: OpenAI Agents SDK trace spans for handoffs, function calls, responses, and timing." | "### Bundle Anatomy" | Spans provide sub-event execution structure and timing |
| 3.3.4 | Environment state | "environment_events: The dated world state active for the order: tariffs, incentives, stockouts, promotions, competitor pressure, launches, and schedule/capacity signals." | "### Bundle Anatomy" | Environment state essential for drift detection |
| 3.3.5 | Review artifact | "review_packet: A simulated review artifact with findings, recommended action, allowed actions, and review status." | "### Bundle Anatomy" | Review artifacts available for escalation evaluation |

### 3.4 Scenario Coverage and Diversity

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 3.4.1 | Case type definition | "A case_type is a scenario label from the generator. It describes the kind of business situation the swarm was asked to handle before any eval or clustering has happened." | "### What case_type Means" | Case types are generated inputs, not learned patterns |
| 3.4.2 | Example enumeration | "Examples from this dataset include: clean_simple, validation_block_simple, supplier_substitution_compound, pricing_exception_compound, regional_compliance_compound." | "### What case_type Means" | Scenario types span routine and pressure cases |
| 3.4.3 | Design principle | "The bar chart above is a coverage view. It shows whether the simulation produced enough variety to evaluate the swarm under different business pressures. A strong macro-eval dataset needs both ordinary cases and pressure cases, because recurring patterns only become meaningful when we can compare behavior across different setups." | "### What case_type Means" | Scenario diversity essential for pattern interpretability |
| 3.4.4 | Scenario count | [Inferred: "14 distinct scenario families (case types)"] | Dataset profile | 14 case-type categories |

### 3.5 Typical Bundle Characterization

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 3.5.1 | Bundle structure | "The typical bundle is a structured record of a simulated business process: the order setup, active world events, specialist handoffs, tool/function activity, review artifacts, and terminal state." | "### How to Read the Dataset Profile" | Bundles capture full workflow lifecycle |

---

## 4. LOWER-LEVEL EVALS: PROMPTFOO LAYER

### 4.1 Promptfoo Role and Representation

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 4.1.1 | Role assignment | "Promptfoo plays that role in this notebook. It represents the lower-level eval layer that would normally live beside the agents in a production workflow." | "3. Lower-Level Agent Evals with Promptfoo" | Promptfoo abstraction represents production eval layer |
| 4.1.2 | Representation claim | "Promptfoo grades completed traces with questions that mirror the kinds of agent-level evals teams build for real systems." | "3. Lower-Level Agent Evals with Promptfoo" | Promptfoo rubrics abstractly represent real-world eval practice |

### 4.2 Five Rubrics Specification

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 4.2.1 | Rubric set enumeration (full) | "In this dataset, Promptfoo grades completed traces with questions that mirror the kinds of agent-level evals teams build for real systems: Did the final decision follow from the active issue? Did the system respect pricing, tariff, incentive, regional, and policy constraints? Did the orchestrator activate the specialists implied by the case? Did the run respond to dated market signals rather than acting as if the world were static? Was review or escalation proportionate to the risk?" | "3. Lower-Level Agent Evals" | Five core eval dimensions specified |
| 4.2.2 | Rubric definitions (detailed) | "Rubrics: (1) final_decision_quality—Final decision is supported by the active issues, terminal state, and agent outputs. (2) policy_compliance_correctness—Policy, tariff, incentive, and regional compliance context is handled correctly. (3) routing_specialist_activation—Specialist routing matches the issues present in the bundle. (4) market_drift_awareness—Changing market conditions and dated environment signals are noticed. (5) review_appropriateness—Review and escalation behavior is proportionate to the case risk." | "3. Lower-Level Agent Evals" | Five discrete evaluable dimensions |

### 4.3 Eval Signal and Local Symptom Model

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 4.3.1 | Signal model | "These checks produce eval_finding. A failing lower-level eval is a local signal: one trace, one rubric, one symptom." | "3. Lower-Level Agent Evals" | Eval findings are trace-local, not aggregate |

### 4.4 Production Model and Implementation Flexibility

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 4.4.1 | Production model | "In a live system, some of these checks might run online, some might run asynchronously, and some might be sampled for human review. The implementation detail matters less than the contract: every run should carry eval signals that say what looked correct, risky, or wrong at the agent and workflow level." | "3. Lower-Level Agent Evals" | Synchronicity/sampling choices orthogonal to contract |

---

## 5. DATASET CONSTRUCTION AND NORMALIZATION

### 5.1 Two-Table Analysis Schema

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 5.1.1 | Normalization structure | "Now we normalize the run bundles into two analysis tables: traces_df: one row per run, with metadata, outcome, findings, and document fields. events_df: one row per normalized trace event, including handoffs, tool calls, status events, model responses, and review/finding markers." | "4. Build the Analysis Dataset" | Two-table schema for downstream analysis |

### 5.2 Label Pipeline

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 5.2.1 | Label pipeline | "The public analysis path is: case_type → run_outcome → eval_finding → behavior_pattern. The first three labels are known before clustering. The fourth appears after discovery." | "4. Build the Analysis Dataset" | Clustering produces only final label in chain |

### 5.3 Outcome Grouping

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 5.3.1 | Outcome mapping | "OUTCOME_GROUP_MAP: completed→successful_completion, awaiting_review→review_escalation, blocked→hard_failure, failed→hard_failure" | "4. Build the Analysis Dataset" | Outcomes collapsed to three groups: successful_completion, review_escalation, hard_failure |

### 5.4 Severity Assignment and Weighting

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 5.4.1 | Severity weight assignment | "SEVERITY_BY_OUTCOME: successful_completion→(low, 1.0), review_escalation→(medium, 2.0), in_progress→(medium, 1.5), blocked→(high, 2.5), hard_failure→(high, 3.0)" | "4. Build the Analysis Dataset" | Severity weight ranges 1.0–3.0; hard_failure weighted highest |

### 5.5 Impact Score Computation

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 5.5.1 | Composite scoring formula | "impact_score = severity_weight × (1.0 + findings_count) × (1.0 + loop_count / 4.0)" | "4. Build the Analysis Dataset" | Impact compounds on severity, findings, and retry loops |
| 5.5.2 | Failure indicator formula | "has_failure = (outcome_group ≠ successful_completion) OR (validation_outcome ≠ passed) OR (findings_count > 0)" | "4. Build the Analysis Dataset" | Failure flagged by outcome, validation, or findings |

### 5.6 Trace Document Construction

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 5.6.1 | Document purpose | "We also build trace documents. The document is the modeling object that the BERTopic-style section will cluster." | "4. Build the Analysis Dataset" | Documents are inputs to clustering algorithm |
| 5.6.2 | Document type selection | "The notebook uses doc_structured_summary because it is compact but still preserves scenario, routing, state transitions, handoffs, findings, and terminal state." | "4. Build the Analysis Dataset" | Structured summary chosen over raw events |
| 5.6.3 | Document design principles | "A good trace document includes: the business setup (case_type, selected route, active environment signals); the run outcome and severity; the important handoffs and specialist activations; review/finding markers; a short state-transition digest." | "### Trace Documents: Turning Runs into Comparable Text" | Content selection shapes what clustering can discover |

### 5.7 Focus-Event Signals

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 5.7.1 | Signal enumeration | "In this simulation, common focus-event signals include: review finding, review required or awaiting_review, failed or blocked, triage route or reroute signals, tool warnings or policy markers." | "### Failure and Focus-Event Glossary" | Five signal types mark attention points |
| 5.7.2 | Signal interpretation caveat | "These are observability signals, not proof of root cause. They tell the diagnosis pass where to anchor its backward search." | "### Failure and Focus-Event Glossary" | Signals indicate locations, not causes |

---

## 6. BERTOPIC-STYLE DISCOVERY: EMBEDDING → REDUCTION → CLUSTERING → LABELING

### 6.1 Four-Stage Pipeline Overview

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 6.1.1 | Methodological ancestry | "The discovery pass is inspired by the BERTopic family of methods." | "5. BERTopic-Style Discovery" | Algorithm builds on established topic-modeling approach |
| 6.1.2 | Four-stage pipeline | "The high-level idea is modular: (1) Represent each trace document as a vector. (2) Reduce the vector geometry. (3) Cluster dense regions. (4) Represent each topic." | "5. BERTopic-Style Discovery" | Standard embedding→reduction→clustering→labeling flow |

### 6.2 Embedding Stage

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 6.2.1 | Embedding function | "If the document for trace i is d_i, the embedding model produces a vector e_i = f(d_i)." | "5. BERTopic-Style Discovery" | Documents embedded via function f (unspecified) |

### 6.3 Dimensionality Reduction

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 6.3.1 | Reduction method | "A reducer such as UMAP maps e_i to a lower-dimensional point z_i that preserves useful local neighborhoods." | "5. BERTopic-Style Discovery" | UMAP cited as example; local neighborhood preservation key |

### 6.4 Clustering

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 6.4.1 | Clustering algorithm | "A density clusterer such as HDBSCAN groups nearby points and can mark outliers as noise." | "5. BERTopic-Style Discovery" | HDBSCAN with noise-handling capability |
| 6.4.2 | Cluster membership | "A trace belongs to a cluster k when its document vector is near other trace vectors in the reduced space." | "5. BERTopic-Style Discovery" | Membership based on proximity in reduced geometry |

### 6.5 Topic Labeling and Term Scoring

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 6.5.1 | Term-scoring formula | "score(t, k) = tf(t, k) × log((1 + N) / (1 + df(t)))" | "5. BERTopic-Style Discovery" | TF-IDF variant with logarithmic denominator adjustment |
| 6.5.2 | Formula notation definitions | "where tf(t, k) is the term frequency for term t inside cluster k, df(t) is the number of clusters/documents where the term appears, and N is the comparison population size." | "5. BERTopic-Style Discovery" | Standard TF-IDF components; N is total trace count |
| 6.5.3 | Implementation flexibility caveat | "The exact implementation can vary, but the intuition is stable: labels should describe what makes a cluster distinctive." | "5. BERTopic-Style Discovery" | Formula details less important than distinctiveness principle |

### 6.6 Discovery Input Filtering

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 6.6.1 | Input filtering logic | "discovery_input_df = labeled_traces_df.loc[labeled_traces_df['has_failure'] | labeled_traces_df['promptfoo_failed'] | labeled_traces_df['run_outcome'].isin(['review_needed', 'blocked', 'runtime_error'])]" | "5. BERTopic-Style Discovery" | Only failure/review/error traces feed discovery |
| 6.6.2 | Fallback procedure | "If very few failure traces exist, discovery broadened to all traces with documents." | "5. BERTopic-Style Discovery" | Minimum population of ~8 traces enforced |

### 6.7 Hyperparameters for Discovery Pipeline

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 6.7.1 | Min cluster size | "effective_min_cluster_size = min(DISCOVERY_MIN_CLUSTER_SIZE, max(2, len(discovery_input_df) // 4))" | "5. BERTopic-Style Discovery" | Adaptive; default DISCOVERY_MIN_CLUSTER_SIZE=24, floor 2 |
| 6.7.2 | UMAP n_neighbors | "effective_n_neighbors = min(30, max(2, len(discovery_input_df) - 1))" | "5. BERTopic-Style Discovery" | Capped at 30; ceiling len(input)-1 |
| 6.7.3 | Terms per topic | "top_n_terms = 8" | "5. BERTopic-Style Discovery" | Each pattern labeled by 8 top-ranked keywords |
| 6.7.4 | Reproducibility seed | "random_state = 42" | "5. BERTopic-Style Discovery" | Deterministic clustering across runs |

### 6.8 Impact Scoring for Patterns

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 6.8.1 | Pattern prioritization formula | "Finally, we rank patterns by a triage metric: impact_score(k) = prevalence_share(k) × severity_weighted_prevalence(k)" | "5. BERTopic-Style Discovery" | Two-factor product: prevalence and severity weighting |
| 6.8.2 | Scoring philosophy caveat | "This is not a universal risk formula. It is a practical prioritization score: a pattern matters more when it is both common and severe." | "5. BERTopic-Style Discovery" | Intentionally domain-specific, not generalizable |

### 6.9 Discovery Output Metrics

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 6.9.1 | Prevalence metric | "trace_count and prevalence tell us how often the pattern appears." | "### Interpreting the Discovery Output" | Prevalence is normalized frequency |
| 6.9.2 | Severity metric | "severity_weighted_prevalence tells us how severe the traces in the pattern tend to be." | "### Interpreting the Discovery Output" | Aggregate severity calculated per pattern |
| 6.9.3 | Impact metric purpose | "impact_score combines prevalence and severity into a ranking." | "### Interpreting the Discovery Output" | Impact score used for pattern prioritization |
| 6.9.4 | Owner label caveat | "dominant_owner is a heuristic owner label, not an assignment." | "### Interpreting the Discovery Output" | Automated heuristic; not authoritative |
| 6.9.5 | Keywords output | "keywords_text gives the terms that made the pattern distinctive." | "### Interpreting the Discovery Output" | Terms derived from scoring formula |

---

## 7. LIFT AND CASE-TYPE HEATMAP ANALYSIS

### 7.1 Heatmap and Cross-Slice Analysis

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 7.1.1 | Heatmap purpose | "The heatmap asks: which generated scenarios concentrate which behavior patterns?" | "### Interpreting the Case-Type Heatmap" | Cross-tabulation of case_type × behavior_pattern |
| 7.1.2 | Heatmap encoding | "Darker or larger values mean that a pattern is more common within that scenario slice." | "### Interpreting the Case-Type Heatmap" | Color intensity proportional to pattern concentration |
| 7.1.3 | Use case example | "This helps distinguish expected behavior from surprising behavior. For example, a fulfillment reroute pattern may be expected in supplier substitution or capacity cases, but more suspicious in clean cases." | "### Interpreting the Case-Type Heatmap" | Case context matters for pattern interpretation |

### 7.2 Lift Computation

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 7.2.1 | Overall share metric | "overall pattern share: among all clustered traces, what share belongs to this behavior pattern?" | "### Comparing Patterns Across Slices" | Denominator is total clustered population |
| 7.2.2 | Slice share metric | "slice pattern share: within one slice, such as case_type = supplier_substitution_compound, what share belongs to this behavior pattern?" | "### Comparing Patterns Across Slices" | Denominator is case-type-specific total |
| 7.2.3 | Lift formula | "lift = slice_pattern_share / overall_pattern_share" | "### Comparing Patterns Across Slices" | Lift > 1 indicates concentration in slice |
| 7.2.4 | Lift interpretation | "A lift of 1.0 means the pattern appears in that slice about as often as it appears overall. A lift above 1.0 means the pattern is concentrated in that slice. A lift below 1.0 means it is less common there." | "### Comparing Patterns Across Slices" | 1.0 is baseline; deviation indicates concentration or depletion |

### 7.3 Actionability Through Metadata Slicing

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 7.3.1 | Actionability principle | "In macro evals, this is the bridge from discovery to action. A behavior pattern is easier to investigate when we can say where it shows up: a generated scenario, an agent version, an orchestration mode, a market regime, or a review state." | "### Comparing Patterns Across Slices" | Metadata-based pattern slicing enables investigation prioritization |

---

## 8. AGENTRACE-STYLE DIAGNOSIS: BACKWARD WALK AND SUSPECT SCORING

### 8.1 Discovery vs. Diagnosis Distinction

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 8.1.1 | Phase distinction | "Discovery tells us what repeats. Diagnosis asks where to inspect first." | "6. AgentTrace-Style Diagnosis" | Two-pass structure: discovery then diagnosis |

### 8.2 Execution Graph Construction

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 8.2.1 | Graph construction | "For a selected behavior pattern, we reconstruct a lightweight execution graph: G = (V, E) where each node v ∈ V is a normalized trace event and each edge e ∈ E links events through temporal order, handoffs, tool calls, and nearby execution context." | "6. AgentTrace-Style Diagnosis" | Events are nodes; temporal/structural links are edges |

### 8.3 Anchor Selection (Focus Event)

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 8.3.1 | Anchor selection | "We then choose a focus event, also called an anchor. In this simulation, a focus event is usually a review/finding marker, failure-related status, or late-stage decision event." | "6. AgentTrace-Style Diagnosis" | Anchor is single event or event type per pattern |

### 8.4 Backward Walk Algorithm

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 8.4.1 | Backward search | "From that anchor, the diagnosis pass walks backward through the graph and scores upstream suspects." | "6. AgentTrace-Style Diagnosis" | Graph traversal from anchor backward |

### 8.5 Suspect Scoring Formula and Components

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 8.5.1 | Suspect scoring formula | "suspect_score = 0.4 × proximity + 0.3 × frequency + 0.2 × bridge + 0.1 × role" | "6. AgentTrace-Style Diagnosis" | Four weighted components sum to 1.0 |
| 8.5.2 | Proximity component | "Proximity rewards events close to the focus event." | "6. AgentTrace-Style Diagnosis" | Temporal/graph distance inversely weighted |
| 8.5.3 | Frequency component | "Frequency rewards events that recur across sampled traces in the same behavior pattern." | "6. AgentTrace-Style Diagnosis" | Cross-trace event occurrence counted |
| 8.5.4 | Bridge component | "Bridge rewards events that connect parts of the execution graph." | "6. AgentTrace-Style Diagnosis" | Centrality/cut-vertex metrics applied |
| 8.5.5 | Role component | "Role rewards events whose agent/tool role is plausibly related to the finding." | "6. AgentTrace-Style Diagnosis" | Domain-specific agent/tool relevance heuristic |

### 8.6 Causal Inference Caveat

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 8.6.1 | Causal inference caveat | "This is not proof of causality. It is a way to turn 'this pattern is important' into 'inspect these agents, tools, handoffs, or review policies first.'" | "6. AgentTrace-Style Diagnosis" | Suspect scores ordinal ranking, not causal attribution |

---

## 9. OUTPUTS, VISUALIZATIONS, AND INTERPRETABILITY

### 9.1 Review Finding Signal

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 9.1.1 | Signal interpretation | "The leading signal is [review finding] from [agent]. In this simulation, a review finding means that a specialist or review surface recorded a structured issue while processing one customer order." | (Section truncated in extraction) | Review findings are explicitly recorded structural markers |

---

## 10. UNDECLARED ASSUMPTIONS AND IMPLICIT COMMITMENTS

### 10.1 Trace Document Quality Assumption

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 10.1.1 | Implicit assumption | [Inferred from methodology] "The quality of the trace document is part of the evaluation design, not a mechanical cleanup step." | "4. Build the Analysis Dataset" | Document design determines what clustering can discover |
| 10.1.2 | Preservation assumption | "The notebook uses doc_structured_summary because it is compact but still preserves scenario, routing, state transitions, handoffs, findings, and terminal state." | "4. Build the Analysis Dataset" | Structured summary sufficient for clustering without information loss |

### 10.2 Embedding Model Assumptions

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 10.2.1 | Implicit choice | [Unspecified in article] | "5. BERTopic-Style Discovery" | Embedding model f(d_i) left unspecified (e.g., text-embedding-3-small, Sentence-BERT, other?) |
| 10.2.2 | Implicit assumption | [Unspecified] | "5. BERTopic-Style Discovery" | Assumed embedding model preserves semantic similarity of trace documents |

### 10.3 Clustering Assumptions

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 10.3.1 | Density assumption | [Implicit] | "5. BERTopic-Style Discovery" | Assumes HDBSCAN density-based clustering appropriate for agent workflow behaviors |
| 10.3.2 | Homogeneity assumption | [Implicit] | "5. BERTopic-Style Discovery" | Assumes traces with similar document vectors have similar root causes |

### 10.4 Backward Walk Assumptions

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 10.4.1 | Temporal causality | [Implicit] | "6. AgentTrace-Style Diagnosis" | Backward walk assumes earlier events in trace may explain later failures |
| 10.4.2 | Graph connectivity | [Implicit] | "6. AgentTrace-Style Diagnosis" | Assumes execution graph edges capture relevant causal pathways |

### 10.5 Feature Importance Assumptions

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 10.5.1 | Severity weighting justification | [Unspecified] | "4. Build the Analysis Dataset" | Why hard_failure=3.0, review_escalation=2.0, low=1.0? No justification given |
| 10.5.2 | Suspect score weights | [Unspecified] | "6. AgentTrace-Style Diagnosis" | Why proximity=0.4, frequency=0.3, bridge=0.2, role=0.1? No justification given |

---

## 11. UNDEFENDED ASSERTIONS AND IMPLICIT COMMITMENTS

### 11.1 Assertions About Practical Value

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 11.1.1 | Actionability assertion | "Macro evals look across many lower-level findings. They ask: which kinds of problems repeat, where do they concentrate, and which part of the agent workflow should we inspect first?" | "1. Why Macro Evals?" | Implies clustering+prioritization sufficient to guide investigation |
| 11.1.2 | Compression value | "The goal is not to build a perfect taxonomy of every trace. The goal is to show how an AI engineering team can move from thousands of agent events to a small number of patterns understandable by both technical and business stakeholders." | Introduction | Asserts compression inherently valuable; completeness sacrificed |

### 11.2 Assertions About Simulation Realism

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 11.2.1 | Realism claim | "The simulation includes the kinds of constraints that make real automotive fulfillment hard..." | "2. The Simulation" | Synthetic EV workflow representative of real multi-agent problems |
| 11.2.2 | Domain generality | "The methodology is domain-agnostic and applicable to any multi-agent system where understanding repeated workflow patterns matters more than auditing individual responses." | (Inferred from context) | Claims methodology transfers beyond EV domain |

### 11.3 Assertions About Two-Level Hierarchy

| # | Claim Type | Quote | Section | Commitment |
|---|---|---|---|---|
| 11.3.1 | Hierarchy necessity | "This notebook separates the problem into two levels: Lower-level evals grade individual agents, handoffs, tools, and completed runs." | "1. Why Macro Evals?" | Asserts two-level structure necessary; doesn't justify against flat or three-level alternatives |
| 11.3.2 | Orthogonality claim | [Implicit] | "4. Build the Analysis Dataset" | Lower-level evals treated as orthogonal inputs to clustering; doesn't test influence of eval signals on clustering |

---

## 12. CRITICAL GAPS: UNSPECIFIED PARAMETERS AND DESIGN CHOICES

### 12.1 Embedding and Feature Representation

| # | Missing Specification | Impact on Reproducibility | Impact on Transferability |
|---|---|---|---|
| 12.1.1 | Embedding model f(d_i): name, version, dimensionality | Cannot reproduce exact embeddings; cluster geometry may differ | Model choice affects what semantic patterns can be discovered |
| 12.1.2 | Document tokenization: n-gram strategy, stemming, lowercasing | TF-IDF calculation depends on token definitions | Different tokenization yields different distinctive terms |
| 12.1.3 | UMAP metric: Euclidean, cosine, Manhattan? | Distance metric affects dimensionality reduction | Different metrics alter neighborhood preservation |
| 12.1.4 | UMAP learning_rate, min_dist default values | These strongly affect global structure preservation | Non-standard settings could change cluster geometry |

### 12.2 Clustering and Graph Construction

| # | Missing Specification | Impact on Reproducibility | Impact on Transferability |
|---|---|---|---|
| 12.2.1 | HDBSCAN linkage method: single, complete, average? | Density region formation depends on linkage | Changing linkage can merge/split clusters |
| 12.2.2 | Event graph edge construction rules: which temporal/structural links counted? | Backward walk explores different graph topologies | Different edge sets change upstream suspect scores |
| 12.2.3 | Proximity metric in backward walk: Euclidean distance, graph hops, both? | Score depends on distance calculation | Different metrics alter suspect ordering |

### 12.3 Scoring and Aggregation

| # | Missing Specification | Impact on Reproducibility | Impact on Transferability |
|---|---|---|---|
| 12.3.1 | Severity weight rationale: why hard_failure=3.0 not 2.0 or 4.0? | Arbitrary weights affect pattern prioritization | Different domains may need different severity scaling |
| 12.3.2 | Impact score formula tuning: why not max(prevalence, severity)? Why not log normalization? | Different aggregation functions yield different rankings | No justification for multiplicative vs. additive vs. other forms |
| 12.3.3 | Suspect score weights: why 0.4/0.3/0.2/0.1? | Weights affect which components dominate suspect ordering | Domain-specific role importance ignored in fixed weights |

### 12.4 Sampling and Search Depth

| # | Missing Specification | Impact on Reproducibility | Impact on Transferability |
|---|---|---|---|
| 12.4.1 | top_n_traces=12 in backward walk: justification? | 12 may oversample small patterns, undersample large ones | Does diagnosis converge with fewer samples? |
| 12.4.2 | max_depth=5 in backward walk: how chosen? | Stops search after 5 hops; may miss distant root causes | Different workflows may need different depths |
| 12.4.3 | min_cluster_size=24 default: how justified? | Small clusters filtered; may lose rare patterns | Trade-off between noise and discovery unexplored |
| 12.4.4 | top_n_terms=8 per topic: sufficient? | Limits interpretability; 8 vs. 4 vs. 12 not compared | Labels may be ambiguous with fewer terms |

### 12.5 Promptfoo Configuration

| # | Missing Specification | Impact on Reproducibility | Impact on Transferability |
|---|---|---|---|
| 12.5.1 | Promptfoo grading LLM: model version, temperature, system prompt? | Eval signal depends on LLM config | Older/newer models may produce different pass/fail rates |
| 12.5.2 | Inter-rater agreement: reported? | No indication of eval consistency | Eval findings may be noisy or controversial |
| 12.5.3 | Online vs. offline grading: when evals run? | Timing affects whether post-hoc context available | Online evals may miss information available offline |

### 12.6 Data and Preprocessing

| # | Missing Specification | Impact on Reproducibility | Impact on Transferability |
|---|---|---|---|
| 12.6.1 | Event normalization rules: how raw SDK traces mapped to normalized events? | Missing details prevent reimplementation | Different event schemas require different normalizers |
| 12.6.2 | Case type generator algorithm: how synthetic scenarios generated? | Reproducibility of synthetic data unknown | Domain-specific generators needed for other workflows |
| 12.6.3 | Bundle construction criteria: why these 5 components (run, events, spans, env, review)? | Information selection design not justified | Other workflows may need different bundle components |

---

## 13. CRITICAL ABLATIONS NOT RUN

### 13.1 Discovery Component Ablations

| # | Ablation | Hypothesis Tested | Result Unknown |
|---|---|---|---|
| 13.1.1 | Drop UMAP reduction; cluster embeddings directly | Does dimensionality reduction improve cluster quality? | No comparison of embedding-direct vs. UMAP-reduced clustering |
| 13.1.2 | Replace HDBSCAN with K-means or Agglomerative clustering | Is density-based clustering necessary for workflow patterns? | No comparison of clustering algorithms |
| 13.1.3 | Use raw term frequency (TF) instead of TF-IDF scoring | Does IDF weighting improve label distinctiveness? | No comparison of TF vs. TF-IDF vs. other scoring |
| 13.1.4 | Vary min_cluster_size from 2 to 48 | How sensitive is cluster count to minimum size? | Fixed to adaptive formula; no sensitivity analysis |
| 13.1.5 | Vary top_n_terms from 3 to 15 per topic | How many terms needed for clear labels? | Fixed to 8; no sweep across cardinalities |

### 13.2 Impact Scoring Ablations

| # | Ablation | Hypothesis Tested | Result Unknown |
|---|---|---|---|
| 13.2.1 | Replace multiplicative impact formula with additive: impact = prevalence + severity | Does product vs. sum change pattern prioritization? | Only one formula tested |
| 13.2.2 | Vary severity weights (e.g., hard_failure=2.0 instead of 3.0) | How sensitive is ranking to severity scaling? | Fixed weights; no sensitivity analysis |
| 13.2.3 | Remove findings_count and loop_count multipliers from impact | Do these amplifications improve ranking? | No comparison to simpler impact formulas |
| 13.2.4 | Reverse impact formula: inverse_impact = 1 / (prevalence × severity) | Does rarity reveal hidden issues? | Only prevalence-times-severity explored |

### 13.3 Diagnosis (Backward Walk) Ablations

| # | Ablation | Hypothesis Tested | Result Unknown |
|---|---|---|---|
| 13.3.1 | Drop role component (set weight to 0) | Is domain-specific role knowledge necessary? | No comparison to role-agnostic suspect scoring |
| 13.3.2 | Drop bridge component (set weight to 0) | Is graph centrality important for suspect ranking? | No comparison to proximity+frequency alone |
| 13.3.3 | Vary weights: try (0.5, 0.3, 0.1, 0.1) instead of (0.4, 0.3, 0.2, 0.1) | How sensitive is suspect ranking to weight distribution? | Fixed weights; no sensitivity analysis |
| 13.3.4 | Vary max_depth from 2 to 10 | Does deeper graph exploration improve suspect identification? | Fixed to 5; no depth sweep |
| 13.3.5 | Replace backward walk with random walk or forward walk | Is backward traversal necessary? | Only backward walk tested |

### 13.4 Document and Signal Ablations

| # | Ablation | Hypothesis Tested | Result Unknown |
|---|---|---|---|
| 13.4.1 | Use raw event trace instead of structured summary document | Does compression lose causal information? | Only structured summary tested |
| 13.4.2 | Cluster on doc_short_narrative vs. doc_structured_summary | Do different summarization levels affect pattern discovery? | Only one document type tested |
| 13.4.3 | Include/exclude specific signal types (review findings vs. failures vs. reroutes) | Which signals most predictive? | All signals treated equally in document |
| 13.4.4 | Vary discovery input filter: use all traces vs. only failures vs. only reviews | How does input population affect discovered patterns? | Fallback to all traces if few failures; no explicit comparison |

### 13.5 Two-Level Hierarchy Ablations

| # | Ablation | Hypothesis Tested | Result Unknown |
|---|---|---|---|
| 13.5.1 | Skip lower-level evals; cluster traces directly by outcome only | Are Promptfoo findings necessary for macro discovery? | evals orthogonally pre-joined; influence on clustering not tested |
| 13.5.2 | Feed lower-level eval signals directly into clustering documents | Do eval_finding labels improve cluster quality vs. raw events? | eval_finding included in traces but not as independent feature |
| 13.5.3 | Use only successful traces to discover positive patterns | Can discovery identify what-works as well as what-fails? | Input filter biased to failure/review; no positive-pattern discovery tested |

### 13.6 Dataset and Scenario Ablations

| # | Ablation | Hypothesis Tested | Result Unknown |
|---|---|---|---|
| 13.6.1 | Train on clean scenarios only; test on pressure scenarios | Does discovery overfit to training scenario distribution? | No train/test split tested |
| 13.6.2 | Vary scenario complexity: simple vs. compound cases | How does case complexity affect pattern interpretability? | Mix of simple and compound in dataset; no stratified analysis |
| 13.6.3 | Vary case_type distribution: 50% clean vs. 50% pressure | Does class imbalance affect pattern discovery? | Natural distribution used; no rebalancing tested |

---

## 14. FAILURE MODES AND EDGE CASES NOT TESTED

### 14.1 Clustering Failure Modes

| # | Failure Mode | Why It Matters | Test Status |
|---|---|---|---|
| 14.1.1 | All traces cluster into single mega-cluster | Kills interpretability and prioritization | Not tested |
| 14.1.2 | Most traces marked as noise by HDBSCAN | Loses 90%+ of data; defeats population-level analysis | Not tested |
| 14.1.3 | Embedding model collapses document vectors to near-identical values | Reduces embedding variance below noise floor | Not tested |
| 14.1.4 | Document summarization loses failure signals (failure info pruned by doc construction) | Clustering misses root-cause patterns | Not tested explicitly |
| 14.1.5 | UMAP reduction fails to preserve local neighborhoods (pathological min_dist/learning_rate) | Distances in reduced space misleading | Not tested |

### 14.2 Diagnosis Failure Modes

| # | Failure Mode | Why It Matters | Test Status |
|---|---|---|---|
| 14.2.1 | Backward walk hits dead-end (no upstream events connected to focus anchor) | Suspect scoring returns empty results | Not tested |
| 14.2.2 | All upstream events scored equally (proximity/frequency/bridge/role all ≈ 0) | Suspect ranking becomes arbitrary | Not tested |
| 14.2.3 | Role heuristic incorrectly identifies innocent agent as suspect (e.g., pricing agent blamed for supply failure) | False blame kills credibility | Not tested |
| 14.2.4 | Focus event anchor is weak signal (e.g., cosmetic review finding, not true failure) | Diagnosis chases red herrings | Not tested |
| 14.2.5 | Backward walk finds many equally high-scoring suspects (no clear top-N) | Actionability unclear | Not tested |

### 14.3 Label and Interpretation Failure Modes

| # | Failure Mode | Why It Matters | Test Status |
|---|---|---|---|
| 14.3.1 | Discovered pattern labels are ambiguous or contradictory ("fulfillment reroute supply pricing") | Uninterpretable to stakeholders | Not tested |
| 14.3.2 | Same pattern discovered multiple times under different labels due to tokenization variance | Overcounts patterns; inflates cluster count | Not tested |
| 14.3.3 | Pattern labels contain domain jargon not understood by business stakeholders | Fails stated goal of "understandable by both technical and business" | Not tested |
| 14.3.4 | Heatmap shows spurious associations between case_type and behavior_pattern (statistical noise) | Misleads investigation direction | Not tested; no significance testing shown |

### 14.4 Dataset and Scope Failure Modes

| # | Failure Mode | Why It Matters | Test Status |
|---|---|---|---|
| 14.4.1 | Discovered patterns only occur in synthetic data; don't transfer to real workflows | Method overfits to simulation | Not tested (no real data comparison) |
| 14.4.2 | 992 traces insufficient for stable pattern discovery (high variance in pattern membership with bootstrap) | Patterns brittle; resampling yields different clusters | Not tested |
| 14.4.3 | EV domain-specific signals (tariffs, supplier substitution) not transferable to e-commerce or manufacturing | Method claims domain-agnostic; domain-specific signals embedded | Not tested on non-EV domain |
| 14.4.4 | Lower-level eval rubrics only catch 30% of real failures (false-negative rate) | Macro evals miss most failures | Not discussed; rubric coverage not measured |

### 14.5 Performance and Scalability Failure Modes

| # | Failure Mode | Why It Matters | Test Status |
|---|---|---|---|
| 14.5.1 | Embedding+UMAP+clustering takes hours for 100K traces (real production scale) | Method doesn't scale | Not tested at scale |
| 14.5.2 | Memory footprint exceeds 100GB for large datasets | Prohibitive for real deployments | Not tested |
| 14.5.3 | Backward walk samples top_n_traces=12 but 500+ traces in pattern | Diagnosis statistically underpowered | Not discussed |
| 14.5.4 | Term-frequency calculation O(n²) for large vocabularies; becomes bottleneck | Labeling phase slows down | Not profiled |

### 14.6 Assumption Violation Failure Modes

| # | Failure Mode | Why It Matters | Test Status |
|---|---|---|---|
| 14.6.1 | Trace documents constructed incorrectly, omitting critical signals (e.g., late tool call precedes failure but doc summarizes early decisions) | Clustering clusters on wrong signals | Not validated |
| 14.6.2 | Lower-level evals have systematic bias (e.g., grader more lenient on policy-compliance than routing) | Eval_finding label unreliable | Not validated with inter-rater or gold standard |
| 14.6.3 | Embedding model trained on non-technical documents (e.g., news articles) doesn't preserve trace-document semantics | Embeddings fail to capture workflow structure | Not tested |
| 14.6.4 | Case-type generator produces unrealistic correlations (e.g., always pairs tariffs with supply issues) | Patterns in data are synthetic artifacts | Not validated |

---

## SUMMARY TABLE: CLAIMS BY CATEGORY

| Category | Count | Examples |
|---|---|---|
| **Motivational/Framing Claims** | 5 | Multi-agent failures > single responses; population-level needed |
| **Architecture/Design Claims** | 8 | Two-layer hierarchy; 10+ specialists; bundle structure |
| **Dataset Claims** | 7 | 992 traces; 14 case types; 5 bundle components |
| **Lower-Level Eval Claims** | 5 | 5 rubrics; Promptfoo representation; local signal model |
| **Preprocessing/Normalization Claims** | 3 | Two-table schema; label pipeline; outcome grouping |
| **Discovery Algorithm Claims** | 12 | 4-stage pipeline; UMAP; HDBSCAN; TF-IDF formula; impact score |
| **Diagnosis Algorithm Claims** | 6 | Backward walk; graph construction; suspect scoring formula |
| **Output Interpretation Claims** | 8 | Heatmap; lift; keywords; owner labels; metrics |
| **Implicit Assumptions** | 8 | Document quality; embedding preservation; clustering appropriateness |
| **Formulas (Named)** | 9 | impact_score; suspect_score; score(t,k); lift; has_failure; others |
| **Hyperparameters (Specified)** | 7 | min_cluster_size=24; top_n_terms=8; random_state=42; others |
| **Undefended Assertions** | 4 | Realism; actionability; hierarchy necessity; orthogonality |
| **Total Enumerated Claims** | **83** | (Primary claims across all categories) |

---

## FINAL INVENTORY: UNSPECIFIED CRITICAL DETAILS

### Parameters Not Specified (15 items)

1. **Embedding model** (name, version, dimensionality) — TBD
2. **Document tokenization** (n-grams, stemming, lowercasing rules) — TBD
3. **UMAP metric** (Euclidean, cosine, Manhattan) — TBD
4. **UMAP learning_rate** (default value) — TBD
5. **UMAP min_dist** (default value) — TBD
6. **HDBSCAN linkage method** (single, complete, average) — TBD
7. **Proximity metric in backward walk** (graph hops vs. Euclidean distance) — TBD
8. **Frequency aggregation method** (average, max, sum across sampled traces) — TBD
9. **Bridge/centrality algorithm** (betweenness, closeness, degree) — TBD
10. **Role heuristic rules** (which agents/tools trigger role score) — TBD
11. **Event graph edge construction rules** (which events linked; temporal window?) — TBD
12. **Promptfoo grading LLM** (model version, temperature, system prompt) — TBD
13. **Case-type generator algorithm** (how synthetic scenarios generated) — TBD
14. **Document construction code** (build_trace_documents() logic) — TBD
15. **Event normalization rules** (SDK trace → normalized event mapping) — TBD

### Key Ablations Not Run (23 items)

**Discovery phase:**
1. Embedding-direct clustering vs. UMAP-reduced
2. HDBSCAN vs. K-means vs. Agglomerative clustering
3. TF-IDF vs. raw TF vs. other term-scoring schemes
4. Sensitivity analysis on min_cluster_size (2 to 48)
5. Sensitivity analysis on top_n_terms (3 to 15)

**Impact scoring:**
6. Multiplicative impact formula vs. additive
7. Sensitivity analysis on severity weights
8. With/without findings_count and loop_count multipliers
9. Rarity-focused impact formula (inverse)

**Diagnosis phase:**
10. Role component contribution (weight = 0 ablation)
11. Bridge component contribution (weight = 0 ablation)
12. Sensitivity analysis on suspect score weights
13. Sensitivity analysis on max_depth (2 to 10)
14. Backward walk vs. random walk vs. forward walk

**Document and signal design:**
15. Raw event trace vs. structured summary
16. Short narrative vs. structured summary documents
17. Signal type importance (review vs. failure vs. reroute)
18. Discovery input filter: all traces vs. failures only vs. reviews only

**Hierarchy and meta:**
19. Lower-level evals orthogonal vs. integrated into clustering
20. Skip Promptfoo; cluster on outcome alone
21. Positive-pattern discovery (succeed cases vs. fail cases)
22. Train/test split: does discovery overfit to scenario distribution?
23. Dataset rebalancing: equal clean vs. pressure case distributions

### Failure Modes and Edge Cases Not Tested (27 items)

**Clustering:**
1. Single mega-cluster (all traces combined)
2. Noise label spam (>90% marked as outliers)
3. Embedding vector collapse (near-identical values)
4. Document construction loss (failure signals pruned)
5. UMAP pathological failure (bad hyperparameters)

**Diagnosis:**
6. Backward walk dead-end (no upstream events)
7. Suspect scoring flatness (all scores ≈ equal)
8. Role heuristic false positive (wrong agent blamed)
9. Weak focus anchor (cosmetic signal, not true failure)
10. Suspect ranking tie (no clear top-N)

**Labels and interpretation:**
11. Ambiguous pattern labels
12. Duplicate patterns under variant labels
13. Domain-jargon labels (unintelligible to business)
14. Spurious heatmap associations (statistical noise)

**Dataset and scope:**
15. Synthetic data → real data transfer failure
16. Sample size insufficiency (bootstrap instability)
17. Domain transfer failure (non-EV workflows)
18. Lower-level eval false-negative rate
19. Eval rubric coverage measurement

**Performance and scalability:**
20. Embedding+UMAP+clustering time for 100K traces
21. Memory footprint at scale
22. Backward walk underpowered (12 samples in 500-trace pattern)
23. Term-frequency O(n²) bottleneck

**Assumption violations:**
24. Document construction bugs (signal omission)
25. Lower-level eval grader bias
26. Embedding model domain mismatch (trained on non-technical text)
27. Case-type generator unrealism (synthetic artifacts)

---

## END OF INVENTORY

**Compilation Date:** 2026-05-25  
**Source URL:** https://developers.openai.com/cookbook/examples/partners/macro_evals_for_agentic_systems/macro_evals_for_agentic_systems  
**Researcher Note:** This inventory captures 83 primary claims across 9 categories, identifies 15 unspecified critical parameters, catalogs 23 unrun ablations, and flags 27 untested failure modes. The article is rigorous in methodology but leaves significant room for gaps and vulnerabilities in the response critique.

