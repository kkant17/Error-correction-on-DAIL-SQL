"""
Main Error Correction Pipeline Orchestrator

This script orchestrates the entire error correction pipeline:
1. Parse evaluation results to identify correct/incorrect queries
2. Store queries in vector databases
3. Generate explanations for incorrect queries
4. Generate correction rules
5. Collect triplets <query, explanation, rules>
6. Perform hierarchical clustering
7. Test rules on correct queries
8. Save validated rules
"""
import os
import sys
import json
import argparse
import logging
import random
from typing import List, Dict, Tuple
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from error_correction.config import (
    MIN_TRIPLETS_FOR_CLUSTERING,
    CORRECT_QUERY_TEST_RATIO,
    CLUSTER_COMBINE_THRESHOLD,
    MIN_PASS_RATE,
    RULE_STORAGE_PATH,
    LOG_LEVEL,
    LOG_FILE,
    VECTOR_DB_BASE_DIR,
    ENABLE_TRANSFORMATION,
    ENABLE_EXECUTION_VALIDATION,
    TRANSFORMATION_CONFIDENCE_THRESHOLD,
    EXECUTION_TIMEOUT
)
from error_correction.vector_store import SQLEmbedder, VectorDatabase, CorrectQueriesDB, IncorrectQueriesDB
from error_correction.rule_engine import Rule, RuleTriplet, RuleGenerator, RuleApplicator
from error_correction.clustering import HierarchicalRuleClusterer
from llm.chatgpt import init_chatgpt

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ErrorCorrectionPipeline:
    """
    Main pipeline for SQL error correction using LLM-generated rules
    and hierarchical clustering.
    """

    def __init__(
        self,
        model: str = "gpt-4",
        openai_api_key: str = None,
        openai_api_base: str = "",
        temperature: float = 0.3,
        enable_transformation: bool = ENABLE_TRANSFORMATION,
        enable_execution_validation: bool = ENABLE_EXECUTION_VALIDATION,
        transformation_confidence_threshold: float = TRANSFORMATION_CONFIDENCE_THRESHOLD
    ):
        """
        Initialize the pipeline.

        Args:
            model: LLM model to use
            openai_api_key: OpenAI API key
            openai_api_base: OpenAI API base URL
            temperature: Temperature for LLM generation
            enable_transformation: Enable query transformation
            enable_execution_validation: Enable execution-based validation
            transformation_confidence_threshold: Minimum confidence to apply transformation
        """
        logger.info("Initializing Error Correction Pipeline")

        # Initialize LLM
        if openai_api_key:
            init_chatgpt(openai_api_key, "", model, openai_api_base)

        # Initialize components
        self.embedder = SQLEmbedder()
        self.correct_db = CorrectQueriesDB()
        self.incorrect_db = IncorrectQueriesDB()
        self.rule_generator = RuleGenerator(model=model, temperature=temperature)
        self.rule_applicator = RuleApplicator()
        self.clusterer = HierarchicalRuleClusterer()

        # Transformation settings
        self.enable_transformation = enable_transformation
        self.enable_execution_validation = enable_execution_validation
        self.transformation_confidence_threshold = transformation_confidence_threshold

        # Storage for triplets and rules
        self.triplets: List[RuleTriplet] = []
        self.validated_rules: List[Rule] = []

        # Metrics tracking
        self.metrics = {
            'total_queries': 0,
            'transformation_attempted': 0,
            'transformation_successful': 0,
            'transformation_failed': 0,
            'execution_validated': 0,
            'execution_failed': 0,
            'transformations': []  # Detailed transformation results
        }

        os.makedirs(RULE_STORAGE_PATH, exist_ok=True)
        os.makedirs(VECTOR_DB_BASE_DIR, exist_ok=True)

        logger.info("Pipeline initialized successfully")
        logger.info(f"Transformation enabled: {self.enable_transformation}")
        logger.info(f"Execution validation enabled: {self.enable_execution_validation}")

    def parse_evaluation_results(
        self,
        eval_file: str,
        predictions_file: str,
        questions_file: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Parse evaluation results to identify correct and incorrect queries.

        Args:
            eval_file: Path to evaluation results file
            predictions_file: Path to predictions file
            questions_file: Path to questions JSON file

        Returns:
            Tuple of (correct_queries, incorrect_queries)
        """
        logger.info(f"Parsing evaluation results from {eval_file}")

        # Load predictions
        with open(predictions_file, 'r') as f:
            predictions = [line.strip() for line in f.readlines()]

        # Load questions data
        with open(questions_file, 'r') as f:
            questions_data = json.load(f)
            questions = questions_data['questions']

        # Parse evaluation results
        correct_queries = []
        incorrect_queries = []

        with open(eval_file, 'r') as f:
            lines = f.readlines()

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if line.startswith("Question") and "CORRECT" in line:
                # Extract question index
                parts = line.split()
                idx = int(parts[1])

                if idx < len(predictions) and idx < len(questions):
                    correct_queries.append({
                        'index': idx,
                        'predicted_sql': predictions[idx],
                        'gold_sql': "SELECT " + questions[idx]['response'],
                        'db_id': questions[idx]['db_id'],
                        'question': questions[idx].get('question', '')
                    })

            elif line.startswith("Question") and "INCORRECT" in line:
                # Extract question index
                parts = line.split()
                idx = int(parts[1])

                # Next lines should have gold and predicted
                gold_sql = ""
                pred_sql = ""

                if i + 1 < len(lines) and "Gold:" in lines[i + 1]:
                    gold_sql = lines[i + 1].split("Gold:", 1)[1].strip()
                if i + 2 < len(lines) and "Pred:" in lines[i + 2]:
                    pred_sql = lines[i + 2].split("Pred:", 1)[1].strip()

                if idx < len(questions):
                    incorrect_queries.append({
                        'index': idx,
                        'predicted_sql': pred_sql or (predictions[idx] if idx < len(predictions) else ""),
                        'gold_sql': gold_sql or ("SELECT " + questions[idx]['response']),
                        'db_id': questions[idx]['db_id'],
                        'question': questions[idx].get('question', '')
                    })

                i += 2  # Skip the gold and pred lines

            i += 1

        logger.info(f"Found {len(correct_queries)} correct and {len(incorrect_queries)} incorrect queries")
        return correct_queries, incorrect_queries

    def store_queries_in_vector_db(
        self,
        correct_queries: List[Dict],
        incorrect_queries: List[Dict]
    ):
        """
        Store queries in vector databases.

        Args:
            correct_queries: List of correct query dicts
            incorrect_queries: List of incorrect query dicts
        """
        logger.info("Storing queries in vector databases")

        # Store correct queries
        if correct_queries:
            correct_sqls = [q['predicted_sql'] for q in correct_queries]
            correct_embeddings = self.embedder.embed_batch(correct_sqls)
            correct_metadatas = [
                {'db_id': q['db_id'], 'question': q['question']}
                for q in correct_queries
            ]
            self.correct_db.add_batch(correct_sqls, correct_embeddings, correct_metadatas)
            logger.info(f"Stored {len(correct_queries)} correct queries")

        # Store incorrect queries
        if incorrect_queries:
            incorrect_sqls = [q['predicted_sql'] for q in incorrect_queries]
            incorrect_embeddings = self.embedder.embed_batch(incorrect_sqls)
            incorrect_metadatas = [
                {'db_id': q['db_id'], 'question': q['question'], 'gold_sql': q['gold_sql']}
                for q in incorrect_queries
            ]
            self.incorrect_db.add_batch(incorrect_sqls, incorrect_embeddings, incorrect_metadatas)
            logger.info(f"Stored {len(incorrect_queries)} incorrect queries")

    def generate_triplets(
        self,
        incorrect_queries: List[Dict],
        max_triplets: int = None
    ) -> List[RuleTriplet]:
        """
        Generate triplets <query, explanation, rules> for incorrect queries.

        Args:
            incorrect_queries: List of incorrect query dicts
            max_triplets: Maximum number of triplets to generate (None for all)

        Returns:
            List of RuleTriplets
        """
        logger.info("Generating triplets")

        triplets = []
        queries_to_process = incorrect_queries[:max_triplets] if max_triplets else incorrect_queries

        for i, query_data in enumerate(queries_to_process):
            logger.info(f"Processing query {i+1}/{len(queries_to_process)}")

            try:
                # Generate explanation
                explanation = self.rule_generator.generate_explanation(
                    predicted_sql=query_data['predicted_sql'],
                    gold_sql=query_data['gold_sql'],
                    db_id=query_data['db_id'],
                    question=query_data['question']
                )

                # Generate rules
                rules = self.rule_generator.generate_rules(
                    incorrect_query=query_data['predicted_sql'],
                    correct_query=query_data['gold_sql'],
                    explanation=explanation
                )

                if not rules:
                    logger.warning(f"No rules generated for query {i}")
                    continue

                # Verify rules
                valid_rules = []
                for rule in rules:
                    if self.rule_applicator.verify_rule(query_data['predicted_sql'], rule):
                        valid_rules.append(rule)
                    else:
                        logger.warning(f"Rule {rule.rule_id} failed verification, discarding")

                if not valid_rules:
                    logger.warning(f"No valid rules for query {i}")
                    continue

                # Create triplet
                triplet = RuleTriplet(
                    incorrect_query=query_data['predicted_sql'],
                    correct_query=query_data['gold_sql'],
                    explanation=explanation,
                    rules=valid_rules,
                    db_id=query_data['db_id'],
                    question=query_data['question']
                )

                triplets.append(triplet)
                logger.info(f"Created triplet with {len(valid_rules)} rule(s)")

            except Exception as e:
                logger.error(f"Error processing query {i}: {e}")
                continue

        logger.info(f"Generated {len(triplets)} triplets")
        self.triplets.extend(triplets)
        return triplets

    def perform_clustering(self) -> List:
        """
        Perform hierarchical clustering on collected triplets.

        Returns:
            List of validated RuleClusters
        """
        if len(self.triplets) < MIN_TRIPLETS_FOR_CLUSTERING:
            logger.warning(
                f"Not enough triplets ({len(self.triplets)}) for clustering "
                f"(minimum: {MIN_TRIPLETS_FOR_CLUSTERING})"
            )
            return []

        logger.info(f"Performing hierarchical clustering on {len(self.triplets)} triplets")

        # Get embeddings for incorrect queries
        incorrect_queries = [t.incorrect_query for t in self.triplets]
        embeddings = self.embedder.embed_batch(incorrect_queries)

        # Cluster
        clusters = self.clusterer.cluster_triplets(self.triplets, embeddings)

        # Filter clusters based on combine threshold
        valid_clusters = self.clusterer.filter_clusters(clusters, len(self.triplets))

        logger.info(f"Created {len(valid_clusters)} valid clusters")
        return valid_clusters

    def apply_transformations(
        self,
        incorrect_queries: List[Dict],
        clusters: List
    ) -> Dict[str, str]:
        """
        Apply transformations to incorrect queries using validated rules.

        Args:
            incorrect_queries: List of incorrect query dicts
            clusters: List of validated RuleClusters

        Returns:
            Dictionary mapping original query → transformed query
        """
        if not self.enable_transformation:
            logger.info("Transformation disabled, skipping")
            return {}

        logger.info(f"Applying transformations to {len(incorrect_queries)} queries")

        transformations = {}
        self.metrics['total_queries'] = len(incorrect_queries)

        # Build a rule lookup from clusters
        all_rules = []
        for cluster in clusters:
            all_rules.extend(cluster.rules)

        for i, query_data in enumerate(incorrect_queries):
            incorrect_query = query_data['predicted_sql']
            gold_query = query_data['gold_sql']

            logger.info(f"Processing query {i+1}/{len(incorrect_queries)}")

            try:
                # Find matching rules for this query
                matching_rules = []
                for rule in all_rules:
                    if self.rule_applicator.verify_rule(incorrect_query, rule):
                        matching_rules.append(rule)

                if not matching_rules:
                    logger.warning(f"No matching rules for query {i}")
                    self.metrics['transformation_failed'] += 1
                    transformations[incorrect_query] = incorrect_query
                    self.metrics['transformations'].append({
                        'original_query': incorrect_query,
                        'transformed_query': incorrect_query,
                        'gold_query': gold_query,
                        'success': False,
                        'reason': 'No matching rules',
                        'rule_id': None
                    })
                    continue

                # Use the first matching rule (could be enhanced with confidence scoring)
                rule = matching_rules[0]
                self.metrics['transformation_attempted'] += 1

                # Apply transformation
                transformed_query = self.rule_applicator.apply_rule(incorrect_query, rule)

                # Check if transformation actually changed the query
                if transformed_query != incorrect_query:
                    transformations[incorrect_query] = transformed_query
                    self.metrics['transformation_successful'] += 1
                    logger.info(f"Successfully transformed query using rule {rule.rule_id}")

                    self.metrics['transformations'].append({
                        'original_query': incorrect_query,
                        'transformed_query': transformed_query,
                        'gold_query': gold_query,
                        'success': True,
                        'reason': 'Transformation applied',
                        'rule_id': rule.rule_id,
                        'error_type': rule.error_type,
                        'pattern': rule.pattern
                    })
                else:
                    transformations[incorrect_query] = incorrect_query
                    self.metrics['transformation_failed'] += 1
                    logger.warning(f"Transformation did not change query for rule {rule.rule_id}")

                    self.metrics['transformations'].append({
                        'original_query': incorrect_query,
                        'transformed_query': incorrect_query,
                        'gold_query': gold_query,
                        'success': False,
                        'reason': 'Transformation returned unchanged query (not implemented)',
                        'rule_id': rule.rule_id
                    })

            except Exception as e:
                logger.error(f"Error transforming query {i}: {e}")
                transformations[incorrect_query] = incorrect_query
                self.metrics['transformation_failed'] += 1
                self.metrics['transformations'].append({
                    'original_query': incorrect_query,
                    'transformed_query': incorrect_query,
                    'gold_query': gold_query,
                    'success': False,
                    'reason': f'Exception: {str(e)}',
                    'rule_id': None
                })

        logger.info(
            f"Transformation complete: {self.metrics['transformation_successful']} successful, "
            f"{self.metrics['transformation_failed']} failed"
        )

        return transformations

    def validate_transformations(
        self,
        transformations: Dict[str, str]
    ) -> Dict[str, str]:
        """
        Validate transformed queries through execution (optional).

        Args:
            transformations: Dictionary mapping original → transformed queries

        Returns:
            Dictionary of validated transformations
        """
        if not self.enable_execution_validation:
            logger.info("Execution validation disabled, skipping")
            return transformations

        logger.info(f"Validating {len(transformations)} transformations through execution")
        logger.warning(
            "Execution validation is not fully implemented yet. "
            "This requires a database executor with safety checks. "
            "Skipping execution validation."
        )

        # TODO: Implement actual execution-based validation
        # 1. Set up read-only database connection
        # 2. Execute transformed queries with timeout
        # 3. Compare results with gold queries
        # 4. Update metrics for execution success/failure
        # 5. Filter out transformations that fail execution

        # For now, return all transformations without validation
        return transformations

    def test_rules_on_correct_queries(
        self,
        clusters: List,
        sample_ratio: float = CORRECT_QUERY_TEST_RATIO,
        min_pass_rate: float = MIN_PASS_RATE
    ) -> List:
        """
        Test clustered rules on correct queries (95% pass rate requirement per methodology).

        Args:
            clusters: List of RuleClusters
            sample_ratio: Ratio of correct queries to sample
            min_pass_rate: Minimum pass rate required (default 0.95)

        Returns:
            List of clusters that passed testing
        """
        logger.info(f"Testing rules on correct queries (min pass rate: {min_pass_rate*100}%)")

        # Get all correct queries from vector DB
        all_correct = self.correct_db.get_all_queries()

        if not all_correct:
            logger.warning("No correct queries available for testing")
            return clusters

        # Sample correct queries
        sample_size = max(1, int(len(all_correct) * sample_ratio))
        sampled_correct = random.sample(all_correct, sample_size)
        sampled_sqls = [q['sql'] for q in sampled_correct]

        logger.info(f"Testing on {len(sampled_sqls)} correct queries")

        # Test each cluster
        validated_clusters = []

        for cluster in clusters:
            false_positives, total = self.clusterer.test_cluster_on_correct_queries(
                cluster, sampled_sqls
            )

            # Calculate pass rate
            pass_rate = (total - false_positives) / total if total > 0 else 0

            # Check against minimum pass rate (95% per methodology)
            if pass_rate >= min_pass_rate:
                validated_clusters.append(cluster)
                logger.info(
                    f"Cluster {cluster.cluster_id} passed testing "
                    f"(pass rate: {pass_rate*100:.2f}%, {total - false_positives}/{total})"
                )
            else:
                logger.warning(
                    f"Cluster {cluster.cluster_id} failed testing "
                    f"(pass rate: {pass_rate*100:.2f}% < {min_pass_rate*100}%, "
                    f"{false_positives} false positives out of {total})"
                )

        logger.info(f"Validated {len(validated_clusters)}/{len(clusters)} clusters")
        return validated_clusters

    def save_results(self, clusters: List):
        """
        Save validated rules and clusters to disk.

        Args:
            clusters: List of validated RuleClusters
        """
        logger.info("Saving results")

        # Save clusters
        clusters_file = os.path.join(RULE_STORAGE_PATH, "clusters.json")
        clusters_data = [cluster.to_dict() for cluster in clusters]

        with open(clusters_file, 'w') as f:
            json.dump(clusters_data, f, indent=2)

        logger.info(f"Saved {len(clusters)} clusters to {clusters_file}")

        # Save all rules
        all_rules = []
        for cluster in clusters:
            all_rules.extend(cluster.rules)

        rules_file = os.path.join(RULE_STORAGE_PATH, "rules.json")
        rules_data = [rule.to_dict() for rule in all_rules]

        with open(rules_file, 'w') as f:
            json.dump(rules_data, f, indent=2)

        logger.info(f"Saved {len(all_rules)} rules to {rules_file}")

        # Save triplets
        triplets_file = os.path.join(RULE_STORAGE_PATH, "triplets.json")
        triplets_data = [t.to_dict() for t in self.triplets]

        with open(triplets_file, 'w') as f:
            json.dump(triplets_data, f, indent=2)

        logger.info(f"Saved {len(self.triplets)} triplets to {triplets_file}")

        # Save transformations (if transformation was enabled)
        if self.enable_transformation and self.metrics['transformations']:
            transformations_file = os.path.join(RULE_STORAGE_PATH, "transformations.json")

            with open(transformations_file, 'w') as f:
                json.dump(self.metrics['transformations'], f, indent=2)

            logger.info(f"Saved {len(self.metrics['transformations'])} transformations to {transformations_file}")

        # Save metrics
        if self.enable_transformation:
            metrics_file = os.path.join(RULE_STORAGE_PATH, "metrics.json")

            # Calculate summary metrics
            metrics_summary = {
                'total_queries': self.metrics['total_queries'],
                'transformation_attempted': self.metrics['transformation_attempted'],
                'transformation_successful': self.metrics['transformation_successful'],
                'transformation_failed': self.metrics['transformation_failed'],
                'success_rate': (
                    self.metrics['transformation_successful'] / self.metrics['transformation_attempted'] * 100
                    if self.metrics['transformation_attempted'] > 0 else 0
                ),
                'execution_validated': self.metrics['execution_validated'],
                'execution_failed': self.metrics['execution_failed']
            }

            with open(metrics_file, 'w') as f:
                json.dump(metrics_summary, f, indent=2)

            logger.info(f"Saved transformation metrics to {metrics_file}")

    def run_pipeline(
        self,
        eval_file: str,
        predictions_file: str,
        questions_file: str,
        max_triplets: int = None
    ):
        """
        Run the complete error correction pipeline.

        Args:
            eval_file: Path to evaluation results
            predictions_file: Path to predictions
            questions_file: Path to questions JSON
            max_triplets: Maximum triplets to process (None for all)
        """
        logger.info("="*50)
        logger.info("Starting Error Correction Pipeline")
        logger.info("="*50)

        # Step 1-2: Parse and store queries
        logger.info("\n[Step 1-2] Parsing evaluation results and storing queries")
        correct_queries, incorrect_queries = self.parse_evaluation_results(
            eval_file, predictions_file, questions_file
        )
        self.store_queries_in_vector_db(correct_queries, incorrect_queries)

        # Step 3-5: Generate triplets
        logger.info("\n[Step 3-5] Generating explanations and rules")
        triplets = self.generate_triplets(incorrect_queries, max_triplets)

        if len(triplets) < MIN_TRIPLETS_FOR_CLUSTERING:
            logger.warning(
                f"Not enough triplets ({len(triplets)}) for clustering. "
                f"Pipeline stopped."
            )
            return

        # Step 6: Hierarchical clustering
        logger.info("\n[Step 6] Performing hierarchical clustering")
        clusters = self.perform_clustering()

        if not clusters:
            logger.warning("No valid clusters created. Pipeline stopped.")
            return

        # Step 6.1: Condense rules in each cluster (per methodology)
        logger.info("\n[Step 6.1] Condensing rules in clusters using LLM")
        for cluster in clusters:
            if cluster.size() > 1:
                combined_rule = self.clusterer.combine_rules_in_cluster(cluster, self.rule_generator)
                if combined_rule:
                    logger.info(f"Cluster {cluster.cluster_id}: condensed {cluster.size()} rules")
                else:
                    logger.warning(f"Cluster {cluster.cluster_id}: condensation failed")
            else:
                logger.debug(f"Cluster {cluster.cluster_id}: only 1 rule, no condensation needed")

        # Step 6.5: Apply transformations (if enabled)
        transformations = {}
        if self.enable_transformation:
            logger.info("\n[Step 6.5] Applying transformations to incorrect queries")
            transformations = self.apply_transformations(incorrect_queries, clusters)

            # Validate transformations (if enabled)
            if self.enable_execution_validation:
                logger.info("\n[Step 6.6] Validating transformations through execution")
                transformations = self.validate_transformations(transformations)
        else:
            logger.info("\n[Step 6.5] Transformation disabled, skipping")

        # Step 7: Test on correct queries
        logger.info("\n[Step 7] Testing rules on correct queries")
        validated_clusters = self.test_rules_on_correct_queries(clusters)

        # Save results
        logger.info("\n[Step 8] Saving results")
        self.save_results(validated_clusters)

        logger.info("\n"+"="*50)
        logger.info("Pipeline completed successfully!")
        logger.info(f"Generated {len(self.triplets)} triplets")
        logger.info(f"Created {len(clusters)} clusters")
        logger.info(f"Validated {len(validated_clusters)} clusters")

        # Log transformation metrics
        if self.enable_transformation:
            logger.info(f"Transformations attempted: {self.metrics['transformation_attempted']}")
            logger.info(f"Transformations successful: {self.metrics['transformation_successful']}")
            logger.info(f"Transformations failed: {self.metrics['transformation_failed']}")
            success_rate = (
                self.metrics['transformation_successful'] / self.metrics['transformation_attempted'] * 100
                if self.metrics['transformation_attempted'] > 0 else 0
            )
            logger.info(f"Transformation success rate: {success_rate:.2f}%")

        logger.info("="*50)


def main():
    parser = argparse.ArgumentParser(description="Error Correction Pipeline for DAIL-SQL")
    parser.add_argument("--eval_results", type=str, required=True,
                        help="Path to evaluation results file")
    parser.add_argument("--predictions_file", type=str, required=True,
                        help="Path to predictions file")
    parser.add_argument("--questions_file", type=str, required=True,
                        help="Path to questions JSON file")
    parser.add_argument("--model", type=str, default="gpt-4",
                        help="LLM model to use")
    parser.add_argument("--openai_api_key", type=str, required=True,
                        help="OpenAI API key")
    parser.add_argument("--openai_api_base", type=str, default="",
                        help="OpenAI API base URL")
    parser.add_argument("--temperature", type=float, default=0.3,
                        help="Temperature for LLM generation")
    parser.add_argument("--max_triplets", type=int, default=None,
                        help="Maximum number of triplets to generate (for testing)")
    parser.add_argument("--enable_transformation", action="store_true",
                        help="Enable query transformation (default: False)")
    parser.add_argument("--enable_execution_validation", action="store_true",
                        help="Enable execution-based validation (default: False)")
    parser.add_argument("--transformation_confidence_threshold", type=float,
                        default=TRANSFORMATION_CONFIDENCE_THRESHOLD,
                        help="Minimum confidence threshold for applying transformations")

    args = parser.parse_args()

    # Initialize and run pipeline
    pipeline = ErrorCorrectionPipeline(
        model=args.model,
        openai_api_key=args.openai_api_key,
        openai_api_base=args.openai_api_base,
        temperature=args.temperature,
        enable_transformation=args.enable_transformation,
        enable_execution_validation=args.enable_execution_validation,
        transformation_confidence_threshold=args.transformation_confidence_threshold
    )

    pipeline.run_pipeline(
        eval_file=args.eval_results,
        predictions_file=args.predictions_file,
        questions_file=args.questions_file,
        max_triplets=args.max_triplets
    )


if __name__ == "__main__":
    main()
