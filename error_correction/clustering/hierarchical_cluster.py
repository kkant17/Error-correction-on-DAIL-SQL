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
    CLUSTER_COMBINE_THRESHOLD,
    PATTERN_DISTANCE_THRESHOLD,
    SOLUTION_DISTANCE_THRESHOLD
)
from error_correction.rule_engine.rule_schema import Rule, RuleTriplet, RuleCluster
from error_correction.rule_engine.rule_applicator import RuleApplicator

logger = logging.getLogger(__name__)


class HierarchicalRuleClusterer:
    """
    Performs three-level hierarchical clustering on rule triplets:
    Level 1: Group by error_type (categorical)
    Level 2: Sub-cluster by pattern+replacement similarity (cosine)
    Level 3: Sub-cluster by solution similarity (cosine)
    """

    def __init__(
        self,
        linkage_method: str = CLUSTERING_LINKAGE,
        metric: str = CLUSTERING_METRIC,
        combine_threshold: float = CLUSTER_COMBINE_THRESHOLD,
        pattern_distance_threshold: float = PATTERN_DISTANCE_THRESHOLD,
        solution_distance_threshold: float = SOLUTION_DISTANCE_THRESHOLD,
        embedder=None,
        rule_generator=None
    ):
        """
        Initialize the hierarchical clusterer.

        Args:
            linkage_method: Linkage method for hierarchical clustering
            metric: Distance metric (cosine recommended)
            combine_threshold: Threshold for combining queries (e.g., 0.90 for 90%)
            pattern_distance_threshold: Max cosine distance for pattern clustering
            solution_distance_threshold: Max cosine distance for solution clustering
            embedder: Embedder instance for generating text embeddings
            rule_generator: RuleGenerator instance for LLM-based rule merging
        """
        self.linkage_method = linkage_method
        self.metric = metric
        self.combine_threshold = combine_threshold
        self.pattern_distance_threshold = pattern_distance_threshold
        self.solution_distance_threshold = solution_distance_threshold
        self.embedder = embedder
        self.rule_applicator = RuleApplicator()
        self.rule_generator = rule_generator

        logger.info(
            f"HierarchicalRuleClusterer initialized: "
            f"linkage={linkage_method}, metric={metric}, "
            f"pattern_threshold={pattern_distance_threshold}, solution_threshold={solution_distance_threshold}"
        )

    def cluster_triplets(
        self,
        triplets: List[RuleTriplet],
        embeddings: np.ndarray = None,
        min_cluster_size: int = MIN_CLUSTER_SIZE,
        max_cluster_size: int = MAX_CLUSTER_SIZE
    ) -> List[RuleCluster]:
        """
        Three-level hierarchical clustering:
        Level 1: Group by error_type (categorical)
        Level 2: Sub-cluster by pattern+replacement similarity (cosine)
        Level 3: Sub-cluster by solution similarity (cosine)

        Args:
            triplets: List of RuleTriplets
            embeddings: Embedding matrix (optional, not used in new approach)
            min_cluster_size: Minimum cluster size
            max_cluster_size: Maximum cluster size

        Returns:
            List of RuleClusters
        """
        if len(triplets) < min_cluster_size:
            logger.warning(f"Not enough triplets ({len(triplets)}) for clustering")
            return []

        logger.info(f"Three-level clustering on {len(triplets)} triplets")

        # Level 1: Group by error_type (categorical)
        error_type_groups = self._group_by_error_type(triplets)
        logger.info(f"Level 1: Grouped into {len(error_type_groups)} error types")

        all_clusters = []
        
        for error_type, group in error_type_groups.items():
            logger.debug(f"Processing error_type={error_type} with {len(group)} triplets")
            
            if len(group) < min_cluster_size:
                # Too small to cluster, create single cluster
                cluster = self._create_cluster(group)
                if cluster:
                    all_clusters.append(cluster)
                continue

            # Level 2: Sub-cluster by pattern+replacement similarity
            pattern_clusters = self._cluster_by_pattern_replacement(group)
            logger.debug(f"Level 2: {len(pattern_clusters)} pattern clusters for {error_type}")

            for pattern_group in pattern_clusters:
                if len(pattern_group) < min_cluster_size:
                    cluster = self._create_cluster(pattern_group)
                    if cluster:
                        all_clusters.append(cluster)
                    continue

                # Level 3: Sub-cluster by solution similarity
                solution_clusters = self._cluster_by_solution(pattern_group)
                logger.debug(f"Level 3: {len(solution_clusters)} solution clusters")

                for sol_group in solution_clusters:
                    cluster = self._create_cluster(sol_group)
                    if cluster:
                        all_clusters.append(cluster)

        logger.info(f"Three-level clustering complete: {len(all_clusters)} final clusters")
        return all_clusters

    def _group_by_error_type(self, triplets: List[RuleTriplet]) -> Dict[str, List[RuleTriplet]]:
        """
        Level 1: Group triplets by error_type (categorical exact match).
        """
        groups = {}
        for triplet in triplets:
            # Get error_type from first rule
            error_type = triplet.rules[0].error_type if triplet.rules else "OTHER"
            if error_type not in groups:
                groups[error_type] = []
            groups[error_type].append(triplet)
        return groups

    def _cluster_by_pattern_replacement(self, triplets: List[RuleTriplet]) -> List[List[RuleTriplet]]:
        """
        Level 2: Cluster by pattern+replacement text using cosine distance.
        """
        if not self.embedder or len(triplets) < 2:
            return [triplets]

        # Create combined text for each triplet
        combined_texts = []
        for t in triplets:
            if t.rules:
                rule = t.rules[0]
                pattern = rule.pattern or ""
                replacement = getattr(rule, 'replacement', '') or ""
                text = f"{pattern} {replacement}"
            else:
                text = ""
            combined_texts.append(text)

        # Generate embeddings
        try:
            embeddings = self.embedder.embed_batch(combined_texts)
            return self._hierarchical_cluster(triplets, embeddings, self.pattern_distance_threshold)
        except Exception as e:
            logger.warning(f"Pattern clustering failed: {e}, returning single group")
            return [triplets]

    def _cluster_by_solution(self, triplets: List[RuleTriplet]) -> List[List[RuleTriplet]]:
        """
        Level 3: Cluster by solution text using cosine distance.
        """
        if not self.embedder or len(triplets) < 2:
            return [triplets]

        # Get solution text (fallback to explanation if no solution)
        solutions = []
        for t in triplets:
            solution = getattr(t, 'solution', '') or t.explanation
            solutions.append(solution)

        # Generate embeddings
        try:
            embeddings = self.embedder.embed_batch(solutions)
            return self._hierarchical_cluster(triplets, embeddings, self.solution_distance_threshold)
        except Exception as e:
            logger.warning(f"Solution clustering failed: {e}, returning single group")
            return [triplets]

    def _hierarchical_cluster(
        self,
        triplets: List[RuleTriplet],
        embeddings: np.ndarray,
        distance_threshold: float
    ) -> List[List[RuleTriplet]]:
        """
        Core hierarchical clustering with cosine distance.
        Stops merging when cosine distance exceeds threshold.
        """
        if len(triplets) < 2:
            return [triplets]

        try:
            # Compute cosine distance matrix
            distance_matrix = pdist(embeddings, metric='cosine')

            # Hierarchical clustering with average linkage (works with cosine)
            linkage_matrix = linkage(distance_matrix, method='average')

            # Cut tree at distance threshold
            cluster_labels = fcluster(linkage_matrix, distance_threshold, criterion='distance')

            # Group triplets by cluster label
            clusters_dict = {}
            for idx, label in enumerate(cluster_labels):
                if label not in clusters_dict:
                    clusters_dict[label] = []
                clusters_dict[label].append(triplets[idx])

            return list(clusters_dict.values())

        except Exception as e:
            logger.warning(f"Hierarchical clustering failed: {e}")
            return [triplets]

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
            triplets=triplets,  # Store all triplets for validation
            representative_triplet=representative
        )

        return cluster

    def validate_cluster(
        self,
        cluster: RuleCluster,
        validation_service=None,
        min_pass_rate: float = 0.5
    ) -> bool:
        """
        Validate a cluster by testing if the rule transforms triplets correctly.
        
        Validation checks:
        1. Rule pattern must match the incorrect queries
        2. Transformation must produce valid SQL
        3. At least min_pass_rate of triplets must pass
        
        Args:
            cluster: RuleCluster to validate
            validation_service: RuleValidationService for SQL validation (optional)
            min_pass_rate: Minimum ratio of triplets that must pass (default 0.5)

        Returns:
            True if valid, False otherwise
        """
        if not cluster.triplets:
            logger.warning(f"Cluster {cluster.cluster_id} has no triplets")
            return False

        # Use combined_rule if available, otherwise use first rule
        rule_to_test = cluster.combined_rule if cluster.combined_rule else (cluster.rules[0] if cluster.rules else None)
        
        if not rule_to_test:
            logger.warning(f"Cluster {cluster.cluster_id} has no rules to validate")
            return False

        passed_count = 0
        total_count = len(cluster.triplets)
        
        for triplet in cluster.triplets:
            incorrect_query = triplet.incorrect_query
            
            # Check 1: Pattern must match the incorrect query
            if not self.rule_applicator.matches_pattern(incorrect_query, rule_to_test.pattern):
                logger.debug(f"Pattern doesn't match triplet {triplet.triplet_id}")
                continue
            
            # Check 2: Apply transformation and verify it produces valid SQL
            try:
                replacement = getattr(rule_to_test, 'replacement', '') or ''
                if replacement:
                    import re
                    transformed = re.sub(
                        rule_to_test.pattern,
                        replacement,
                        incorrect_query,
                        count=1,
                        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL
                    )
                    
                    # Check transformation actually changed the query
                    if transformed == incorrect_query:
                        logger.debug(f"Transformation didn't change triplet {triplet.triplet_id}")
                        continue
                    
                    # Check 3: Validate transformed SQL syntax (if validation service available)
                    if validation_service:
                        if not validation_service._is_valid_sql(transformed):
                            logger.debug(f"Transformed SQL invalid for triplet {triplet.triplet_id}")
                            continue
                    
                    # Basic SQL validity checks (if no validation service)
                    else:
                        transformed_lower = transformed.lower().strip()
                        if not transformed_lower.startswith('select'):
                            continue
                        if transformed_lower.count(' where ') > 1:
                            continue
                    
                    passed_count += 1
                else:
                    # No replacement field - just check pattern matches
                    passed_count += 1
                    
            except Exception as e:
                logger.debug(f"Validation error for triplet {triplet.triplet_id}: {e}")
                continue
        
        pass_rate = passed_count / total_count if total_count > 0 else 0
        
        if pass_rate >= min_pass_rate:
            logger.info(
                f"Cluster {cluster.cluster_id} validated: "
                f"{passed_count}/{total_count} triplets passed ({pass_rate*100:.1f}%)"
            )
            return True
        else:
            logger.warning(
                f"Cluster {cluster.cluster_id} validation failed: "
                f"{passed_count}/{total_count} triplets passed ({pass_rate*100:.1f}% < {min_pass_rate*100}%)"
            )
            return False

    def filter_clusters(
        self,
        clusters: List[RuleCluster],
        total_triplets: int,
        validation_service=None
    ) -> List[RuleCluster]:
        """
        Filter clusters based on combine threshold and validation.

        Args:
            clusters: List of clusters
            total_triplets: Total number of triplets
            validation_service: RuleValidationService for SQL validation (optional)

        Returns:
            Filtered list of clusters
        """
        if not clusters:
            return []

        # Calculate how many triplets are combined (count triplets, not rules!)
        combined_count = sum(len(cluster.triplets) for cluster in clusters)
        combine_rate = combined_count / total_triplets if total_triplets > 0 else 0

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
            if self.validate_cluster(cluster, validation_service=validation_service):
                valid_clusters.append(cluster)
            else:
                logger.info(f"Discarding invalid cluster {cluster.cluster_id}")

        logger.info(f"Kept {len(valid_clusters)}/{len(clusters)} clusters after validation")
        return valid_clusters

    def combine_rules_in_cluster(
        self,
        cluster: RuleCluster,
        llm_generator=None,
        validation_service=None
    ) -> Optional[Rule]:
        """
        Combine rules in cluster using ONLY programmatic approaches (no LLM).
        
        Strategy:
        1. If only 1 rule → return it
        2. If all patterns identical → return first rule
        3. Calculate pattern similarity
        4. If patterns too different (< 0.5) → return best rule (no merge)
        5. Try programmatic merge using common prefix/suffix + alternation
        6. If programmatic merge fails → return best rule

        Args:
            cluster: RuleCluster with multiple rules
            llm_generator: Not used (kept for API compatibility)
            validation_service: RuleValidationService for validating merged rule (optional)

        Returns:
            Combined rule or None
        """
        from error_correction.rule_engine.rule_schema import RegexRule
        
        if cluster.size() == 0:
            return None

        if cluster.size() == 1:
            return cluster.rules[0]

        logger.info(f"Attempting to combine {cluster.size()} rules in cluster {cluster.cluster_id}")

        # Extract patterns and replacements
        patterns = [r.pattern for r in cluster.rules]
        replacements = [getattr(r, 'replacement', '') or '' for r in cluster.rules]
        
        # Strategy 1: Check if all patterns are identical
        unique_patterns = set(patterns)
        if len(unique_patterns) == 1:
            logger.info("All patterns identical, using first rule")
            return cluster.rules[0]
        
        # Strategy 2: Check if all replacements are identical (can merge patterns with alternation)
        unique_replacements = set(replacements)
        if len(unique_replacements) == 1:
            # Same replacement - can safely create alternation pattern
            merged_pattern = self._create_alternation_pattern(patterns)
            if merged_pattern:
                logger.info("Created alternation pattern (same replacement)")
                merged_rule = RegexRule(
                    pattern=merged_pattern,
                    replacement=replacements[0],
                    correction=cluster.rules[0].correction,
                    error_type=cluster.rules[0].error_type
                )
                if self._validate_merged_rule_basic(merged_rule, cluster):
                    cluster.combined_rule = merged_rule
                    return merged_rule
        
        # Strategy 3: Calculate pattern similarity
        similarity = self._calculate_pattern_similarity(patterns)
        logger.info(f"Pattern similarity: {similarity:.2f}")
        
        if similarity < 0.5:
            # Patterns are too different - don't force a merge
            logger.info(f"Patterns too different (similarity={similarity:.2f} < 0.5), not merging")
            best_rule = self._select_best_rule(cluster)
            return best_rule
        
        # Strategy 4: Try programmatic merging (find common prefix/suffix)
        merged_pattern = self._try_programmatic_merge(patterns)
        merged_replacement = self._try_programmatic_merge(replacements) if replacements[0] else None
        
        if merged_pattern and merged_replacement:
            logger.info("Successfully merged patterns programmatically")
            merged_rule = RegexRule(
                pattern=merged_pattern,
                replacement=merged_replacement,
                correction=cluster.rules[0].correction,
                error_type=cluster.rules[0].error_type
            )
            
            # Validate merged rule
            if validation_service and cluster.triplets:
                if self._validate_merged_rule(merged_rule, cluster, validation_service):
                    cluster.combined_rule = merged_rule
                    return merged_rule
                else:
                    logger.warning("Programmatically merged rule failed validation")
            elif self._validate_merged_rule_basic(merged_rule, cluster):
                cluster.combined_rule = merged_rule
                return merged_rule
        
        # Fallback: Return best rule without merging
        logger.info("Cannot merge patterns programmatically, using best rule")
        return self._select_best_rule(cluster)

    def _calculate_pattern_similarity(self, patterns: List[str]) -> float:
        """
        Calculate similarity between patterns using combined metrics.
        Returns 0.0 (completely different) to 1.0 (identical).
        """
        if len(patterns) < 2:
            return 1.0
        
        # Use both structural and token-based similarity
        structural_sim = self._calculate_structural_similarity(patterns)
        token_sim = self._calculate_token_similarity(patterns)
        
        # Structural similarity is more important for regex
        combined = 0.7 * structural_sim + 0.3 * token_sim
        
        return combined

    def _calculate_structural_similarity(self, patterns: List[str]) -> float:
        """
        Structural similarity - compares regex structure by normalizing specific values.
        """
        import re
        from difflib import SequenceMatcher
        
        def normalize_pattern(pattern: str) -> str:
            """Normalize pattern by replacing specific values with placeholders."""
            normalized = pattern
            
            # Replace common table names with <TABLE>
            tables = r'\b(singer|concert|stadium|pets|student|car|country|continent|model|maker)\b'
            normalized = re.sub(tables, '<TABLE>', normalized, flags=re.IGNORECASE)
            
            # Replace common column names with <COL>
            columns = r'\b(Age|Name|Year|Country|Id|Weight|Capacity|Population|Count|Model|Make)\b'
            normalized = re.sub(columns, '<COL>', normalized, flags=re.IGNORECASE)
            
            # Replace string literals with <STR>
            normalized = re.sub(r"'[^']*'", '<STR>', normalized)
            normalized = re.sub(r'"[^"]*"', '<STR>', normalized)
            
            # Replace numbers with <NUM>
            normalized = re.sub(r'\b\d+\b', '<NUM>', normalized)
            
            # Replace capture groups content but keep structure
            normalized = re.sub(r'\([^()]+\)', '(<CAPTURE>)', normalized)
            
            return normalized
        
        if len(patterns) < 2:
            return 1.0
        
        # Normalize all patterns
        normalized = [normalize_pattern(p) for p in patterns]
        
        # Calculate pairwise similarity
        total = 0
        count = 0
        for i in range(len(normalized)):
            for j in range(i + 1, len(normalized)):
                ratio = SequenceMatcher(None, normalized[i], normalized[j]).ratio()
                total += ratio
                count += 1
        
        return total / count if count > 0 else 0.0

    def _calculate_token_similarity(self, patterns: List[str]) -> float:
        """
        Token-based similarity using Jaccard index on SQL keywords and identifiers.
        """
        import re
        
        def tokenize_regex(pattern: str) -> set:
            """Split regex into tokens."""
            # SQL keywords
            keywords = set(re.findall(
                r'\b(SELECT|FROM|WHERE|JOIN|ON|GROUP|BY|ORDER|AND|OR|COUNT|AVG|MAX|MIN|SUM|DISTINCT|AS|LEFT|RIGHT|INNER|LIMIT|HAVING)\b', 
                pattern, re.IGNORECASE
            ))
            # Identifiers (table/column names)
            identifiers = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]{2,})\b', pattern))
            # Remove SQL keywords from identifiers
            sql_keywords = {'select', 'from', 'where', 'join', 'on', 'group', 'by', 'order', 
                          'and', 'or', 'count', 'avg', 'max', 'min', 'sum', 'distinct', 'as',
                          'left', 'right', 'inner', 'limit', 'having'}
            identifiers = {i for i in identifiers if i.lower() not in sql_keywords}
            
            return keywords | identifiers
        
        if len(patterns) < 2:
            return 1.0
        
        token_sets = [tokenize_regex(p) for p in patterns]
        
        # Jaccard similarity: |A ∩ B| / |A ∪ B|
        total = 0
        count = 0
        for i in range(len(token_sets)):
            for j in range(i + 1, len(token_sets)):
                intersection = len(token_sets[i] & token_sets[j])
                union = len(token_sets[i] | token_sets[j])
                jaccard = intersection / union if union > 0 else 0
                total += jaccard
                count += 1
        
        return total / count if count > 0 else 0.0

    def _try_programmatic_merge(self, strings: List[str]) -> Optional[str]:
        """
        Try to merge strings by finding common prefix/suffix and using alternation.
        Returns merged string or None if too different.
        """
        import re
        import os
        
        if not strings or len(strings) < 2:
            return strings[0] if strings else None
        
        # Remove empty strings
        strings = [s for s in strings if s]
        if len(strings) < 2:
            return strings[0] if strings else None
        
        # Find common prefix
        prefix = os.path.commonprefix(strings)
        
        # Find common suffix
        reversed_strings = [s[::-1] for s in strings]
        suffix = os.path.commonprefix(reversed_strings)[::-1]
        
        # If very little in common, can't merge programmatically
        min_common = min(len(prefix), len(suffix))
        max_len = max(len(s) for s in strings)
        
        if min_common < 10 and (len(prefix) + len(suffix)) < max_len * 0.3:
            return None
        
        # Extract varying middle parts
        middles = []
        for s in strings:
            start = len(prefix)
            end = len(s) - len(suffix) if suffix else len(s)
            if end > start:
                middle = s[start:end]
                if middle:
                    middles.append(middle)
        
        if not middles:
            return prefix + suffix if prefix or suffix else None
        
        # Create alternation for different middles
        unique_middles = list(set(middles))
        
        if len(unique_middles) == 1:
            return prefix + unique_middles[0] + suffix
        elif len(unique_middles) <= 5:
            # Don't create huge alternations - escape special regex chars in middles
            escaped_middles = []
            for m in unique_middles:
                # Only escape if the middle contains special chars that aren't already regex
                if not any(c in m for c in ['.*', '.+', '\\d', '\\w', '\\s']):
                    escaped_middles.append(re.escape(m))
                else:
                    escaped_middles.append(m)
            
            alternation = f"({'|'.join(escaped_middles)})"
            return prefix + alternation + suffix
        
        return None

    def _select_best_rule(self, cluster: RuleCluster) -> Rule:
        """
        Select the best rule from cluster based on how many triplets it matches.
        """
        if not cluster.rules:
            return None
        
        best_rule = cluster.rules[0]
        best_score = 0
        
        for rule in cluster.rules:
            score = 0
            for triplet in cluster.triplets:
                if self.rule_applicator.matches_pattern(triplet.incorrect_query, rule.pattern):
                    score += 1
            
            if score > best_score:
                best_score = score
                best_rule = rule
        
        logger.debug(f"Selected best rule with score {best_score}/{len(cluster.triplets)}")
        return best_rule

    def _create_alternation_pattern(self, patterns: List[str]) -> Optional[str]:
        """
        Create a single pattern using alternation: (pattern1|pattern2|pattern3)
        Only works if patterns are reasonably short.
        """
        if not patterns or len(patterns) < 2:
            return patterns[0] if patterns else None
        
        # Don't create alternations for very long patterns
        max_len = max(len(p) for p in patterns)
        if max_len > 200:
            return None
        
        # Don't create alternations with too many patterns
        if len(patterns) > 5:
            return None
        
        unique_patterns = list(set(patterns))
        if len(unique_patterns) == 1:
            return unique_patterns[0]
        
        # Create alternation
        alternation = f"({'|'.join(unique_patterns)})"
        return alternation

    def _validate_merged_rule_basic(self, rule: Rule, cluster: RuleCluster) -> bool:
        """
        Basic validation without external validation service.
        Checks that merged rule matches at least 50% of triplets.
        """
        if not cluster.triplets:
            return True
        
        import re
        matched = 0
        for triplet in cluster.triplets:
            try:
                if re.search(rule.pattern, triplet.incorrect_query, re.IGNORECASE):
                    matched += 1
            except re.error:
                return False  # Invalid regex
        
        match_rate = matched / len(cluster.triplets)
        logger.debug(f"Basic validation: {matched}/{len(cluster.triplets)} matched ({match_rate:.1%})")
        return match_rate >= 0.5

    def _validate_merged_rule(
        self, 
        rule: Rule, 
        cluster: RuleCluster, 
        validation_service
    ) -> bool:
        """Validate a merged rule against cluster's triplets using validation service."""
        try:
            all_passed, results = validation_service.validate_rule_on_representatives(
                rule, cluster.triplets
            )
            if all_passed:
                logger.info(f"Merged rule passed validation on {len(cluster.triplets)} triplets")
                return True
            else:
                passed_count = sum(r.passed for r in results)
                logger.warning(f"Merged rule validation: {passed_count}/{len(results)} passed")
                return passed_count >= len(results) * 0.5  # Accept if at least 50% pass
        except Exception as e:
            logger.warning(f"Validation error: {e}")
            # Fall back to basic validation
            return self._validate_merged_rule_basic(rule, cluster)

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

        # Use combined_rule if available, otherwise test individual rules
        rules_to_test = [cluster.combined_rule] if cluster.combined_rule else cluster.rules

        for query in correct_queries:
            for rule in rules_to_test:
                if rule and self.rule_applicator.matches_pattern(query, rule.pattern):
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

    def get_final_rules(self, clusters: List[RuleCluster]) -> List[Rule]:
        """
        Extract the final merged rule from each cluster for validation.

        For each cluster:
        - If cluster has a combined_rule (from merging), use that
        - Otherwise, use the first rule as representative

        Args:
            clusters: List of RuleClusters after clustering

        Returns:
            List of final rules (one per cluster) for validation
        """
        final_rules = []

        for cluster in clusters:
            if cluster.combined_rule:
                # Use the merged rule
                final_rules.append(cluster.combined_rule)
                logger.debug(f"Cluster {cluster.cluster_id}: using merged rule")
            elif cluster.rules:
                # Use first rule as representative
                final_rules.append(cluster.rules[0])
                logger.debug(f"Cluster {cluster.cluster_id}: using representative rule")
            else:
                logger.warning(f"Cluster {cluster.cluster_id}: no rules found")

        logger.info(f"Extracted {len(final_rules)} final rules from {len(clusters)} clusters")
        return final_rules
