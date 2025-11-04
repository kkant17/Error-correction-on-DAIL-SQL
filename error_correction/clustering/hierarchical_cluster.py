"""
Hierarchical Clustering for SQL Error Correction Rules
Combines similar queries/rules and validates combined rules
"""
import numpy as np
import logging
from typing import List, Dict, Tuple, Optional
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist, squareform

from error_correction.config import (
    CLUSTERING_LINKAGE,
    CLUSTERING_METRIC,
    MIN_CLUSTER_SIZE,
    MAX_CLUSTER_SIZE,
    CLUSTER_COMBINE_THRESHOLD
)
from error_correction.rule_engine.rule_schema import Rule, RuleTriplet, RuleCluster
from error_correction.rule_engine.rule_applicator import RuleApplicator

logger = logging.getLogger(__name__)


class HierarchicalRuleClusterer:
    """
    Performs hierarchical clustering on rule triplets to combine similar rules.
    """

    def __init__(
        self,
        linkage_method: str = CLUSTERING_LINKAGE,
        metric: str = CLUSTERING_METRIC,
        combine_threshold: float = CLUSTER_COMBINE_THRESHOLD
    ):
        """
        Initialize the hierarchical clusterer.

        Args:
            linkage_method: Linkage method for hierarchical clustering
            metric: Distance metric
            combine_threshold: Threshold for combining queries (e.g., 0.90 for 90%)
        """
        self.linkage_method = linkage_method
        self.metric = metric
        self.combine_threshold = combine_threshold
        self.rule_applicator = RuleApplicator()

        logger.info(
            f"HierarchicalRuleClusterer initialized: "
            f"linkage={linkage_method}, metric={metric}, threshold={combine_threshold}"
        )

    def cluster_triplets(
        self,
        triplets: List[RuleTriplet],
        embeddings: np.ndarray,
        min_cluster_size: int = MIN_CLUSTER_SIZE,
        max_cluster_size: int = MAX_CLUSTER_SIZE
    ) -> List[RuleCluster]:
        """
        Cluster rule triplets based on query/rule similarity.

        Args:
            triplets: List of RuleTriplets
            embeddings: Embedding matrix for queries (n_triplets x embedding_dim)
            min_cluster_size: Minimum cluster size
            max_cluster_size: Maximum cluster size

        Returns:
            List of RuleClusters
        """
        if len(triplets) < min_cluster_size:
            logger.warning(f"Not enough triplets ({len(triplets)}) for clustering")
            return []

        logger.info(f"Clustering {len(triplets)} triplets")

        # Compute distance matrix
        distance_matrix = pdist(embeddings, metric=self.metric)

        # Perform hierarchical clustering
        linkage_matrix = linkage(distance_matrix, method=self.linkage_method)

        # Determine optimal number of clusters
        # We'll try different numbers and find the best
        best_clusters = []
        best_combine_rate = 0

        for n_clusters in range(2, min(len(triplets) // min_cluster_size + 1, 10)):
            cluster_labels = fcluster(linkage_matrix, n_clusters, criterion='maxclust')

            # Group triplets by cluster
            clusters_dict = {}
            for idx, label in enumerate(cluster_labels):
                if label not in clusters_dict:
                    clusters_dict[label] = []
                clusters_dict[label].append(idx)

            # Create RuleCluster objects
            clusters = []
            total_triplets = 0
            combined_triplets = 0

            for label, indices in clusters_dict.items():
                if len(indices) < min_cluster_size:
                    continue
                if len(indices) > max_cluster_size:
                    # Split large clusters
                    continue

                cluster_triplets = [triplets[i] for i in indices]
                cluster = self._create_cluster(cluster_triplets)

                if cluster:
                    clusters.append(cluster)
                    total_triplets += len(indices)
                    if len(indices) >= min_cluster_size:
                        combined_triplets += len(indices)

            # Calculate combine rate
            combine_rate = combined_triplets / len(triplets) if len(triplets) > 0 else 0

            logger.debug(
                f"n_clusters={n_clusters}: {len(clusters)} valid clusters, "
                f"combine_rate={combine_rate:.2%}"
            )

            if combine_rate > best_combine_rate:
                best_combine_rate = combine_rate
                best_clusters = clusters

        logger.info(
            f"Best clustering: {len(best_clusters)} clusters, "
            f"combine_rate={best_combine_rate:.2%}"
        )

        return best_clusters

    def _create_cluster(self, triplets: List[RuleTriplet]) -> Optional[RuleCluster]:
        """
        Create a RuleCluster from a list of triplets.

        Args:
            triplets: List of triplets in the cluster

        Returns:
            RuleCluster or None if invalid
        """
        if not triplets:
            return None

        # Select representative triplet (first one for now)
        representative = triplets[0]

        # Collect all rules from all triplets
        all_rules = []
        for triplet in triplets:
            all_rules.extend(triplet.rules)

        cluster = RuleCluster(
            rules=all_rules,
            representative_triplet=representative
        )

        return cluster

    def validate_cluster(
        self,
        cluster: RuleCluster,
        db_path: str = None
    ) -> bool:
        """
        Validate a cluster by testing if the combined rule still corrects
        the representative query.

        Args:
            cluster: RuleCluster to validate
            db_path: Database path for query execution (optional)

        Returns:
            True if valid, False otherwise
        """
        if not cluster.representative_triplet:
            logger.warning("Cluster has no representative triplet")
            return False

        # For now, just check if rules match the representative's incorrect query
        # TODO: Implement actual execution-based validation
        representative_query = cluster.representative_triplet.incorrect_query

        for rule in cluster.rules:
            if self.rule_applicator.matches_pattern(representative_query, rule.pattern):
                logger.info(f"Cluster {cluster.cluster_id} validated successfully")
                return True

        logger.warning(f"Cluster {cluster.cluster_id} validation failed")
        return False

    def filter_clusters(
        self,
        clusters: List[RuleCluster],
        total_triplets: int
    ) -> List[RuleCluster]:
        """
        Filter clusters based on combine threshold.

        Args:
            clusters: List of clusters
            total_triplets: Total number of triplets

        Returns:
            Filtered list of clusters
        """
        if not clusters:
            return []

        # Calculate how many triplets are combined
        combined_count = sum(cluster.size() for cluster in clusters)
        combine_rate = combined_count / total_triplets

        logger.info(
            f"Combine rate: {combine_rate:.2%} "
            f"(threshold: {self.combine_threshold:.2%})"
        )

        if combine_rate < self.combine_threshold:
            logger.warning(
                f"Combine rate {combine_rate:.2%} below threshold "
                f"{self.combine_threshold:.2%}, discarding clusters"
            )
            return []

        # Validate each cluster
        valid_clusters = []
        for cluster in clusters:
            if self.validate_cluster(cluster):
                valid_clusters.append(cluster)
            else:
                logger.info(f"Discarding invalid cluster {cluster.cluster_id}")

        logger.info(f"Kept {len(valid_clusters)}/{len(clusters)} clusters after validation")
        return valid_clusters

    def combine_rules_in_cluster(
        self,
        cluster: RuleCluster,
        llm_generator = None
    ) -> Optional[Rule]:
        """
        Combine multiple rules in a cluster into a single generalized rule using LLM.
        Implements the "Condense Rules" step from methodology.

        Args:
            cluster: RuleCluster with multiple rules
            llm_generator: RuleGenerator instance for LLM-based combination (optional)

        Returns:
            Combined rule or None
        """
        if cluster.size() == 0:
            return None

        if cluster.size() == 1:
            return cluster.rules[0]

        logger.info(f"Combining {cluster.size()} rules in cluster {cluster.cluster_id}")

        # If no LLM generator provided, return first rule as fallback
        if not llm_generator:
            logger.warning("No LLM generator provided, using first rule as representative")
            return cluster.rules[0]

        try:
            # Collect all rule information
            rules_info = []
            for rule in cluster.rules:
                rules_info.append({
                    'pattern': rule.pattern,
                    'correction': rule.correction,
                    'error_type': rule.error_type
                })

            # Build prompt for LLM to condense rules
            prompt = self._build_rule_condensation_prompt(rules_info, cluster)

            # Call LLM to generate combined rule
            from llm.chatgpt import ask_llm
            response = ask_llm(prompt, model=llm_generator.model if llm_generator else "gpt-4", temperature=0.3)

            # Parse LLM response to extract combined rule
            combined_rule = self._parse_combined_rule(response, cluster.rules[0].error_type)

            if combined_rule:
                logger.info(f"Successfully combined {cluster.size()} rules into one")
                cluster.combined_rule = combined_rule
                return combined_rule
            else:
                logger.warning("Failed to parse combined rule, using first rule as fallback")
                return cluster.rules[0]

        except Exception as e:
            logger.error(f"Error combining rules: {e}")
            return cluster.rules[0]

    def _build_rule_condensation_prompt(self, rules_info: List[Dict], cluster: RuleCluster) -> str:
        """Build prompt for LLM to condense multiple rules into one."""
        rules_text = "\n".join([
            f"Rule {i+1}:\n  Pattern: {r['pattern']}\n  Correction: {r['correction']}\n  Type: {r['error_type']}"
            for i, r in enumerate(rules_info)
        ])

        prompt = f"""You are a SQL expert. You have {len(rules_info)} similar error correction rules that need to be condensed into a single, more general rule.

Rules to combine:
{rules_text}

Please create ONE combined rule that:
1. Has a regex pattern that matches all the error cases covered by individual rules
2. Has a clear, generalized correction description
3. Maintains the same error type

Output the combined rule in this JSON format:
{{
    "pattern": "<generalized regex pattern>",
    "correction": "<generalized correction description>",
    "error_type": "{rules_info[0]['error_type']}"
}}

Only output the JSON, nothing else."""

        return prompt

    def _parse_combined_rule(self, llm_response: str, error_type: str) -> Optional[Rule]:
        """Parse LLM response to extract combined rule."""
        import json
        import re

        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                rule_data = json.loads(json_str)

                return Rule(
                    pattern=rule_data.get('pattern', ''),
                    correction=rule_data.get('correction', ''),
                    error_type=rule_data.get('error_type', error_type)
                )
        except Exception as e:
            logger.error(f"Failed to parse combined rule: {e}")

        return None

    def test_cluster_on_correct_queries(
        self,
        cluster: RuleCluster,
        correct_queries: List[str]
    ) -> Tuple[int, int]:
        """
        Test if cluster's rules incorrectly match correct queries.

        Args:
            cluster: RuleCluster to test
            correct_queries: List of correct queries to test against

        Returns:
            Tuple of (num_false_positives, total_tested)
        """
        false_positives = 0

        for query in correct_queries:
            for rule in cluster.rules:
                if self.rule_applicator.matches_pattern(query, rule.pattern):
                    false_positives += 1
                    logger.warning(
                        f"Rule {rule.rule_id} incorrectly matched correct query: {query[:50]}..."
                    )
                    break  # Count once per query

        logger.info(
            f"Cluster {cluster.cluster_id}: {false_positives}/{len(correct_queries)} "
            f"false positives"
        )

        return false_positives, len(correct_queries)
