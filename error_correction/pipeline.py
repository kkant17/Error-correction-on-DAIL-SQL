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
from datetime import datetime
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
from error_correction.rule_engine import Rule, RuleTriplet, RuleGenerator, RuleApplicator, CommittedRulesStore, RuleValidationService
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
        use_code_generation: bool = False,
        allow_code_execution: bool = False,
        use_regex_rules: bool = True,
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

        # Initialize LLM (skipped for Ollama/local-only setups)
        placeholder_keys = {"not_needed_for_ollama", "ollama", "local"}
        if openai_api_key and openai_api_key not in placeholder_keys:
            init_chatgpt(openai_api_key, "", model, openai_api_base)

        # Initialize components
        self.embedder = SQLEmbedder()
        self.correct_db = CorrectQueriesDB()
        self.incorrect_db = IncorrectQueriesDB()
        self.rule_generator = RuleGenerator(
            model=model,
            temperature=temperature,
            use_code_generation=use_code_generation,
            allow_code_execution=allow_code_execution,
            use_regex_rules=use_regex_rules
        )
        self.rule_applicator = RuleApplicator()
        self.validation_service = RuleValidationService()
        self.clusterer = HierarchicalRuleClusterer(
            embedder=self.embedder,
            rule_generator=self.rule_generator
        )
        self.committed_rules = CommittedRulesStore()

        # Transformation settings
        self.use_regex_rules = use_regex_rules
        self.use_code_generation = use_code_generation
        self.allow_code_execution = allow_code_execution
        self.enable_transformation = enable_transformation
        self.enable_execution_validation = enable_execution_validation
        self.transformation_confidence_threshold = transformation_confidence_threshold

        # Storage for triplets and rules
        self.triplets: List[RuleTriplet] = []
        self.validated_rules: List[Rule] = []

        # Streaming state tracking for incremental processing
        self.pending_triplets: List[RuleTriplet] = []  # Triplets awaiting clustering
        self.completed_triplets: List[RuleTriplet] = []  # Triplets that passed clustering
        self.processed_query_ids: set = set()  # Track which queries have been processed
        self.clustering_cycles: int = 0  # Number of clustering cycles completed
        self.all_validated_clusters: List = []  # Accumulate clusters across cycles

        # Metrics tracking
        self.metrics = {
            'total_queries': 0,
            'transformation_attempted': 0,
            'transformation_successful': 0,
            'transformation_failed': 0,
            'execution_validated': 0,
            'execution_failed': 0,
            'transformations': [],  # Detailed transformation results
            'clustering_cycles': 0,
            'triplets_per_cycle': [],
            'rules_per_cycle': [],
            'validation_stats': {
                'total_validated': 0,
                'exact_matches': 0,
                'execution_matches': 0,
                'partial_match_computed': 0,
                'partial_match_scores': {
                    'select_f1_sum': 0.0,
                    'where_f1_sum': 0.0,
                    'group_f1_sum': 0.0,
                    'order_f1_sum': 0.0,
                    'overall_f1_sum': 0.0
                }
            }
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

    def populate_correct_queries_from_json(
        self,
        correct_predictions_file: str = "results/correct_predictions.json",
        clear_existing: bool = False
    ) -> int:
        """
        Populate the correct queries vector database from a JSON file of correct predictions.
        
        This file is generated by running evaluation with --save_correct flag:
        python eval/evaluation.py --gold ... --pred ... --save_correct results/correct_predictions.json
        
        Args:
            correct_predictions_file: Path to JSON file with correct predictions
            clear_existing: Whether to clear existing correct queries first
            
        Returns:
            Number of correct predictions added
        """
        logger.info(f"Populating correct queries from {correct_predictions_file}")
        
        # Optionally clear existing
        if clear_existing:
            logger.info("Clearing existing correct queries")
            self.correct_db.clear()
        
        # Check if already populated
        existing_count = self.correct_db.size()
        if existing_count > 0 and not clear_existing:
            logger.info(f"Correct queries DB already has {existing_count} queries")
            return existing_count
        
        if not os.path.exists(correct_predictions_file):
            logger.warning(f"Correct predictions file not found: {correct_predictions_file}")
            logger.warning("Run evaluation with --save_correct to generate this file:")
            logger.warning("  python eval/evaluation.py --gold ... --pred ... --save_correct results/correct_predictions.json")
            return 0
        
        # Load correct predictions
        with open(correct_predictions_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        predictions = data.get('predictions', [])
        if not predictions:
            logger.warning("No predictions found in file")
            return 0
        
        logger.info(f"Loaded {len(predictions)} correct predictions from file")
        
        # Convert to format expected by vector DB
        correct_queries = []
        for pred in predictions:
            correct_queries.append({
                'sql': pred.get('predicted_sql', ''),
                'db_id': pred.get('db_id', ''),
                'question': pred.get('question', ''),
                'gold_sql': pred.get('gold_sql', '')
            })
        
        # Embed and store
        logger.info(f"Embedding {len(correct_queries)} correct predictions...")
        sqls = [q['sql'] for q in correct_queries]
        embeddings = self.embedder.embed_batch(sqls)
        
        metadatas = [
            {'db_id': q['db_id'], 'question': q['question'], 'gold_sql': q['gold_sql']}
            for q in correct_queries
        ]
        
        self.correct_db.add_batch(sqls, embeddings, metadatas)
        
        logger.info(f"Added {len(correct_queries)} correct predictions to vector DB")
        return len(correct_queries)

    def populate_incorrect_queries_from_json(
        self,
        incorrect_predictions_file: str = "results/incorrect_predictions.json",
        clear_existing: bool = False
    ) -> int:
        """
        Populate the incorrect queries vector database from a JSON file of incorrect predictions.
        
        This file is generated by running evaluation with --save_incorrect flag:
        python eval/evaluation.py --gold ... --pred ... --save_incorrect results/incorrect_predictions.json
        
        Args:
            incorrect_predictions_file: Path to JSON file with incorrect predictions
            clear_existing: Whether to clear existing incorrect queries first
            
        Returns:
            Number of incorrect predictions added
        """
        logger.info(f"Populating incorrect queries from {incorrect_predictions_file}")
        
        # Optionally clear existing
        if clear_existing:
            logger.info("Clearing existing incorrect queries")
            self.incorrect_db.clear()
        
        # Check if already populated
        existing_count = self.incorrect_db.size()
        if existing_count > 0 and not clear_existing:
            logger.info(f"Incorrect queries DB already has {existing_count} queries")
            return existing_count
        
        if not os.path.exists(incorrect_predictions_file):
            logger.warning(f"Incorrect predictions file not found: {incorrect_predictions_file}")
            logger.warning("Run evaluation with --save_incorrect to generate this file:")
            logger.warning("  python eval/evaluation.py --gold ... --pred ... --save_incorrect results/incorrect_predictions.json")
            return 0
        
        # Load incorrect predictions
        with open(incorrect_predictions_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        predictions = data.get('predictions', [])
        if not predictions:
            logger.warning("No predictions found in file")
            return 0
        
        logger.info(f"Loaded {len(predictions)} incorrect predictions from file")
        
        # Convert to format expected by vector DB
        incorrect_queries = []
        for pred in predictions:
            incorrect_queries.append({
                'sql': pred.get('predicted_sql', ''),
                'db_id': pred.get('db_id', ''),
                'question': pred.get('question', ''),
                'gold_sql': pred.get('gold_sql', '')
            })
        
        # Embed and store
        logger.info(f"Embedding {len(incorrect_queries)} incorrect predictions...")
        sqls = [q['sql'] for q in incorrect_queries]
        embeddings = self.embedder.embed_batch(sqls)
        
        metadatas = [
            {'db_id': q['db_id'], 'question': q['question'], 'gold_sql': q['gold_sql']}
            for q in incorrect_queries
        ]
        
        self.incorrect_db.add_batch(sqls, embeddings, metadatas)
        
        logger.info(f"Added {len(incorrect_queries)} incorrect predictions to vector DB")
        return len(incorrect_queries)

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

    def get_next_unprocessed_query(self) -> Dict:
        """
        Get the next unprocessed incorrect query from the database.
        
        Returns:
            Query dict or None if no unprocessed queries remain
        """
        all_queries = self.incorrect_db.get_all_queries()
        
        for query in all_queries:
            # Generate a unique ID for this query
            query_id = hash(query.get('sql', ''))
            if query_id not in self.processed_query_ids:
                return {
                    'predicted_sql': query.get('sql', ''),
                    'gold_sql': query.get('metadata', {}).get('gold_sql', ''),
                    'db_id': query.get('metadata', {}).get('db_id', ''),
                    'question': query.get('metadata', {}).get('question', ''),
                    'query_id': query_id
                }
        
        return None

    def get_unprocessed_query_count(self) -> int:
        """
        Get the count of unprocessed incorrect queries.
        
        Returns:
            Number of queries not yet processed
        """
        all_queries = self.incorrect_db.get_all_queries()
        count = 0
        for query in all_queries:
            query_id = hash(query.get('sql', ''))
            if query_id not in self.processed_query_ids:
                count += 1
        return count

    def generate_triplet_for_query(self, query_data: Dict) -> RuleTriplet:
        """
        Generate a triplet for a single query.
        
        This is the core single-query processing logic extracted from generate_triplets().
        It applies existing rules, generates new rules if needed, validates them,
        and either returns a valid triplet or deletes the query from incorrect_db.
        
        Args:
            query_data: Dict containing predicted_sql, gold_sql, db_id, question, query_id
            
        Returns:
            RuleTriplet if successful, None if query was deleted/failed
        """
        query_id = query_data.get('query_id', hash(query_data.get('predicted_sql', '')))
        predicted_sql_short = query_data.get('predicted_sql', '')[:80] + '...' if len(query_data.get('predicted_sql', '')) > 80 else query_data.get('predicted_sql', '')
        gold_sql_short = query_data.get('gold_sql', '')[:80] + '...' if len(query_data.get('gold_sql', '')) > 80 else query_data.get('gold_sql', '')
        
        logger.info(f"--- Processing Query ---")
        logger.info(f"  DB: {query_data.get('db_id', 'unknown')}")
        logger.info(f"  Question: {query_data.get('question', 'N/A')[:100]}")
        logger.info(f"  Predicted: {predicted_sql_short}")
        logger.info(f"  Gold: {gold_sql_short}")
        
        try:
            # Mark as processed
            self.processed_query_ids.add(query_id)
            
            # Step 1: Check for existing committed rule
            logger.info(f"  [Step 1] Checking committed rules store ({self.committed_rules.size()} rules)...")
            existing_rule = self.committed_rules.find_matching_rule(query_data['predicted_sql'])
            
            if existing_rule:
                logger.info(f"  [Step 1] [OK] Found matching committed rule: {existing_rule.rule_id}")
                logger.info(f"    Pattern: {existing_rule.pattern[:60]}...")
                # Apply existing rule
                transformed = existing_rule.apply(query_data['predicted_sql'])

                if transformed and transformed != query_data['predicted_sql']:
                    logger.info(f"  [Step 1] Rule transformed query successfully")
                    logger.info(f"    Transformed: {transformed[:80]}...")
                    # Validate transformation using RuleValidationService
                    db_id = query_data.get('db_id') or query_data.get('metadata', {}).get('db_id')
                    validation_result = self.validation_service.validate_transformation(
                        original_query=query_data['predicted_sql'],
                        transformed_query=transformed,
                        expected_query=query_data['gold_sql'],
                        db_id=db_id
                    )

                    if validation_result.passed:
                        logger.info(f"  [Step 1] [OK] Existing rule PASSED validation ({validation_result.method})")
                        # Track validation accuracy
                        self._track_validation_result(validation_result)
                        # Remove from incorrect queries DB since it's now fixed
                        if self.incorrect_db.delete_query(query_data['predicted_sql']):
                            logger.info("  [Step 1] [OK] Query FIXED by existing rule - deleted from incorrect_db")
                        # Query is fixed by existing rule, no new triplet needed
                        return None
                    else:
                        logger.info(f"  [Step 1] [FAIL] Existing rule FAILED validation ({validation_result.method})")
                else:
                    logger.info(f"  [Step 1] [FAIL] Existing rule did not transform query")
            else:
                logger.info(f"  [Step 1] No matching committed rule found")
            
            # Step 2: Generate explanation (only if we reach here - existing rule didn't fix it)
            logger.info(f"  [Step 2] Generating explanation via LLM...")
            explanation = self.rule_generator.generate_explanation(
                predicted_sql=query_data['predicted_sql'],
                gold_sql=query_data['gold_sql'],
                db_id=query_data['db_id'],
                question=query_data['question']
            )
            logger.info(f"  [Step 2] [OK] Explanation generated ({len(explanation)} chars)")
            
            # Step 3: Generate rules
            logger.info(f"  [Step 3] Generating rules via LLM...")
            rules = self.rule_generator.generate_rules(
                incorrect_query=query_data['predicted_sql'],
                correct_query=query_data['gold_sql'],
                explanation=explanation
            )

            if not rules:
                logger.warning(f"  [Step 3] [FAIL] No rules generated by LLM")
                # Delete from incorrect_db - can't fix this query
                self.incorrect_db.delete_query(query_data['predicted_sql'])
                logger.info(f"  [DELETED] Query removed from incorrect_db (no rules generated)")
                return None
            
            logger.info(f"  [Step 3] [OK] Generated {len(rules)} rule(s)")

            # Step 4: Verify rules
            logger.info(f"  [Step 4] Verifying rules with RuleApplicator...")
            valid_rules = []
            for i, rule in enumerate(rules):
                logger.info(f"    Rule {i+1}: pattern='{rule.pattern[:50]}...' replacement='{rule.replacement[:30]}...'")
                if self.rule_applicator.verify_rule(query_data['predicted_sql'], rule):
                    valid_rules.append(rule)
                    logger.info(f"    Rule {i+1}: [OK] VERIFIED")
                else:
                    logger.warning(f"    Rule {i+1}: [FAIL] FAILED verification")

            if not valid_rules:
                logger.warning(f"  [Step 4] [FAIL] No rules passed verification")
                # Delete from incorrect_db - rules don't work on this query
                self.incorrect_db.delete_query(query_data['predicted_sql'])
                logger.info(f"  [DELETED] Query removed from incorrect_db (no valid rules)")
                return None
            
            logger.info(f"  [Step 4] [OK] {len(valid_rules)}/{len(rules)} rules verified")

            # Step 5: Create triplet
            triplet = RuleTriplet(
                incorrect_query=query_data['predicted_sql'],
                correct_query=query_data['gold_sql'],
                explanation=explanation,
                rules=valid_rules,
                db_id=query_data['db_id'],
                question=query_data['question']
            )

            logger.info(f"  [Step 5] [OK] Created RuleTriplet with {len(valid_rules)} rule(s)")
            logger.info(f"--- Query Processing Complete ---\n")
            return triplet

        except Exception as e:
            logger.error(f"  [ERROR] Exception during query processing: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def generate_triplets(
        self,
        incorrect_queries: List[Dict],
        max_triplets: int = None
    ) -> List[RuleTriplet]:
        """
        Generate triplets <query, explanation, rules> for incorrect queries.
        
        NOTE: This is the batch method. For streaming workflow, use generate_triplet_for_query()
        with process_next_query() instead.

        Args:
            incorrect_queries: List of incorrect query dicts
            max_triplets: Maximum number of triplets to generate (None for all)

        Returns:
            List of RuleTriplets
        """
        logger.info("Generating triplets (batch mode)")

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

                # Check for existing committed rule before generating new one
                existing_rule = self.committed_rules.find_matching_rule(query_data['predicted_sql'])

                if existing_rule:
                    logger.info(f"Found existing committed rule: {existing_rule.rule_id}")
                    # Apply existing rule
                    transformed = existing_rule.apply(query_data['predicted_sql'])

                    if transformed and transformed != query_data['predicted_sql']:
                        # Validate transformation using RuleValidationService
                        # This checks exact match, execution match, and partial match
                        db_id = query_data.get('db_id') or query_data.get('metadata', {}).get('db_id')
                        validation_result = self.validation_service.validate_transformation(
                            original_query=query_data['predicted_sql'],
                            transformed_query=transformed,
                            expected_query=query_data['gold_sql'],
                            db_id=db_id
                        )

                        if validation_result.passed:
                            logger.info(f"Existing rule validated via {validation_result.method}")
                            # Track validation accuracy
                            self._track_validation_result(validation_result)
                            rules = [existing_rule]

                            # Remove from incorrect queries DB since it's now fixed
                            if self.incorrect_db.delete_query(query_data['predicted_sql']):
                                logger.info("Removed fixed query from incorrect queries DB")
                        else:
                            logger.info(f"Existing rule failed validation ({validation_result.method}), generating new rule")
                            # Generate new rules
                            rules = self.rule_generator.generate_rules(
                                incorrect_query=query_data['predicted_sql'],
                                correct_query=query_data['gold_sql'],
                                explanation=explanation
                            )
                    else:
                        logger.info("Existing rule did not transform query, generating new rule")
                        # Generate new rules
                        rules = self.rule_generator.generate_rules(
                            incorrect_query=query_data['predicted_sql'],
                            correct_query=query_data['gold_sql'],
                            explanation=explanation
                        )
                else:
                    # No existing rule, generate new rules
                    rules = self.rule_generator.generate_rules(
                        incorrect_query=query_data['predicted_sql'],
                        correct_query=query_data['gold_sql'],
                        explanation=explanation
                    )

                if not rules:
                    logger.warning(f"No rules generated for query {i}")
                    # Delete from incorrect_db - can't fix this query
                    self.incorrect_db.delete_query(query_data['predicted_sql'])
                    logger.info(f"Deleted unfixable query from incorrect_db (no rules)")
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
                    # Delete from incorrect_db - rules don't work on this query
                    self.incorrect_db.delete_query(query_data['predicted_sql'])
                    logger.info(f"Deleted unfixable query from incorrect_db (no valid rules)")
                    continue

                # NOTE: Rules are NOT added to committed_rules here!
                # They will only be committed after passing the full pipeline:
                # clustering → correct query testing → validation
                # See test_rules_on_correct_queries() for where rules are committed

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

    def process_next_query(self) -> bool:
        """
        Process the next unprocessed query from incorrect_db.
        
        This is the main orchestrator for streaming workflow:
        1. Gets next unprocessed query
        2. Generates triplet (or deletes query if it fails)
        3. Adds successful triplet to pending_triplets
        4. Triggers clustering when threshold is reached
        
        Returns:
            True if a query was processed, False if no queries remain
        """
        # Get next unprocessed query
        query_data = self.get_next_unprocessed_query()
        
        if query_data is None:
            logger.info("No more unprocessed queries")
            return False
        
        remaining = self.get_unprocessed_query_count()
        logger.info(f"\n{'='*60}")
        logger.info(f"QUERY {len(self.processed_query_ids)+1} ({remaining} remaining in incorrect_db)")
        logger.info(f"{'='*60}")
        
        # Generate triplet for this query
        triplet = self.generate_triplet_for_query(query_data)
        
        if triplet:
            # Add to pending triplets (awaiting clustering)
            self.pending_triplets.append(triplet)
            logger.info(f"[PENDING] Added triplet to pending queue ({len(self.pending_triplets)}/{MIN_TRIPLETS_FOR_CLUSTERING} for clustering)")
            
            # Check if we should trigger clustering
            if len(self.pending_triplets) >= MIN_TRIPLETS_FOR_CLUSTERING:
                logger.info(f"\n*** CLUSTERING THRESHOLD REACHED ({len(self.pending_triplets)} >= {MIN_TRIPLETS_FOR_CLUSTERING}) ***")
                self.run_clustering_cycle()
        else:
            logger.info("[SKIPPED] Query processed but no triplet created (fixed by existing rule or failed)")
        
        return True

    def run_clustering_cycle(self):
        """
        Run a clustering cycle on pending_triplets.
        
        This method:
        1. Moves pending_triplets to self.triplets for clustering
        2. Calls perform_clustering()
        3. Calls test_rules_on_correct_queries()
        4. Moves surviving triplets to completed_triplets
        5. Clears pending_triplets for next cycle
        6. Updates metrics
        """
        if len(self.pending_triplets) < MIN_TRIPLETS_FOR_CLUSTERING:
            logger.warning(f"Not enough pending triplets ({len(self.pending_triplets)}) for clustering cycle")
            return
        
        self.clustering_cycles += 1
        logger.info(f"\n{'#'*70}")
        logger.info(f"# CLUSTERING CYCLE {self.clustering_cycles}")
        logger.info(f"{'#'*70}")
        logger.info(f"Input: {len(self.pending_triplets)} pending triplets")
        
        # Move pending triplets to self.triplets for clustering
        self.triplets = self.pending_triplets.copy()
        self.pending_triplets = []
        
        # Step 1: Perform clustering
        logger.info(f"\n[Cluster Step 1] Performing hierarchical clustering...")
        clusters, final_rules = self.perform_clustering()
        
        if not clusters:
            logger.warning(f"[Cluster Step 1] ✗ No valid clusters created - triplets will be lost")
            self.triplets = []
            return
        
        logger.info(f"[Cluster Step 1] [OK] Created {len(clusters)} clusters with {len(final_rules)} rules")
        for i, cluster in enumerate(clusters):
            logger.info(f"  Cluster {i+1}: {len(cluster.triplets)} triplets, combined_rule={cluster.combined_rule is not None}")
        
        # Step 2: Test rules on correct queries (this also commits rules and deletes queries)
        logger.info(f"\n[Cluster Step 2] Testing merged rules on correct queries ({self.correct_db.size()} correct queries)...")
        validated_clusters = self.test_rules_on_correct_queries(clusters)
        
        # Track metrics
        self.metrics['clustering_cycles'] = self.clustering_cycles
        self.metrics['triplets_per_cycle'].append(len(self.triplets))
        self.metrics['rules_per_cycle'].append(len(final_rules))
        
        # Accumulate validated clusters across cycles
        self.all_validated_clusters.extend(validated_clusters)
        
        # Move surviving triplets to completed
        for cluster in validated_clusters:
            self.completed_triplets.extend(cluster.triplets)
        
        logger.info(f"\n{'#'*70}")
        logger.info(f"# CYCLE {self.clustering_cycles} SUMMARY")
        logger.info(f"{'#'*70}")
        logger.info(f"  Clusters validated: {len(validated_clusters)}/{len(clusters)}")
        logger.info(f"  Rules committed (total): {self.committed_rules.size()}")
        logger.info(f"  Completed triplets (total): {len(self.completed_triplets)}")
        logger.info(f"  Remaining incorrect queries: {self.incorrect_db.size()}")
        logger.info(f"{'#'*70}\n")
        
        # Clear triplets for next cycle
        self.triplets = []

    def run_streaming_pipeline(self, max_queries: int = None) -> Dict:
        """
        Run the complete streaming pipeline.
        
        This is the main entry point for the incremental workflow:
        1. Process incorrect queries one-by-one
        2. Trigger clustering every MIN_TRIPLETS_FOR_CLUSTERING triplets
        3. Run final clustering if any pending triplets remain
        4. Save results and return summary
        
        Args:
            max_queries: Maximum queries to process (None for all)
            
        Returns:
            Summary dict with metrics
        """
        logger.info("\n" + "="*80)
        logger.info("STARTING STREAMING ERROR CORRECTION PIPELINE")
        logger.info("="*80)
        logger.info(f"Min triplets for clustering: {MIN_TRIPLETS_FOR_CLUSTERING}")
        
        queries_processed = 0
        
        # Main processing loop
        while True:
            # Check max_queries limit
            if max_queries and queries_processed >= max_queries:
                logger.info(f"Reached max_queries limit ({max_queries})")
                break
            
            # Process next query
            had_query = self.process_next_query()
            
            if not had_query:
                break
            
            queries_processed += 1
        
        logger.info(f"\nProcessed {queries_processed} queries")
        
        # Run final clustering cycle if any pending triplets remain
        if len(self.pending_triplets) > 0:
            logger.info(f"\nRunning final clustering cycle on {len(self.pending_triplets)} remaining triplets")
            
            # For final pass, cluster even if below threshold
            if len(self.pending_triplets) >= 2:  # Need at least 2 for clustering
                # Temporarily lower threshold for final pass
                self.triplets = self.pending_triplets.copy()
                self.pending_triplets = []
                
                # Perform clustering with whatever we have
                clusters, final_rules = self.perform_clustering()
                
                if clusters:
                    validated_clusters = self.test_rules_on_correct_queries(clusters)
                    self.all_validated_clusters.extend(validated_clusters)
                    
                    for cluster in validated_clusters:
                        self.completed_triplets.extend(cluster.triplets)
                    
                    logger.info(f"Final cycle validated {len(validated_clusters)} clusters")
                
                self.triplets = []
            else:
                logger.info(f"Only {len(self.pending_triplets)} triplet(s) remaining, skipping final clustering")
                # Move remaining to completed anyway (they just won't have validated rules)
                self.completed_triplets.extend(self.pending_triplets)
                self.pending_triplets = []
        
        # Generate summary
        summary = {
            'queries_processed': queries_processed,
            'clustering_cycles': self.clustering_cycles,
            'completed_triplets': len(self.completed_triplets),
            'validated_clusters': len(self.all_validated_clusters),
            'committed_rules': self.committed_rules.size(),
            'remaining_incorrect': self.incorrect_db.size(),
            'metrics': self.metrics
        }
        
        logger.info("\n" + "="*80)
        logger.info("STREAMING PIPELINE COMPLETE")
        logger.info("="*80)
        logger.info(f"Queries processed: {queries_processed}")
        logger.info(f"Clustering cycles: {self.clustering_cycles}")
        logger.info(f"Completed triplets: {len(self.completed_triplets)}")
        logger.info(f"Validated clusters: {len(self.all_validated_clusters)}")
        logger.info(f"Committed rules: {self.committed_rules.size()}")
        logger.info(f"Remaining incorrect queries: {self.incorrect_db.size()}")
        
        return summary

    def perform_clustering(self) -> Tuple[List, List]:
        """
        Perform three-level hierarchical clustering on collected triplets.

        Returns:
            Tuple of (clusters, final_rules) where:
            - clusters: List of validated RuleClusters
            - final_rules: List of merged rules (one per cluster) for validation
        """
        if len(self.triplets) < MIN_TRIPLETS_FOR_CLUSTERING:
            logger.warning(
                f"Not enough triplets ({len(self.triplets)}) for clustering "
                f"(minimum: {MIN_TRIPLETS_FOR_CLUSTERING})"
            )
            return [], []

        logger.info(f"Performing three-level clustering on {len(self.triplets)} triplets")

        # Get embeddings for incorrect queries (optional, new approach uses text embeddings)
        incorrect_queries = [t.incorrect_query for t in self.triplets]
        embeddings = self.embedder.embed_batch(incorrect_queries)

        # Cluster using three-level approach
        clusters = self.clusterer.cluster_triplets(self.triplets, embeddings)

        # Filter clusters based on combine threshold (with SQL validation)
        valid_clusters = self.clusterer.filter_clusters(
            clusters, 
            len(self.triplets),
            validation_service=self.validation_service
        )

        # Merge rules within each cluster (with validation on representative triplets)
        # Track clusters where merge validation fails - their queries will be deleted
        merge_failed_triplets = []
        clusters_to_remove = []
        
        for cluster in valid_clusters:
            if cluster.size() > 1:
                combined_rule = self.clusterer.combine_rules_in_cluster(
                    cluster, 
                    self.rule_generator,
                    self.validation_service
                )
                if combined_rule:
                    cluster.combined_rule = combined_rule
                    logger.debug(f"Cluster {cluster.cluster_id}: merged {cluster.size()} rules")
                else:
                    # Merge validation FAILED - mark for deletion
                    merge_failed_triplets.extend(cluster.triplets)
                    clusters_to_remove.append(cluster)
                    logger.warning(f"Cluster {cluster.cluster_id} merge failed - marking queries for deletion")
        
        # Remove failed clusters from valid_clusters
        for cluster in clusters_to_remove:
            valid_clusters.remove(cluster)
        
        # Delete queries from merge-failed clusters
        if merge_failed_triplets:
            for triplet in merge_failed_triplets:
                self.incorrect_db.delete_query(triplet.incorrect_query)
                if triplet in self.triplets:
                    self.triplets.remove(triplet)
            logger.info(f"Deleted {len(merge_failed_triplets)} queries (merged rule validation failed)")

        # Extract final rules for validation
        final_rules = self.clusterer.get_final_rules(valid_clusters)

        logger.info(f"Created {len(valid_clusters)} clusters with {len(final_rules)} final rules")
        return valid_clusters, final_rules

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

        # Build a rule lookup from clusters (use combined_rule when available)
        all_rules = []
        for cluster in clusters:
            if cluster.combined_rule:
                # Use the merged rule (better generalization)
                all_rules.append(cluster.combined_rule)
            else:
                # Fall back to individual rules
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
            logger.warning("No correct queries available for testing - REJECTING ALL CLUSTERS")
            logger.warning("Please populate the correct queries DB first using populate_correct_queries_from_json()")
            return []  # Return empty - don't accept untested rules!

        # Sample correct queries
        sample_size = max(1, int(len(all_correct) * sample_ratio))
        sampled_correct = random.sample(all_correct, sample_size)
        sampled_sqls = [q['sql'] for q in sampled_correct]

        logger.info(f"Testing on {len(sampled_sqls)} correct queries")

        # Test each cluster
        validated_clusters = []

        for cluster in clusters:
            # Get the rule for this cluster
            rule = cluster.rule
            passed_count = 0
            false_positives = 0
            total = 0

            # Test rule on each sampled correct query
            for query in sampled_correct:
                total += 1
                query_sql = query['sql']
                gold_sql = query.get('gold_sql', query_sql)  # For correct queries, predicted == gold
                db_id = query.get('db_id', '')

                # Apply rule transformation
                transformed = rule.apply(query_sql)

                # Validate transformation using RuleValidationService
                validation_result = self.validation_service.validate_transformation(
                    original_query=query_sql,
                    transformed_query=transformed,
                    expected_query=gold_sql,
                    db_id=db_id
                )

                # Track validation result for accuracy stats
                if validation_result.passed:
                    passed_count += 1
                    self._track_validation_result(validation_result)
                else:
                    false_positives += 1

            # Calculate pass rate
            pass_rate = passed_count / total if total > 0 else 0

            # Check against minimum pass rate (95% per methodology)
            if pass_rate >= min_pass_rate:
                validated_clusters.append(cluster)
                logger.info(
                    f"Cluster {cluster.cluster_id} passed testing "
                    f"(pass rate: {pass_rate*100:.2f}%, {passed_count}/{total})"
                )
            else:
                logger.warning(
                    f"Cluster {cluster.cluster_id} failed testing "
                    f"(pass rate: {pass_rate*100:.2f}% < {min_pass_rate*100}%, "
                    f"{false_positives} false positives out of {total})"
                )
                # FAILED correct query testing - delete these queries
                for triplet in cluster.triplets:
                    self.incorrect_db.delete_query(triplet.incorrect_query)
                    if triplet in self.triplets:
                        self.triplets.remove(triplet)
                logger.info(f"Deleted {len(cluster.triplets)} queries (failed correct query testing)")

        logger.info(f"Validated {len(validated_clusters)}/{len(clusters)} clusters")

        # Extract final rules from validated clusters and store in CommittedRulesStore
        if validated_clusters:
            final_rules = self.clusterer.get_final_rules(validated_clusters)
            for rule in final_rules:
                self.committed_rules.add_rule(rule)
            logger.info(f"Stored {len(final_rules)} validated rules in CommittedRulesStore")
            
            # Delete successful queries from incorrect_db (they're now solved)
            solved_count = 0
            for cluster in validated_clusters:
                for triplet in cluster.triplets:
                    if self.incorrect_db.delete_query(triplet.incorrect_query):
                        solved_count += 1
                    if triplet in self.triplets:
                        self.triplets.remove(triplet)
            logger.info(f"Deleted {solved_count} solved queries from incorrect_db")

        return validated_clusters

    def save_results(self, clusters: List):
        """
        Save validated rules and clusters to disk.
        
        Handles both streaming mode (uses completed_triplets) and batch mode (uses self.triplets).

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

        # Save committed rules from database (validated rules that passed full pipeline)
        committed_rules = self.committed_rules.get_all_rules()
        rules_file = os.path.join(RULE_STORAGE_PATH, "rules.json")
        rules_data = [rule.to_dict() for rule in committed_rules]

        with open(rules_file, 'w') as f:
            json.dump(rules_data, f, indent=2)

        logger.info(f"Saved {len(committed_rules)} committed rules to {rules_file}")

        # Save triplets - use completed_triplets if available (streaming mode), otherwise self.triplets (batch mode)
        triplets_to_save = self.completed_triplets if self.completed_triplets else self.triplets
        triplets_file = os.path.join(RULE_STORAGE_PATH, "triplets.json")
        triplets_data = [t.to_dict() for t in triplets_to_save]

        with open(triplets_file, 'w') as f:
            json.dump(triplets_data, f, indent=2)

        logger.info(f"Saved {len(triplets_to_save)} triplets to {triplets_file}")

        # Save transformations (if transformation was enabled)
        if self.enable_transformation and self.metrics['transformations']:
            transformations_file = os.path.join(RULE_STORAGE_PATH, "transformations.json")

            with open(transformations_file, 'w') as f:
                json.dump(self.metrics['transformations'], f, indent=2)

            logger.info(f"Saved {len(self.metrics['transformations'])} transformations to {transformations_file}")

        # Save metrics (for both batch and streaming modes)
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
            'execution_failed': self.metrics['execution_failed'],
            # Streaming-specific metrics
            'clustering_cycles': self.metrics.get('clustering_cycles', 0),
            'triplets_per_cycle': self.metrics.get('triplets_per_cycle', []),
            'rules_per_cycle': self.metrics.get('rules_per_cycle', []),
            'completed_triplets': len(self.completed_triplets),
            'committed_rules': self.committed_rules.size()
        }

        with open(metrics_file, 'w') as f:
            json.dump(metrics_summary, f, indent=2)

        logger.info(f"Saved metrics to {metrics_file}")

        # Save accuracy statistics
        validation_stats = self.metrics['validation_stats']
        total = validation_stats['total_validated']

        accuracy_stats = {
            'total_validated': total,
            'exact_matches': validation_stats['exact_matches'],
            'execution_matches': validation_stats['execution_matches'],
            'exact_match_accuracy': round(validation_stats['exact_matches'] / total * 100, 2) if total > 0 else 0,
            'execution_match_accuracy': round(validation_stats['execution_matches'] / total * 100, 2) if total > 0 else 0,
            'overall_accuracy': round((validation_stats['exact_matches'] + validation_stats['execution_matches']) / total * 100, 2) if total > 0 else 0,
            'partial_match_computed': validation_stats['partial_match_computed']
        }

        # Add partial match F1 scores if computed
        if validation_stats['partial_match_computed'] > 0:
            count = validation_stats['partial_match_computed']
            scores = validation_stats['partial_match_scores']
            accuracy_stats['partial_match_scores'] = {
                'avg_select_f1': round(scores['select_f1_sum'] / count, 3),
                'avg_where_f1': round(scores['where_f1_sum'] / count, 3),
                'avg_group_f1': round(scores['group_f1_sum'] / count, 3),
                'avg_order_f1': round(scores['order_f1_sum'] / count, 3),
                'avg_overall_f1': round(scores['overall_f1_sum'] / count, 3)
            }

        accuracy_file = os.path.join(RULE_STORAGE_PATH, "accuracy_stats.json")
        with open(accuracy_file, 'w') as f:
            json.dump(accuracy_stats, f, indent=2)

        logger.info(f"Saved accuracy statistics to {accuracy_file}")

        # Generate consolidated evaluation report
        model_name = getattr(self.rule_generator, 'model', 'unknown_model')
        eval_file = self.save_consolidated_eval_report(model_name)
        logger.info(f"Saved consolidated evaluation report to {eval_file}")

    def _sanitize_model_name(self, model_name: str) -> str:
        """
        Convert model name to valid filename.

        Examples:
            'codellama:7b' -> 'codellama_7b'
            'llama3.1:8b' -> 'llama3_1_8b'
            'gpt-4' -> 'gpt_4'

        Args:
            model_name: Model identifier

        Returns:
            Sanitized model name safe for filenames
        """
        sanitized = model_name.replace(":", "_").replace(".", "_").replace("/", "_").replace("-", "_")
        return sanitized

    def save_consolidated_eval_report(self, model_name: str) -> str:
        """
        Generate comprehensive human-readable evaluation report from all result files.

        Merges clusters.json, rules.json, metrics.json, accuracy_stats.json, triplets.json,
        and transformations.json into a single text file for easy review and comparison.

        Args:
            model_name: Model identifier (e.g., "codellama:7b" or "llama3.1:8b")

        Returns:
            Path to generated eval file
        """
        logger.info(f"Generating consolidated evaluation report for model: {model_name}")

        # Sanitize model name for filename
        sanitized_model = self._sanitize_model_name(model_name)

        # Output filename
        results_dir = "results"
        os.makedirs(results_dir, exist_ok=True)
        output_file = os.path.join(results_dir, f"eval_error_correction_{sanitized_model}.txt")

        # Read all result JSON files
        clusters_file = os.path.join(RULE_STORAGE_PATH, "clusters.json")
        rules_file = os.path.join(RULE_STORAGE_PATH, "rules.json")
        metrics_file = os.path.join(RULE_STORAGE_PATH, "metrics.json")
        accuracy_file = os.path.join(RULE_STORAGE_PATH, "accuracy_stats.json")
        triplets_file = os.path.join(RULE_STORAGE_PATH, "triplets.json")
        transformations_file = os.path.join(RULE_STORAGE_PATH, "transformations.json")

        # Load JSON data
        clusters = []
        rules = []
        metrics = {}
        accuracy_stats = {}
        triplets = []
        transformations = []

        if os.path.exists(clusters_file):
            with open(clusters_file, 'r') as f:
                clusters = json.load(f)

        if os.path.exists(rules_file):
            with open(rules_file, 'r') as f:
                rules = json.load(f)

        if os.path.exists(metrics_file):
            with open(metrics_file, 'r') as f:
                metrics = json.load(f)

        if os.path.exists(accuracy_file):
            with open(accuracy_file, 'r') as f:
                accuracy_stats = json.load(f)

        if os.path.exists(triplets_file):
            with open(triplets_file, 'r') as f:
                triplets = json.load(f)

        if os.path.exists(transformations_file):
            with open(transformations_file, 'r') as f:
                transformations = json.load(f)

        # Generate report
        with open(output_file, 'w') as f:
            # Header
            f.write("=" * 80 + "\n")
            f.write("ERROR CORRECTION PIPELINE EVALUATION REPORT\n")
            f.write(f"Model: {model_name}\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

            # Section 1: Pipeline Metrics
            f.write("SECTION 1: PIPELINE METRICS\n")
            f.write("-" * 40 + "\n")
            f.write(f"Total Queries: {metrics.get('total_queries', 0)}\n")
            f.write(f"Clustering Cycles: {metrics.get('clustering_cycles', 0)}\n")
            f.write(f"Completed Triplets: {metrics.get('completed_triplets', 0)}\n")
            f.write(f"Committed Rules: {metrics.get('committed_rules', 0)}\n\n")

            f.write("Transformation Stats:\n")
            f.write(f"  - Attempted: {metrics.get('transformation_attempted', 0)}\n")
            f.write(f"  - Successful: {metrics.get('transformation_successful', 0)}\n")
            f.write(f"  - Failed: {metrics.get('transformation_failed', 0)}\n")
            success_rate = metrics.get('success_rate', 0)
            f.write(f"  - Success Rate: {success_rate:.2f}%\n\n")

            f.write("Execution Validation:\n")
            f.write(f"  - Validated: {metrics.get('execution_validated', 0)}\n")
            f.write(f"  - Failed: {metrics.get('execution_failed', 0)}\n\n\n")

            # Section 2: Accuracy Statistics
            f.write("SECTION 2: ACCURACY STATISTICS\n")
            f.write("-" * 40 + "\n")
            f.write(f"Total Validated: {accuracy_stats.get('total_validated', 0)}\n\n")

            f.write("Match Accuracy:\n")
            f.write(f"  - Exact Matches: {accuracy_stats.get('exact_matches', 0)} ")
            f.write(f"({accuracy_stats.get('exact_match_accuracy', 0):.2f}%)\n")
            f.write(f"  - Execution Matches: {accuracy_stats.get('execution_matches', 0)} ")
            f.write(f"({accuracy_stats.get('execution_match_accuracy', 0):.2f}%)\n")
            f.write(f"  - Overall Accuracy: {accuracy_stats.get('overall_accuracy', 0):.2f}%\n\n")

            if 'partial_match_scores' in accuracy_stats:
                pm_scores = accuracy_stats['partial_match_scores']
                f.write("Partial Match Scores (F1):\n")
                f.write(f"  - SELECT: {pm_scores.get('avg_select_f1', 0):.3f}\n")
                f.write(f"  - WHERE: {pm_scores.get('avg_where_f1', 0):.3f}\n")
                f.write(f"  - GROUP BY: {pm_scores.get('avg_group_f1', 0):.3f}\n")
                f.write(f"  - ORDER BY: {pm_scores.get('avg_order_f1', 0):.3f}\n")
                f.write(f"  - Overall: {pm_scores.get('avg_overall_f1', 0):.3f}\n")
            f.write("\n\n")

            # Section 3: Committed Rules
            f.write("SECTION 3: COMMITTED RULES\n")
            f.write("-" * 40 + "\n")
            f.write(f"Total Rules: {len(rules)}\n\n")

            for idx, rule in enumerate(rules, 1):
                f.write(f"Rule {idx}:\n")
                f.write(f"  ID: {rule.get('rule_id', 'N/A')}\n")
                f.write(f"  Error Type: {rule.get('error_type', 'N/A')}\n")
                pattern = rule.get('pattern', 'N/A')
                if len(pattern) > 100:
                    pattern = pattern[:100] + "..."
                f.write(f"  Pattern: {pattern}\n")
                replacement = rule.get('replacement', 'N/A')
                if len(replacement) > 100:
                    replacement = replacement[:100] + "..."
                f.write(f"  Replacement: {replacement}\n")
                if 'confidence_score' in rule:
                    f.write(f"  Confidence: {rule.get('confidence_score', 'N/A')}\n")
                f.write("\n")
            f.write("\n")

            # Section 4: Clustering Summary
            f.write("SECTION 4: CLUSTERING SUMMARY\n")
            f.write("-" * 40 + "\n")
            f.write(f"Total Clusters: {len(clusters)}\n\n")

            for idx, cluster in enumerate(clusters, 1):
                f.write(f"Cluster {idx}:\n")
                f.write(f"  ID: {cluster.get('cluster_id', 'N/A')}\n")
                f.write(f"  Size: {cluster.get('size', 0)}\n")
                if cluster.get('combined_rule'):
                    f.write(f"  Combined Rule: {cluster['combined_rule'].get('rule_id', 'N/A')}\n")
                else:
                    f.write("  Combined Rule: None\n")

                # Count error types in cluster
                error_types = {}
                for rule in cluster.get('rules', []):
                    et = rule.get('error_type', 'UNKNOWN')
                    error_types[et] = error_types.get(et, 0) + 1
                if error_types:
                    f.write(f"  Error Types: {dict(error_types)}\n")
                f.write("\n")
            f.write("\n")

            # Section 5: Triplet Samples
            f.write("SECTION 5: TRIPLET SAMPLES (First 10)\n")
            f.write("-" * 40 + "\n")

            for idx, triplet in enumerate(triplets[:10], 1):
                f.write(f"Triplet {idx}:\n")
                f.write(f"  ID: {triplet.get('triplet_id', 'N/A')}\n")
                f.write(f"  DB: {triplet.get('db_id', 'N/A')}\n")
                question = triplet.get('question', 'N/A')
                if len(question) > 80:
                    question = question[:80] + "..."
                f.write(f"  Question: {question}\n")

                incorrect_q = triplet.get('incorrect_query', 'N/A')
                if len(incorrect_q) > 80:
                    incorrect_q = incorrect_q[:80] + "..."
                f.write(f"  Incorrect Query: {incorrect_q}\n")

                correct_q = triplet.get('correct_query', 'N/A')
                if len(correct_q) > 80:
                    correct_q = correct_q[:80] + "..."
                f.write(f"  Correct Query: {correct_q}\n")

                explanation = triplet.get('explanation', 'N/A')
                if len(explanation) > 80:
                    explanation = explanation[:80] + "..."
                f.write(f"  Explanation: {explanation}\n")

                f.write(f"  Rules Generated: {len(triplet.get('rules', []))}\n")
                f.write("\n")
            f.write("\n")

            # Section 6: Transformation Details
            if transformations:
                f.write("SECTION 6: TRANSFORMATION DETAILS\n")
                f.write("-" * 40 + "\n")
                f.write(f"Total Transformations: {len(transformations)}\n\n")
                f.write("\n")

            # Section 7: Error Type Breakdown
            f.write("SECTION 7: ERROR TYPE BREAKDOWN\n")
            f.write("-" * 40 + "\n")

            error_type_counts = {}
            for rule in rules:
                et = rule.get('error_type', 'UNKNOWN')
                error_type_counts[et] = error_type_counts.get(et, 0) + 1

            for error_type in sorted(error_type_counts.keys()):
                f.write(f"{error_type}: {error_type_counts[error_type]} rules\n")
            f.write("\n\n")

            # Footer
            f.write("=" * 80 + "\n")
            f.write("END OF REPORT\n")
            f.write("=" * 80 + "\n")

        logger.info(f"Saved consolidated evaluation report to {output_file}")
        return output_file

    def run_pipeline(
        self,
        eval_file: str = None,
        predictions_file: str = None,
        questions_file: str = None,
        max_triplets: int = None,
        streaming: bool = True
    ):
        """
        Run the complete error correction pipeline.
        
        Supports two modes:
        - streaming=True (default): Process queries one-by-one, trigger clustering every 20 triplets
        - streaming=False: Batch mode - generate all triplets then cluster once

        Args:
            eval_file: Path to evaluation results (optional if DBs pre-populated)
            predictions_file: Path to predictions (optional if DBs pre-populated)
            questions_file: Path to questions JSON (optional if DBs pre-populated)
            max_triplets: Maximum triplets to process (None for all)
            streaming: Use streaming workflow (default True)
        """
        logger.info("="*50)
        logger.info("Starting Error Correction Pipeline")
        logger.info(f"Mode: {'Streaming' if streaming else 'Batch'}")
        logger.info("="*50)

        # Step 1-2: Parse and store queries (if files provided)
        if eval_file and predictions_file and questions_file:
            logger.info("\n[Step 1-2] Parsing evaluation results and storing queries")
            correct_queries, incorrect_queries = self.parse_evaluation_results(
                eval_file, predictions_file, questions_file
            )
            self.store_queries_in_vector_db(correct_queries, incorrect_queries)
        else:
            logger.info("\n[Step 1-2] Using pre-populated vector databases")
            incorrect_queries = None  # Will use incorrect_db directly

        if streaming:
            # STREAMING MODE: Process queries incrementally
            logger.info("\n[Step 3-7] Running streaming pipeline")
            summary = self.run_streaming_pipeline(max_queries=max_triplets)
            
            # Save results using accumulated clusters
            logger.info("\n[Step 8] Saving results")
            self.save_results(self.all_validated_clusters)
            
            logger.info("\n"+"="*50)
            logger.info("Pipeline completed successfully! (Streaming Mode)")
            logger.info(f"Queries processed: {summary['queries_processed']}")
            logger.info(f"Clustering cycles: {summary['clustering_cycles']}")
            logger.info(f"Completed triplets: {summary['completed_triplets']}")
            logger.info(f"Validated clusters: {summary['validated_clusters']}")
            logger.info(f"Committed rules: {summary['committed_rules']}")
            logger.info(f"Remaining incorrect queries: {summary['remaining_incorrect']}")
            logger.info("="*50)
            
            return summary
        
        else:
            # BATCH MODE: Original workflow
            logger.info("\n[Step 3-5] Generating explanations and rules (batch mode)")
            
            if incorrect_queries is None:
                # Get from DB if not from parsing
                incorrect_queries = [
                    {
                        'predicted_sql': q.get('sql', ''),
                        'gold_sql': q.get('metadata', {}).get('gold_sql', ''),
                        'db_id': q.get('metadata', {}).get('db_id', ''),
                        'question': q.get('metadata', {}).get('question', '')
                    }
                    for q in self.incorrect_db.get_all_queries()
                ]
            
            triplets = self.generate_triplets(incorrect_queries, max_triplets)

            if len(triplets) < MIN_TRIPLETS_FOR_CLUSTERING:
                logger.warning(
                    f"Not enough triplets ({len(triplets)}) for clustering. "
                    f"Pipeline stopped."
                )
                return

            # Step 6: Hierarchical clustering
            logger.info("\n[Step 6] Performing hierarchical clustering")
            clusters, final_rules = self.perform_clustering()

            if not clusters:
                logger.warning("No valid clusters created. Pipeline stopped.")
                return

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
            logger.info("Pipeline completed successfully! (Batch Mode)")
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

    def _track_validation_result(self, validation_result) -> None:
        """
        Track validation accuracy statistics.

        Args:
            validation_result: RuleValidationResult from validation
        """
        stats = self.metrics['validation_stats']

        # Only track successful validations
        if not validation_result.passed:
            return

        stats['total_validated'] += 1

        # Track by validation method
        if validation_result.method == "exact_match":
            stats['exact_matches'] += 1
        elif validation_result.method == "execution_match":
            stats['execution_matches'] += 1

        # Track partial match scores if available
        if validation_result.partial_match_scores:
            partial_scores = validation_result.partial_match_scores
            stats['partial_match_computed'] += 1

            # Accumulate component F1 scores
            if 'select' in partial_scores and 'f1' in partial_scores['select']:
                stats['partial_match_scores']['select_f1_sum'] += partial_scores['select']['f1']
            if 'where' in partial_scores and 'f1' in partial_scores['where']:
                stats['partial_match_scores']['where_f1_sum'] += partial_scores['where']['f1']
            if 'group' in partial_scores and 'f1' in partial_scores['group']:
                stats['partial_match_scores']['group_f1_sum'] += partial_scores['group']['f1']
            if 'order' in partial_scores and 'f1' in partial_scores['order']:
                stats['partial_match_scores']['order_f1_sum'] += partial_scores['order']['f1']

            # Calculate overall F1 as average of components
            component_count = 0
            total_f1 = 0.0
            for component in ['select', 'where', 'group', 'order']:
                if component in partial_scores and 'f1' in partial_scores[component]:
                    total_f1 += partial_scores[component]['f1']
                    component_count += 1
            if component_count > 0:
                stats['partial_match_scores']['overall_f1_sum'] += total_f1 / component_count

    def _normalize_sql(self, sql: str) -> str:
        """
        Normalize SQL for comparison.

        Args:
            sql: SQL query string

        Returns:
            Normalized SQL string
        """
        return ' '.join(sql.lower().split()).strip().rstrip(';')

    def _check_exact_match(self, transformed: str, correct: str) -> bool:
        """
        Check if transformed query exactly matches correct query (normalized).

        Args:
            transformed: Transformed SQL query
            correct: Correct SQL query

        Returns:
            True if exact match, False otherwise
        """
        return self._normalize_sql(transformed) == self._normalize_sql(correct)

    def _check_execution_match(self, transformed: str, correct: str, db_path: str) -> bool:
        """
        Execute both queries and compare results.

        Args:
            transformed: Transformed SQL query
            correct: Correct SQL query
            db_path: Path to database file

        Returns:
            True if execution results match, False otherwise
        """
        if not db_path or not os.path.exists(db_path):
            return False

        try:
            from eval.exec_eval import eval_exec_match
            result = eval_exec_match(
                db=db_path,
                p_str=transformed,
                g_str=correct,
                plug_value=False,
                keep_distinct=True,
                progress_bar_for_each_datapoint=False
            )
            return result == 1
        except Exception as e:
            logger.warning(f"Execution match failed: {e}")
            return False

    def _check_partial_match(self, transformed: str, correct: str) -> Dict:
        """
        Component-level SQL comparison (SELECT, WHERE, GROUP BY, etc.).

        Args:
            transformed: Transformed SQL query
            correct: Correct SQL query

        Returns:
            Dictionary with component scores
        """
        try:
            from eval.evaluation import Evaluator
            from eval.process_sql import get_sql

            evaluator = Evaluator()
            db = None  # Parser doesn't need actual database

            p_parsed = get_sql(db, transformed)
            g_parsed = get_sql(db, correct)

            if not p_parsed or not g_parsed:
                return {}

            return evaluator.eval_partial_match(p_parsed, g_parsed)
        except Exception as e:
            logger.warning(f"Partial match failed: {e}")
            return {}


def main():
    """
    CLI for running the error correction pipeline.
    
    Usage:
        python -m error_correction.pipeline \
            --correct results/correct_predictions.json \
            --incorrect results/incorrect_predictions.json \
            --model codellama:7b \
            --max_queries 60
    """
    parser = argparse.ArgumentParser(
        description="Error Correction Pipeline for DAIL-SQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with JSON files from evaluation
  python -m error_correction.pipeline \\
      --correct results/correct_predictions.json \\
      --incorrect results/incorrect_predictions.json \\
      --model codellama:7b

  # Limit queries and use batch mode
  python -m error_correction.pipeline \\
      --correct results/correct_predictions.json \\
      --incorrect results/incorrect_predictions.json \\
      --max_queries 20 --batch
        """
    )
    
    # Input files (JSON from evaluation)
    parser.add_argument("--correct", type=str, default=None,
                        help="Path to correct_predictions.json")
    parser.add_argument("--incorrect", type=str, default=None,
                        help="Path to incorrect_predictions.json")
    parser.add_argument("--skip_json", action="store_true",
                        help="Skip JSON loading, use pre-populated vector DBs")
    
    # Model settings
    parser.add_argument("--model", type=str, default="codellama:7b",
                        help="LLM model to use (default: codellama:7b)")
    parser.add_argument("--temperature", type=float, default=0.3,
                        help="Temperature for LLM generation (default: 0.3)")
    
    # Processing options
    parser.add_argument("--max_queries", type=int, default=None,
                        help="Maximum queries to process (default: all)")
    parser.add_argument("--batch", action="store_true",
                        help="Use batch mode instead of streaming (default: streaming)")
    
    # Database paths (for execution matching)
    parser.add_argument("--db_dir", type=str, default="dataset/spider/database",
                        help="Path to Spider database directory")
    
    # Output
    parser.add_argument("--output_dir", type=str, default="error_correction/rules",
                        help="Output directory for results")

    args = parser.parse_args()
    
    # Validate input files (unless skipping JSON)
    if not args.skip_json:
        if not args.correct or not os.path.exists(args.correct):
            logger.error(f"Correct predictions file not found: {args.correct}")
            logger.error("Use --skip_json if vector DBs are already populated")
            sys.exit(1)
        if not args.incorrect or not os.path.exists(args.incorrect):
            logger.error(f"Incorrect predictions file not found: {args.incorrect}")
            logger.error("Use --skip_json if vector DBs are already populated")
            sys.exit(1)
    
    # Set Ollama URL for local models
    if args.model in ["codellama:7b", "deepseek-coder:6.7b", "llama3.1:8b"]:
        os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
        logger.info(f"Using Ollama model: {args.model}")
    
    # Initialize pipeline
    logger.info("Initializing Error Correction Pipeline...")
    pipeline = ErrorCorrectionPipeline(
        model=args.model,
        openai_api_key="not_needed_for_ollama",
        temperature=args.temperature
    )
    
    # Build database paths for execution matching
    if os.path.exists(args.db_dir):
        db_paths = {}
        for db_name in os.listdir(args.db_dir):
            db_file = os.path.join(args.db_dir, db_name, f"{db_name}.sqlite")
            if os.path.exists(db_file):
                db_paths[db_name] = db_file
        pipeline.validation_service = RuleValidationService(db_paths=db_paths)
        logger.info(f"Loaded {len(db_paths)} database paths for execution matching")
    
    # Populate vector databases from JSON (unless skipping)
    if args.skip_json:
        logger.info("Skipping JSON loading - using pre-populated vector DBs")
        incorrect_count = pipeline.incorrect_db.size()
        correct_count = pipeline.correct_db.size()
        logger.info(f"Found {incorrect_count} incorrect, {correct_count} correct queries in DBs")
    else:
        logger.info("Populating vector databases...")
        incorrect_count = pipeline.populate_incorrect_queries_from_json(args.incorrect, clear_existing=True)
        correct_count = pipeline.populate_correct_queries_from_json(args.correct, clear_existing=True)
        logger.info(f"Loaded {incorrect_count} incorrect, {correct_count} correct queries")
    
    if incorrect_count == 0:
        logger.error("No incorrect predictions to process!")
        sys.exit(1)
    
    # Run pipeline
    streaming = not args.batch
    logger.info(f"Running pipeline in {'streaming' if streaming else 'batch'} mode...")
    
    summary = pipeline.run_pipeline(streaming=streaming, max_triplets=args.max_queries)
    
    # Print summary
    if summary:
        print("\n" + "="*60)
        print("PIPELINE COMPLETE")
        print("="*60)
        print(f"Queries processed: {summary.get('queries_processed', 'N/A')}")
        print(f"Clustering cycles: {summary.get('clustering_cycles', 'N/A')}")
        print(f"Completed triplets: {summary.get('completed_triplets', 'N/A')}")
        print(f"Committed rules: {summary.get('committed_rules', 'N/A')}")


if __name__ == "__main__":
    main()
