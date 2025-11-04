"""
Incremental Error Correction Pipeline
Processes queries one-by-one and triggers rule generation after x queries stored.
Implements online learning during a single evaluation run.
"""
import os
import json
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from error_correction.config import (
    MIN_TRIPLETS_FOR_CLUSTERING,
    RULE_STORAGE_PATH,
    ENABLE_TRANSFORMATION,
    MIN_PASS_RATE,
    CORRECT_QUERY_TEST_RATIO
)
from error_correction.vector_store import SQLEmbedder
from error_correction.vector_store.vector_db import CorrectQueriesDB, IncorrectQueriesDB
from error_correction.rule_engine.rule_generator import RuleGenerator
from error_correction.rule_engine.rule_applicator import RuleApplicator
from error_correction.clustering.hierarchical_cluster import HierarchicalRuleClusterer
from error_correction.rule_engine.rule_schema import Rule, RuleTriplet, RuleCluster

logger = logging.getLogger(__name__)


class IncrementalErrorCorrectionPipeline:
    """
    Incremental pipeline that processes queries one-by-one.

    Key Features:
    - Processes queries as they come in (not batch)
    - Stores incorrect queries incrementally
    - Triggers rule generation after MIN_TRIPLETS_FOR_CLUSTERING queries
    - Applies existing rules to new queries before evaluation
    - Maintains state across queries in the same run
    """

    def __init__(
        self,
        db_id: str,
        model: str = "gpt-4",
        openai_api_key: str = None,
        enable_transformation: bool = ENABLE_TRANSFORMATION,
        vector_db_path: str = None
    ):
        """
        Initialize incremental pipeline.

        Args:
            db_id: Database identifier
            model: LLM model for rule generation
            openai_api_key: OpenAI API key
            enable_transformation: Whether to apply transformations
            vector_db_path: Path to vector database (optional, not used - kept for compatibility)
        """
        self.db_id = db_id
        self.model = model
        self.openai_api_key = openai_api_key
        self.enable_transformation = enable_transformation

        # Initialize components
        self.embedder = SQLEmbedder()
        self.correct_db = CorrectQueriesDB()
        self.incorrect_db = IncorrectQueriesDB()
        self.rule_generator = RuleGenerator(model=model, temperature=0.3)
        self.rule_applicator = RuleApplicator()
        self.clusterer = HierarchicalRuleClusterer()

        # State management
        self.stored_incorrect_queries = []  # List of (query, gold_query, question) tuples
        self.stored_correct_queries = []    # List of correct queries
        self.current_triplets = []          # Generated triplets
        self.current_clusters = []          # Validated clusters
        self.current_rules = []             # Active rules
        self.query_count = 0
        self.correction_triggered_count = 0

        # Metrics
        self.metrics = {
            'total_queries_processed': 0,
            'queries_corrected': 0,
            'queries_improved': 0,
            'rule_generations_triggered': 0,
            'total_rules_generated': 0,
            'total_clusters_created': 0,
            'corrections': []
        }

        # Load existing rules if available
        self._load_existing_rules()

        logger.info(
            f"IncrementalErrorCorrectionPipeline initialized: "
            f"db_id={db_id}, model={model}, enable_transformation={enable_transformation}"
        )

    def _load_existing_rules(self):
        """Load previously generated rules if they exist."""
        rules_file = os.path.join(RULE_STORAGE_PATH, "rules.json")
        if os.path.exists(rules_file):
            try:
                with open(rules_file, 'r') as f:
                    rules_data = json.load(f)

                for rule_dict in rules_data:
                    rule = Rule(
                        pattern=rule_dict['pattern'],
                        correction=rule_dict['correction'],
                        error_type=rule_dict.get('error_type', 'OTHER'),
                        rule_id=rule_dict.get('rule_id', '')
                    )
                    self.current_rules.append(rule)

                logger.info(f"Loaded {len(self.current_rules)} existing rules")
            except Exception as e:
                logger.warning(f"Failed to load existing rules: {e}")

    def process_query(
        self,
        predicted_query: str,
        gold_query: str,
        question: str,
        is_correct: bool
    ) -> Tuple[str, bool, Dict]:
        """
        Process a single query incrementally.

        Args:
            predicted_query: The generated SQL query
            gold_query: The correct SQL query
            question: Natural language question
            is_correct: Whether predicted matches gold (exact/execution match)

        Returns:
            Tuple of (final_query, was_corrected, correction_info)
        """
        self.query_count += 1
        self.metrics['total_queries_processed'] += 1

        correction_info = {
            'original_query': predicted_query,
            'final_query': predicted_query,
            'was_corrected': False,
            'correction_successful': False,
            'rules_applied': []
        }

        # If query is correct, store for validation and return
        if is_correct:
            self.stored_correct_queries.append(predicted_query)
            logger.debug(f"Query {self.query_count}: Correct - stored for validation")
            return predicted_query, False, correction_info

        # Query is incorrect - try to apply existing rules first
        final_query = predicted_query
        if self.enable_transformation and len(self.current_rules) > 0:
            logger.debug(f"Query {self.query_count}: Incorrect - attempting correction with {len(self.current_rules)} rules")

            for rule in self.current_rules:
                transformed = self.rule_applicator.apply_rule(final_query, rule)
                if transformed != final_query:
                    logger.info(f"Rule {rule.rule_id} applied: {rule.error_type}")
                    correction_info['rules_applied'].append({
                        'rule_id': rule.rule_id,
                        'error_type': rule.error_type,
                        'pattern': rule.pattern
                    })
                    final_query = transformed
                    correction_info['was_corrected'] = True

            if correction_info['was_corrected']:
                correction_info['final_query'] = final_query
                self.metrics['queries_corrected'] += 1

                # Check if correction brought it closer to gold
                # (For now, just log - could add execution validation here)
                logger.info(
                    f"Query {self.query_count}: Applied {len(correction_info['rules_applied'])} rules\n"
                    f"  Original: {predicted_query[:100]}...\n"
                    f"  Corrected: {final_query[:100]}..."
                )

        # Store incorrect query (original) for learning
        self.stored_incorrect_queries.append({
            'predicted_query': predicted_query,
            'gold_query': gold_query,
            'question': question
        })

        # Add to vector store
        embedding = self.embedder.embed_query(predicted_query)
        self.incorrect_db.add_query(
            sql=predicted_query,
            embedding=embedding,
            metadata={'db_id': self.db_id, 'question': question, 'gold_sql': gold_query}
        )

        logger.debug(
            f"Query {self.query_count}: Stored incorrect query "
            f"({len(self.stored_incorrect_queries)} total incorrect)"
        )

        # Check if we should trigger rule generation
        if self._should_trigger_rule_generation():
            logger.info(
                f"\n{'='*70}\n"
                f"TRIGGER: {len(self.stored_incorrect_queries)} incorrect queries stored "
                f"(threshold: {MIN_TRIPLETS_FOR_CLUSTERING})\n"
                f"Starting rule generation...\n"
                f"{'='*70}"
            )
            self._trigger_rule_generation()

        self.metrics['corrections'].append(correction_info)
        return final_query, correction_info['was_corrected'], correction_info

    def _should_trigger_rule_generation(self) -> bool:
        """
        Determine if rule generation should be triggered.

        Per methodology: Trigger after >= MIN_TRIPLETS_FOR_CLUSTERING queries stored
        """
        # Only trigger if we have enough new queries since last trigger
        queries_since_last_trigger = len(self.stored_incorrect_queries) - (
            self.correction_triggered_count * MIN_TRIPLETS_FOR_CLUSTERING
        )

        return queries_since_last_trigger >= MIN_TRIPLETS_FOR_CLUSTERING

    def _trigger_rule_generation(self):
        """
        Trigger the rule generation pipeline on stored incorrect queries.
        Implements Steps 3-7 from the main pipeline.
        """
        try:
            self.correction_triggered_count += 1
            self.metrics['rule_generations_triggered'] += 1

            # Step 3-5: Generate triplets for stored incorrect queries
            logger.info("\n[Step 3-5] Generating error explanations and rules...")
            new_triplets = self._generate_triplets()

            if len(new_triplets) == 0:
                logger.warning("No valid triplets generated, skipping clustering")
                return

            self.current_triplets.extend(new_triplets)
            logger.info(f"Generated {len(new_triplets)} new triplets ({len(self.current_triplets)} total)")

            # Step 6: Hierarchical clustering
            logger.info("\n[Step 6] Performing hierarchical clustering...")
            new_clusters = self._perform_clustering(new_triplets)

            if len(new_clusters) == 0:
                logger.warning("No clusters created, skipping validation")
                return

            logger.info(f"Created {len(new_clusters)} new clusters")

            # Step 6.1: Condense rules in clusters
            logger.info("\n[Step 6.1] Condensing rules in clusters using LLM...")
            for cluster in new_clusters:
                if cluster.size() > 1:
                    combined_rule = self.clusterer.combine_rules_in_cluster(
                        cluster, self.rule_generator
                    )
                    if combined_rule:
                        logger.info(
                            f"Cluster {cluster.cluster_id}: Combined {cluster.size()} rules "
                            f"into generalized rule"
                        )

            # Step 7: Test on correct queries
            logger.info("\n[Step 7] Validating clusters on correct queries...")
            validated_clusters = self._validate_clusters(new_clusters)

            if len(validated_clusters) == 0:
                logger.warning("No clusters passed validation")
                return

            logger.info(
                f"Validated {len(validated_clusters)}/{len(new_clusters)} clusters "
                f"(pass rate >= {MIN_PASS_RATE*100}%)"
            )

            # Extract rules from validated clusters
            new_rules = []
            for cluster in validated_clusters:
                # Use combined rule if available, otherwise use cluster rules
                if hasattr(cluster, 'combined_rule') and cluster.combined_rule:
                    new_rules.append(cluster.combined_rule)
                else:
                    new_rules.extend(cluster.rules)

            # Add to current rules
            self.current_rules.extend(new_rules)
            self.current_clusters.extend(validated_clusters)

            self.metrics['total_rules_generated'] += len(new_rules)
            self.metrics['total_clusters_created'] += len(validated_clusters)

            logger.info(
                f"\n{'='*70}\n"
                f"Rule Generation Complete!\n"
                f"  New Rules: {len(new_rules)}\n"
                f"  Total Active Rules: {len(self.current_rules)}\n"
                f"  New Clusters: {len(validated_clusters)}\n"
                f"  Total Clusters: {len(self.current_clusters)}\n"
                f"{'='*70}\n"
            )

            # Save results incrementally
            self._save_incremental_results()

        except Exception as e:
            logger.error(f"Error during rule generation: {e}", exc_info=True)

    def _generate_triplets(self) -> List[RuleTriplet]:
        """Generate triplets for recently stored incorrect queries."""
        triplets = []

        # Process only queries that don't have triplets yet
        start_idx = len(self.current_triplets)
        queries_to_process = self.stored_incorrect_queries[start_idx:]

        for query_info in queries_to_process:
            try:
                # Generate explanation
                explanation = self.rule_generator.generate_explanation(
                    db_id=self.db_id,
                    question=query_info['question'],
                    predicted_sql=query_info['predicted_query'],
                    gold_sql=query_info['gold_query']
                )

                if not explanation:
                    continue

                # Generate rules
                rules = self.rule_generator.generate_rules(
                    incorrect_query=query_info['predicted_query'],
                    correct_query=query_info['gold_query'],
                    explanation=explanation
                )

                if not rules or len(rules) == 0:
                    continue

                # Create triplet
                triplet = RuleTriplet(
                    incorrect_query=query_info['predicted_query'],
                    correct_query=query_info['gold_query'],
                    explanation=explanation,
                    rules=rules
                )

                triplets.append(triplet)

            except Exception as e:
                logger.error(f"Failed to generate triplet: {e}")
                continue

        return triplets

    def _perform_clustering(self, triplets: List[RuleTriplet]) -> List[RuleCluster]:
        """Perform hierarchical clustering on triplets."""
        if len(triplets) == 0:
            return []

        # Get embeddings for triplets
        embeddings = []
        for triplet in triplets:
            embedding = self.embedder.embed_query(triplet.incorrect_query)
            embeddings.append(embedding)

        import numpy as np
        embeddings_matrix = np.array(embeddings)

        # Cluster
        clusters = self.clusterer.cluster_triplets(
            triplets=triplets,
            embeddings=embeddings_matrix
        )

        return clusters

    def _validate_clusters(self, clusters: List[RuleCluster]) -> List[RuleCluster]:
        """Validate clusters against correct queries (95% pass rate)."""
        if len(self.stored_correct_queries) == 0:
            logger.warning("No correct queries available for validation")
            return clusters  # Return all if we can't validate

        # Sample correct queries
        import random
        sample_size = max(1, int(len(self.stored_correct_queries) * CORRECT_QUERY_TEST_RATIO))
        sampled_correct = random.sample(self.stored_correct_queries, min(sample_size, len(self.stored_correct_queries)))

        logger.info(f"Testing on {len(sampled_correct)} correct queries (sample size: {CORRECT_QUERY_TEST_RATIO*100}%)")

        validated_clusters = []
        for cluster in clusters:
            false_positives, total = self.clusterer.test_cluster_on_correct_queries(
                cluster, sampled_correct
            )

            pass_rate = (total - false_positives) / total if total > 0 else 0

            if pass_rate >= MIN_PASS_RATE:
                validated_clusters.append(cluster)
                logger.info(
                    f"Cluster {cluster.cluster_id}: PASS (pass_rate={pass_rate*100:.2f}%, "
                    f"false_positives={false_positives}/{total})"
                )
            else:
                logger.warning(
                    f"Cluster {cluster.cluster_id}: FAIL (pass_rate={pass_rate*100:.2f}%, "
                    f"threshold={MIN_PASS_RATE*100}%)"
                )

        return validated_clusters

    def _save_incremental_results(self):
        """Save current state incrementally."""
        os.makedirs(RULE_STORAGE_PATH, exist_ok=True)

        # Save triplets
        triplets_file = os.path.join(RULE_STORAGE_PATH, "triplets.json")
        with open(triplets_file, 'w') as f:
            json.dump([t.to_dict() for t in self.current_triplets], f, indent=2)

        # Save clusters
        clusters_file = os.path.join(RULE_STORAGE_PATH, "clusters.json")
        with open(clusters_file, 'w') as f:
            json.dump([c.to_dict() for c in self.current_clusters], f, indent=2)

        # Save rules
        rules_file = os.path.join(RULE_STORAGE_PATH, "rules.json")
        with open(rules_file, 'w') as f:
            json.dump([r.to_dict() for r in self.current_rules], f, indent=2)

        # Save metrics
        metrics_file = os.path.join(RULE_STORAGE_PATH, "incremental_metrics.json")
        with open(metrics_file, 'w') as f:
            json.dump(self.metrics, f, indent=2)

        logger.info(f"Saved incremental results to {RULE_STORAGE_PATH}")

    def finalize(self) -> Dict:
        """
        Finalize the pipeline and return complete metrics.
        Call this at the end of evaluation.
        """
        logger.info(
            f"\n{'='*70}\n"
            f"Incremental Pipeline Finalization\n"
            f"{'='*70}\n"
            f"Total Queries Processed: {self.metrics['total_queries_processed']}\n"
            f"Queries Corrected: {self.metrics['queries_corrected']}\n"
            f"Rule Generation Triggers: {self.metrics['rule_generations_triggered']}\n"
            f"Total Rules Generated: {self.metrics['total_rules_generated']}\n"
            f"Total Clusters Created: {self.metrics['total_clusters_created']}\n"
            f"Active Rules: {len(self.current_rules)}\n"
            f"{'='*70}"
        )

        # Save final results
        self._save_incremental_results()

        # Save final summary
        summary_file = os.path.join(RULE_STORAGE_PATH, "pipeline_summary.json")
        summary = {
            'total_queries_processed': self.metrics['total_queries_processed'],
            'total_incorrect_queries': len(self.stored_incorrect_queries),
            'total_correct_queries': len(self.stored_correct_queries),
            'queries_corrected': self.metrics['queries_corrected'],
            'correction_rate': self.metrics['queries_corrected'] / self.metrics['total_queries_processed']
                if self.metrics['total_queries_processed'] > 0 else 0,
            'rule_generations_triggered': self.metrics['rule_generations_triggered'],
            'total_rules_generated': self.metrics['total_rules_generated'],
            'total_clusters_created': self.metrics['total_clusters_created'],
            'active_rules': len(self.current_rules)
        }

        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

        return summary
