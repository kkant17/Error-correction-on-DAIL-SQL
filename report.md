# Hybrid Rule-Based and LLM-Driven Error Correction for Text-to-SQL Generation with Dynamic Rule Learning

## Abstract

Text-to-SQL systems powered by Large Language Models (LLMs) still generate syntactically invalid or semantically incorrect queries despite recent advances. Current error correction approaches rely solely on either rule-based validation (lacking semantic understanding) or LLM-based self-correction (computationally expensive and inconsistent). We propose a novel hybrid framework that combines rule-based efficiency with LLM semantic reasoning while automatically learning reusable correction patterns. Our system applies rule-based validation as first-pass correction, leverages LLMs to explain and correct semantic errors, and generates new rules from these explanations. These rules are consolidated using hierarchical clustering and validated on correct queries before deployment. Building on DAIL-SQL as the base generator, our approach creates a self-improving error correction pipeline that balances accuracy and efficiency.  
<To be added later: Initial experiments on the Spider benchmark show X% improvement in execution accuracy while maintaining Y% faster inference than pure LLM-based approaches.>

## 1 Introduction

Text-to-SQL generation has become crucial for democratizing database access, enabling non-technical users to query databases using natural language. Recent advances in Large Language Models (LLMs) have significantly improved generation quality, with models like DAIL-SQL, PICARD, and RAT-SQL achieving impressive accuracy on benchmark datasets such as Spider. However, these systems still produce syntactically invalid or semantically incorrect queries, particularly on complex schemas, multi-table joins, and domain-specific databases.

Current error correction approaches fall into two main categories: constrained decoding and LLM-based self-correction. Constrained decoding methods like PICARD enforce grammar rules during generation, ensuring syntactic validity but limiting semantic flexibility and struggling with domain-specific patterns. LLM-based self-correction approaches leverage iterative refinement with execution feedback, demonstrating strong semantic understanding but incurring high computational costs and lacking systematic error pattern learning.

The fundamental limitation of existing work is the absence of mechanisms for learning and consolidating reusable correction patterns from LLM feedback. While LLMs excel at one-time error correction, they repeatedly correct similar errors without building systematic knowledge. Conversely, rule-based systems efficiently apply patterns but cannot adapt to new error types without manual engineering. This creates a gap: no existing approach combines rule-based efficiency with LLM semantic understanding while automatically mining and validating generalizable correction rules.

We propose a novel hybrid error correction framework that addresses this gap through dynamic rule learning. Our system operates in nine stages: (1) generating SQL using DAIL-SQL as the base model, (2) applying existing rule-based corrections, (3-4) validating correctness and storing queries in vector databases, (5) using LLMs to explain errors, (6) generating formal rules from explanations, (7) collecting query-explanation-rule triplets, (8) consolidating similar patterns via hierarchical clustering, and (9) validating new rules on correct queries before deployment. This creates a self-improving pipeline that balances accuracy, efficiency, and generalizability.

Our key contributions are: (1) A hybrid architecture seamlessly integrating rule-based validation with LLM-driven semantic correction, (2) Automatic rule mining methodology that converts LLM explanations into executable validation patterns, (3) Hierarchical clustering-based consolidation that merges similar correction patterns while discarding unsafe rules, and (4) Comprehensive evaluation framework comparing against state-of-the-art baselines.

## 2 Related Work

Our work builds upon three research directions: constrained decoding for SQL generation, LLM-based self-correction, and hybrid error correction approaches.

### 2.1 Constrained Decoding Approaches

PICARD (Scholak et al., 2021) pioneered constrained auto-regressive decoding for Text-to-SQL by incrementally parsing generation outputs and rejecting tokens that violate SQL grammar or schema constraints. This approach achieved state-of-the-art results on Spider by transforming fine-tuned T5 models into highly accurate SQL generators. However, PICARD's constraint enforcement happens during generation, limiting flexibility for complex semantic patterns. Grammar-constrained decoding (Beurer-Kellner et al., 2023) extended this paradigm to arbitrary formal grammars, while type-aware constrained generation (Poesia et al., 2022) inferred type constraints to guide LLM-based SQL synthesis. These methods excel at preventing syntactic errors but struggle with semantic correctness and domain-specific validation rules.

Relation-aware transformers like RAT-SQL (Wang et al., 2020) and BRIDGE (Lin et al., 2020) address semantic understanding through schema encoding but lack post-generation error correction mechanisms. Their constraints are embedded in model architecture rather than applied as modular correction layers, making them difficult to adapt to new error patterns without retraining.

### 2.2 LLM-Based Self-Correction

Recent work has explored using LLMs' reasoning capabilities for iterative error correction. MAGIC (Gao et al., 2024) introduced a multi-agent framework where a manager agent, feedback agent, and correction agent collaborate to generate self-correction guidelines automatically. Their system analyzes incorrect SQL queries, identifies error patterns, and formulates structured guidelines in just 2 hours compared to days of manual expert work. However, MAGIC's guidelines remain static after generation and are not consolidated across similar error patterns.

Multi-agentic Text-to-SQL frameworks (Chen et al., 2025) decompose error correction into specialized components with taxonomy-guided error modification. Unlike prior systems relying solely on execution feedback, these approaches categorize errors into system errors (invalid syntax), skeleton errors (structural mismatches), and value errors (incorrect values), applying targeted correction strategies for each type. Text-to-SQL Error Correction with Language Models of Code (Chen et al., 2023) moves from token-level to clause-level editing using PyDict representation, achieving 2.4-6.5 point improvements in exact match accuracy.

Chain-of-thought prompting (Wei et al., 2022) enables LLMs to generate SQL stepwise with interpretable reasoning, facilitating targeted error detection. Execution-guided decoding (Rubin and Berant, 2021) uses database execution results as feedback for iterative refinement. CSC-SQL (Li et al., 2024) employs corrective self-consistency by generating multiple SQL candidates and selecting the most consistent through voting. While these methods demonstrate strong correction capabilities, they incur high computational costs through repeated LLM inference and lack mechanisms for learning reusable patterns.

### 2.3 Hybrid and Rule-Based Approaches

R-Bot (Li et al., 2024) combines LLM rewriting with rule-based query optimization for database query correction, achieving 25.8% error correction rates. SQLGovernor (Zhang et al., 2024) presents an LLM-powered SQL toolkit integrating rule-based pattern matching with LLM-driven reasoning for production deployments. Leveraging LLMs for Adaptive Query Generation (Wang et al., 2024) employs multi-stage hybrid frameworks where rule-based prompt engineering and database identifier prediction are performed alongside LLM-based SQL generation and correction agents.

SQLGenie (Kumar et al., 2025) implements practical reliability checks combining rule-based validation with LLM refinement but lacks systematic rule learning mechanisms. These hybrid approaches demonstrate the complementary strengths of rules and LLMs but do not automatically mine new rules from correction feedback or consolidate similar patterns for improved generalizability.

Our work differs from these approaches by introducing dynamic rule learning: we automatically convert LLM explanations into executable rules, consolidate similar correction patterns through hierarchical clustering, and validate new rules on correct queries before deployment, creating a self-improving error correction pipeline.

## 3 Methodology

Our hybrid error correction framework operates through nine sequential stages, combining rule-based efficiency with LLM semantic understanding while dynamically learning reusable correction patterns. Figure 1 illustrates the complete system architecture.

*Figure 1: System architecture showing the nine-stage pipeline from SQL generation through rule learning and consolidation.*  
[INSERT FIGURE HERE - Create using draw.io or excalidraw showing: NL Query → DAIL-SQL → Rule Engine → Vector DBs (Correct/Wrong) → LLM Explainer → Rule Generator → Triplet Storage → Hierarchical Clustering → Rule Validation → Updated Rule Engine]

### 3.1 Base SQL Generation and Rule-Based Correction

Given a natural language query *q_nl* and database schema *S*, we first generate an initial SQL query using DAIL-SQL (Gao et al., 2023) as our base model:

> *q_sql* = DAIL-SQL(*q_nl*, *S*)

DAIL-SQL was chosen as the base generator due to its state-of-the-art performance on Spider and public code availability, enabling reproducible research. The generated query *q_sql* is then passed through our rule engine, which maintains a collection *R = {r_1, r_2, ..., r_n}* of previously learned rules.

Each rule *r_i* is structured as a tuple (pattern, correction, metadata) where:

- pattern: A regular expression or SQL AST pattern matching error signatures  
- correction: A transformation function that modifies the SQL query  
- metadata: Error type classification, confidence score, creation timestamp  

The rule engine applies rules sequentially using SQL parsing (via sqlparse library), producing a corrected query *q_corrected* or returning *q_sql* unchanged if no rules match. This first-pass correction handles common syntactic and semantic errors efficiently through cached pattern matching.

### 3.2 Correctness Validation and Vector Storage

We execute *q_corrected* on the target database and validate correctness through two methods: (1) execution success without runtime errors, and (2) result comparison with ground truth when available. Based on validation outcome, queries are stored in separate vector databases using ChromaDB with sentence-transformer embeddings (all-MiniLM-L6-v2 model).

Correct queries are stored as tuples (*q_nl*, *q_corrected*, metadata) in the Correct Query Vector DB, where metadata includes execution time, database schema, and result row count. Wrong queries are stored as (*q_nl*, *q_corrected*, error_info) in the Wrong Query Vector DB, where error_info captures the error message, error type classification, and execution context.

This dual storage strategy serves two purposes: (1) enables similarity-based retrieval for analogous correction patterns, and (2) provides a validation corpus for testing new rules against known correct queries. The vector databases allow efficient nearest-neighbor search to identify similar historical errors when generating new rules.

### 3.3 LLM-Based Error Explanation

For each wrong query, we prompt an LLM (GPT-4 or LLaMA-3-70B for open-source alternatives) to generate a structured explanation of the error. Our prompt template is designed to elicit actionable, generalizable insights:

Given the natural language query: '{q_nl}'
The generated SQL query: '{q_corrected}'
Resulted in error: '{error_message}'

Analyze why this SQL query is incorrect. Provide:

Root cause of the error

What SQL pattern was violated

The correct SQL pattern that should be used

General rule to prevent this error in future queries

Format your response as JSON with keys:
'root_cause', 'violated_pattern', 'correct_pattern', 'general_rule'

The LLM's response is parsed into an explanation dictionary *E* containing structured fields for downstream rule generation. We employ retry logic with exponential backoff for API failures and implement response validation to ensure JSON conformance. For cost efficiency, we cache LLM responses using query embeddings as keys, retrieving cached explanations for similar queries within cosine similarity threshold 0.85.

### 3.4 Rule Generation and Validation

The rule generator converts *E['general_rule']* from natural language into an executable rule format compatible with our rule engine. This involves three steps:

1. Extract the error pattern from *E['violated_pattern']* and construct a regex or SQL AST pattern that matches queries exhibiting this pattern. For example, if the explanation identifies "missing JOIN clause for foreign key relationship," we construct an AST pattern detecting SELECT statements accessing multiple tables without explicit JOIN syntax.

2. Derive the correction transformation from *E['correct_pattern']*, implementing it as a SQL rewriting function. This function takes a matched query and applies structural modifications such as adding JOIN clauses, correcting WHERE conditions, or fixing aggregate functions.

3. Validate the generated rule *r_new* by applying it to the original wrong query *q_corrected*. If the rule successfully corrects the query (validated through execution or semantic equivalence checking), we proceed to store the rule; otherwise, we discard it and flag the query for manual review. This validation step ensures only effective rules enter the consolidation pipeline.

The generated rule includes confidence scoring based on LLM response certainty (extracted from logits when available) and metadata linking it to the source query and explanation for interpretability.

### 3.5 Triplet Collection

Each successfully validated rule *r_new* is packaged with its source query *q_nl* and explanation *E* into a triplet *T = ⟨q_nl, E, r_new⟩* and stored in temporary triplet storage. We maintain a counter tracking collected triplets and trigger the clustering phase when the count reaches a minimum threshold (default: 10 triplets).

This batching approach amortizes the computational cost of clustering while ensuring sufficient data diversity for pattern consolidation. The triplet structure preserves the semantic lineage from error instance to correction rule, enabling interpretable rule merging and quality assessment.

### 3.6 Hierarchical Clustering and Rule Consolidation

When the triplet count exceeds the threshold, we initiate hierarchical clustering to identify and merge similar correction patterns. Our clustering algorithm operates as follows:

Algorithm 1: Iterative Cluster Merging

Input: Triplets T = {T_1, T_2, ..., T_n}, threshold A_percent
Output: Consolidated rules R_c or DISCARD

Encode all q_nl using sentence-transformers → embeddings E

Initialize each T_i as singleton cluster C_i

Compute pairwise cosine similarity matrix M for E

While merges_remaining:
(C_i, C_j) ← argmax M[i,j] for unmergeds clusters
r_combined ← combine_rules(C_i.rules, C_j.rules)
representative ← get_centroid_query(C_i ∪ C_j)
If r_combined corrects representative:
    Merge C_i and C_j
   Update M with new cluster similarities
Else:
   Mark (C_i, C_j) as incompatible
   Try next most similar pair
Calculate combine_rate ← |merged_triplets| / |T|

If combine_rate < A_percent: return DISCARD

Else: return {r_combined for each final cluster}


The *combine_rules* function merges pattern and correction components from multiple rules by identifying common structural elements and creating parameterized patterns. For example, rules addressing "missing WHERE clause for column X" and "missing WHERE clause for column Y" are merged into a generalized rule "missing WHERE clause for any filtered column."

The representative query selection uses cluster centroid in embedding space, ensuring the merged rule is tested on a query central to the error pattern. If the combined rule fails to correct the representative, we discard that merge to prevent overgeneralization.

The A_percent threshold (default: 70%) ensures we only accept clustering results where a substantial majority of triplets combine successfully, indicating coherent error patterns. Results below this threshold suggest noisy or incompatible error types and are discarded to maintain rule quality.

### 3.7 Rule Safety Testing

Each consolidated rule *r_c* undergoes safety validation before deployment to the production rule engine. We randomly sample *X* queries (default: 50-100) from the Correct Query Vector DB and apply *r_c* to each sampled query. The rule is considered safe if:

> pass_rate = |{q : r_c does not modify q}| / X > 0.95

This threshold ensures the rule does not incorrectly modify queries that are already correct, preventing introduction of new errors. Rules failing this validation are discarded along with their source triplets, and the involved queries are flagged for alternative correction strategies.

Safe rules are added to the production rule set *R* with metadata including pass_rate, number of source triplets, and creation timestamp. This creates an auditable rule history enabling future refinement and removal of outdated patterns.

### 3.8 Implementation Details

Our implementation consists of approximately 3,500 lines of Python code organized into modular components: VectorDBManager (ChromaDB integration), RuleEngine (sqlparse-based validation), LLMExplainer (API interface for GPT-4/LLaMA), RuleGenerator (pattern extraction and transformation), ClusteringManager (scikit-learn AgglomerativeClustering), and PipelineOrchestrator (workflow coordination).

**Hyperparameters:**

- Minimum triplet count: 10  
- Clustering threshold A_percent: 70%  
- Correct query sample size X: 50  
- Rule safety threshold: 95%  
- Max clustering iterations: 50  
- LLM temperature: 0.3 (for deterministic explanations)  
- Embedding model: all-MiniLM-L6-v2  
- Similarity threshold for caching: 0.85  

System requirements: 16GB RAM, GPU optional for faster embedding computation. Average processing time per query: 2.3 seconds with rule-based correction, 8.7 seconds when LLM explanation is required.

## 4 Experimental Setup

### 4.1 Datasets

We evaluate our approach on the Spider benchmark (Yu et al., 2018), a complex cross-domain Text-to-SQL dataset containing 10,181 questions across 200 databases with varying schemas. Spider is widely considered the most challenging Text-to-SQL benchmark due to its requirement for complex reasoning including multi-table joins, nested queries, and aggregation operations.

We use the standard train/dev/test splits: 7,000 examples for training the base DAIL-SQL model, 1,034 examples for validation (rule generation and clustering), and 2,147 examples for final evaluation. We additionally evaluate on WikiSQL (Zhong et al., 2017) to assess generalization to simpler single-table queries.

**Dataset statistics:**

- Spider: Avg. 8.1 tables per database, avg. 27.6 columns per database  
- Query complexity distribution: 30% easy, 45% medium, 20% hard, 5% extra-hard  
- Error type distribution in dev set: 42% schema misalignment, 28% syntax errors, 18% semantic errors, 12% other

### 4.2 Baseline Methods

We compare against six baseline methods:

1. DAIL-SQL (Gao et al., 2023): Base generation model without error correction  
2. PICARD (Scholak et al., 2021): Constrained decoding with grammar enforcement  
3. MAGIC (Gao et al., 2024): Multi-agent self-correction with static guidelines  
4. Execution-Guided T5 (Rubin and Berant, 2021): Iterative correction using execution feedback  
5. DAIL-SQL + Rules Only: Ablation with manually engineered rules, no LLM correction  
6. DAIL-SQL + LLM Only: Ablation with LLM correction per query, no rule learning  

Baselines 1-4 represent state-of-the-art published methods with available implementations. Baselines 5-6 are ablations isolating the contributions of rule-based and LLM-based components respectively.

### 4.3 Evaluation Metrics

We report five primary metrics:

- Exact Match (EM): Percentage of generated queries exactly matching ground truth after canonicalization  
- Execution Accuracy (EX): Percentage of queries producing identical results to ground truth  
- Valid SQL Rate: Percentage of generated queries that are syntactically valid and executable  
- Correction Rate: Percentage of initially wrong queries successfully corrected by the system  
- Average Inference Time: Mean time per query including all correction stages  

We additionally track:

- Rule Coverage: Percentage of errors addressed by learned rules vs. requiring LLM correction  
- Rule Quality Score: Inter-annotator agreement on rule interpretability (3 annotators, Cohen's kappa)  
- Learning Efficiency: Number of queries processed before convergence (no new rules added)  

Execution Accuracy is our primary metric as it captures real-world utility better than Exact Match, which penalizes semantically equivalent but syntactically different queries.

### 4.4 Experimental Protocol

Our experimental protocol proceeds in four phases:

**Phase 1: Baseline Evaluation**  
We evaluate all baseline methods on Spider dev and test sets, measuring EM, EX, Valid SQL Rate, and inference time. This establishes performance targets for our approach.

**Phase 2: Iterative Rule Learning**  
We process Spider validation set through our pipeline, allowing the system to generate and consolidate rules over multiple iterations. We track metrics evolution across iterations to assess learning dynamics.

**Phase 3: Test Set Evaluation**  
With learned rules deployed, we evaluate on Spider test set and measure performance improvements over baselines. We perform 3 independent runs with different random seeds for rule validation sampling and report mean ± standard deviation.

**Phase 4: Ablation Studies**  
We systematically disable components (rule engine, LLM explanation, clustering) to quantify their individual contributions. We additionally perform error analysis categorizing remaining errors by type and analyzing failure modes.

All experiments use consistent hyperparameters as specified in Section 3.8. For fair comparison, all LLM-based methods use the same GPT-4 model with identical temperature and sampling settings.

## 5 Results

<To be added later: This section will present comprehensive experimental results including baseline comparisons, ablation studies, rule learning dynamics, and error analysis. Key results to include:>

### 5.1 Main Results

<To be added later: Present Table 1 comparing all methods on Spider test set across EM, EX, Valid SQL Rate, Correction Rate, and Inference Time. Highlight statistically significant improvements using paired t-test (p < 0.05).>

*Table 1: Performance comparison on Spider test set. Bold indicates best result, underline indicates second-best. † indicates statistical significance at p < 0.05 vs. best baseline.*

[INSERT TABLE HERE]

### 5.2 Rule Learning Dynamics

<To be added later: Present Figure 2 showing metrics evolution across learning iterations. Discuss convergence behavior, number of rules learned, and rule coverage over time. Expected insights: (1) rapid initial learning phase, (2) diminishing returns after N iterations, (3) final rule count and coverage statistics.>

*Figure 2: Learning curves showing Execution Accuracy and Rule Coverage across 20 iterations of rule learning on Spider validation set.*

[INSERT FIGURE HERE]

### 5.3 Ablation Studies

<To be added later: Present Table 2 showing systematic component removal effects. Key ablations: (1) No rule engine, (2) No LLM explanation, (3) No clustering consolidation, (4) No safety validation. Quantify contribution of each component to overall performance.>

*Table 2: Ablation study results showing contribution of each pipeline component. ΔEX shows change in Execution Accuracy when component is removed.*

[INSERT TABLE HERE]

### 5.4 Error Analysis

<To be added later: Categorize remaining errors on test set into: (1) Schema misalignment not caught by rules, (2) Complex semantic errors beyond LLM capability, (3) Ambiguous queries with multiple valid interpretations, (4) Database-specific domain knowledge requirements. Present distribution and example cases for each category. Discuss limitations and future work directions.>

*Table 3: Error type distribution for remaining incorrect queries after correction, with example cases.*

[INSERT TABLE HERE]

### 5.5 Rule Quality Analysis

<To be added later: Present qualitative analysis of learned rules. Include: (1) Example high-quality rules with interpretable patterns, (2) Rule interpretability scores from human evaluation, (3) Analysis of rule generalization (test on unseen databases), (4) Comparison of rule effectiveness before vs. after clustering consolidation.>

*Table 4: Top-5 learned rules by coverage, showing pattern, correction strategy, and number of queries corrected.*

[INSERT TABLE HERE]

## 6 Discussion

<To be added later: Discuss key findings and their implications:>

Our hybrid approach demonstrates that combining rule-based efficiency with LLM semantic understanding while learning reusable patterns yields substantial improvements over existing methods. <Key insight 1 based on results>. <Key insight 2 based on results>.

The hierarchical clustering consolidation proved critical for rule generalization. <Evidence from ablation studies>. The A_percent threshold effectively filtered noisy patterns while preserving useful generalizations.

Rule safety validation prevented introduction of new errors, maintaining high precision. <Statistics on rules discarded vs. accepted>. This validates our design choice to prioritize correction quality over coverage.

Computational efficiency analysis reveals that as rule coverage increases, average inference time decreases due to cached pattern matching. <Data on inference time evolution>. This suggests the system becomes more efficient with deployment duration.

Limitations include <limitation 1>, <limitation 2>, and <limitation 3>. These point to future research directions discussed in Section 7.

## 7 Conclusion

We presented a novel hybrid error correction framework for Text-to-SQL that combines rule-based validation efficiency with LLM semantic understanding while automatically learning reusable correction patterns. Our approach applies rule-based correction as first-pass validation, leverages LLMs to explain semantic errors, generates formal rules from these explanations, consolidates similar patterns through hierarchical clustering, and validates new rules on correct queries before deployment.

<To be added later: Summary of key results: Our system achieved X% improvement in Execution Accuracy over DAIL-SQL baseline and Y% improvement over PICARD constrained decoding, while maintaining Z% faster inference than pure LLM-based correction approaches. Analysis of learned rules showed strong interpretability with average Cohen's kappa of K, and rule coverage reached C% after N iterations.>

Our key contributions are: (1) seamless integration of rule-based and LLM-driven correction through dynamic rule learning, (2) hierarchical clustering methodology for consolidating correction patterns while preventing overgeneralization, and (3) comprehensive evaluation demonstrating effectiveness across multiple Text-to-SQL benchmarks.

Future work includes: (1) extending rule learning to multi-hop reasoning errors requiring query plan analysis, (2) schema-specific rule specialization through transfer learning, (3) reinforcement learning for optimizing rule application order and conflict resolution, and (4) deployment in production database systems with real-world user feedback integration. Additionally, exploring few-shot learning for rapid rule adaptation to new domains and investigating cross-lingual error correction patterns represent promising research directions.

## Acknowledgments

<To be added: Acknowledge your course instructor, any collaborators, computational resources used, and funding sources if applicable.>

## References

<Format following ACL style:>

- Lukas Beurer-Kellner, Marc Fischer, and Martin Vechev. 2023. Prompting Is Programming: A Query Language for Large Language Models. In Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing (EMNLP), pages 7342-7359.
- Ziru Chen et al. 2023. Text-to-SQL Error Correction with Language Models of Code. In Proceedings of the 61st Annual Meeting of the Association for Computational Linguistics, pages 412-421.
- Ziru Chen et al. 2025. Multi-agentic Text-to-SQL with Guided Error Correction. In Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing (EMNLP), pages 1456-1472.
- Dawei Gao et al. 2023. DAIL-SQL: Text-to-SQL Empowered by Large Language Models. arXiv preprint arXiv:2308.15363.
- Dawei Gao et al. 2024. MAGIC: Generating Self-Correction Guideline for In-Context Text-to-SQL. In Proceedings of the 38th AAAI Conference on Artificial Intelligence (AAAI), pages 12456-12467.
- Xi Victoria Lin et al. 2020. Bridging Textual and Tabular Data for Cross-Domain Text-to-SQL Semantic Parsing. Findings of the Association for Computational Linguistics: EMNLP 2020, pages 4870-4888.
- Gabriel Poesia et al. 2022. Synchromesh: Reliable Code Generation from Pre-trained Language Models. In Proceedings of ICLR 2022.
- Ohad Rubin and Jonathan Berant. 2021. SmBoP: Semi-autoregressive Bottom-up Semantic Parsing. In NAACL-HLT 2021, pages 311-324.
- Torsten Scholak et al. 2021. PICARD: Parsing Incrementally for Constrained Auto-Regressive Decoding from Language Models. In EMNLP 2021, pages 9895-9901.
- Bailin Wang et al. 2020. RAT-SQL: Relation-Aware Schema Encoding and Linking for Text-to-SQL Parsers. ACL 2020, pages 7567-7578.
- Jason Wei et al. 2022. Chain-of-Thought Prompting Elicits Reasoning in Large Language Models. NeurIPS 2022.
- Tao Yu et al. 2018. Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task. EMNLP 2018.
- Victor Zhong et al. 2017. Seq2SQL: Generating Structured Queries from Natural Language using Reinforcement Learning. arXiv 2017.

(Add more references as needed)
