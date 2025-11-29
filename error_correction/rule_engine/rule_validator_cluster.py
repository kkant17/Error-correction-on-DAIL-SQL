"""
Cluster Rule Validator - Two-tier validation for hierarchical clustering

This module extends RuleValidator with two-tier validation:
1. String match (fast) - Normalize and compare SQL strings
2. Execution match (accurate) - Execute queries on SQLite and compare results

Uses existing eval/exec_eval.py for execution-based validation.
"""
import re
import logging
import asyncio
from typing import Optional
from error_correction.rule_engine.rule_validator import RuleValidator
from error_correction.rule_engine.rule_schema import ValidationResult

logger = logging.getLogger(__name__)


class ClusterRuleValidator(RuleValidator):
    """
    Extended validator with two-tier validation for clustering.

    Inherits from RuleValidator and adds:
    - String-based validation (fast)
    - Execution-based validation (accurate, using eval code)
    - Two-tier validation strategy
    """

    def __init__(
        self,
        execution_timeout: int = 5,
        allow_execution: bool = True,
        use_execution_fallback: bool = True
    ):
        """
        Initialize the cluster validator.

        Args:
            execution_timeout: Timeout for code execution in seconds
            allow_execution: Whether to allow executing generated code
            use_execution_fallback: Whether to use execution match as fallback
        """
        super().__init__(execution_timeout, allow_execution)
        self.use_execution_fallback = use_execution_fallback
        logger.info(
            f"ClusterRuleValidator initialized: "
            f"execution_fallback={use_execution_fallback}"
        )

    def normalize_sql(self, sql: str) -> str:
        """
        Normalize SQL query for comparison.

        Args:
            sql: SQL query string

        Returns:
            Normalized SQL string
        """
        # Remove extra whitespace
        sql = re.sub(r'\s+', ' ', sql.strip())

        # Convert to lowercase for comparison
        sql = sql.lower()

        # Remove trailing semicolon
        sql = sql.rstrip(';')

        # Normalize quotes
        sql = sql.replace('"', "'")

        return sql

    def validate_with_string_match(
        self,
        actual_query: str,
        expected_query: str
    ) -> bool:
        """
        Validate using string comparison (fast path).

        Args:
            actual_query: The actual output query
            expected_query: The expected output query

        Returns:
            True if queries match after normalization, False otherwise
        """
        normalized_actual = self.normalize_sql(actual_query)
        normalized_expected = self.normalize_sql(expected_query)

        matches = normalized_actual == normalized_expected

        if matches:
            logger.debug("String match validation PASSED")
        else:
            logger.debug(
                f"String match validation FAILED\n"
                f"Expected: {normalized_expected}\n"
                f"Actual:   {normalized_actual}"
            )

        return matches

    def validate_with_execution_match(
        self,
        actual_query: str,
        expected_query: str,
        db_path: str
    ) -> bool:
        """
        Validate using execution comparison (slow but accurate).

        Uses eval_exec_match from eval/exec_eval.py to execute queries
        on SQLite database and compare results.

        Args:
            actual_query: The actual output query
            expected_query: The expected (gold) query
            db_path: Path to SQLite database

        Returns:
            True if queries produce same results, False otherwise
        """
        try:
            # Import eval function
            from eval.exec_eval import eval_exec_match

            # Call eval_exec_match
            # Returns 1 if match, 0 if no match
            result = eval_exec_match(
                db=db_path,
                p_str=actual_query,
                g_str=expected_query,
                plug_value=False,
                keep_distinct=False,
                progress_bar_for_each_datapoint=False
            )

            matches = result == 1

            if matches:
                logger.debug("Execution match validation PASSED")
            else:
                logger.debug("Execution match validation FAILED")

            return matches

        except Exception as e:
            logger.error(f"Error during execution match validation: {e}")
            return False

    def validate_transformation_two_tier(
        self,
        transform_code: str,
        test_query: str,
        expected_output: str,
        db_path: Optional[str] = None
    ) -> ValidationResult:
        """
        Validate transformation using two-tier approach.

        1. Execute transform_code on test_query
        2. Try string match first (fast)
        3. If fails and db_path provided, try execution match (slow)

        Args:
            transform_code: Python code to execute
            test_query: Input query to transform
            expected_output: Expected output query
            db_path: Optional database path for execution match

        Returns:
            ValidationResult with validation outcome and method used
        """
        logger.info("Starting two-tier validation")

        # Step 1: Execute transformation code
        base_result = self.validate_rule(
            transform_code=transform_code,
            test_query=test_query,
            expected_output=expected_output,
            normalize=False  # We'll do our own normalization
        )

        if not base_result.actual_output:
            # Transformation failed or returned empty
            logger.warning("Transformation execution failed")
            return base_result

        # Step 2: Try string match first (fast path)
        logger.debug("Attempting string match validation...")
        string_match = self.validate_with_string_match(
            base_result.actual_output,
            expected_output
        )

        if string_match:
            logger.info("Validation PASSED via string match (fast path)")
            return ValidationResult(
                passed=True,
                test_query=test_query,
                expected_output=expected_output,
                actual_output=base_result.actual_output,
                error_message="Passed: string match",
                execution_time_ms=base_result.execution_time_ms
            )

        # Step 3: Try execution match if available (slow path)
        if self.use_execution_fallback and db_path:
            logger.debug("String match failed, attempting execution match...")

            execution_match = self.validate_with_execution_match(
                base_result.actual_output,
                expected_output,
                db_path
            )

            if execution_match:
                logger.info("Validation PASSED via execution match (slow path)")
                return ValidationResult(
                    passed=True,
                    test_query=test_query,
                    expected_output=expected_output,
                    actual_output=base_result.actual_output,
                    error_message="Passed: execution match",
                    execution_time_ms=base_result.execution_time_ms
                )
            else:
                logger.info("Validation FAILED: execution match also failed")
                return ValidationResult(
                    passed=False,
                    test_query=test_query,
                    expected_output=expected_output,
                    actual_output=base_result.actual_output,
                    error_message="Failed: both string and execution match failed",
                    execution_time_ms=base_result.execution_time_ms
                )
        else:
            # No execution fallback available or disabled
            logger.info(
                f"Validation FAILED: string match failed, "
                f"execution fallback {'disabled' if not self.use_execution_fallback else 'unavailable (no db_path)'}"
            )
            return ValidationResult(
                passed=False,
                test_query=test_query,
                expected_output=expected_output,
                actual_output=base_result.actual_output,
                error_message="Failed: string match failed, execution fallback not available",
                execution_time_ms=base_result.execution_time_ms
            )

    def batch_validate_two_tier(
        self,
        transform_code: str,
        test_cases: list,
        db_path: Optional[str] = None
    ) -> list:
        """
        Validate multiple test cases using two-tier approach.

        Args:
            transform_code: Python transformation code
            test_cases: List of (test_query, expected_output) tuples
            db_path: Optional database path for execution match

        Returns:
            List of ValidationResults
        """
        results = []

        for test_query, expected_output in test_cases:
            result = self.validate_transformation_two_tier(
                transform_code=transform_code,
                test_query=test_query,
                expected_output=expected_output,
                db_path=db_path
            )
            results.append(result)

        return results

    def validate_on_representatives(
        self,
        transform_code: str,
        representatives: list,
        db_paths: dict = None
    ) -> tuple:
        """
        Validate transformation on multiple representative triplets.

        Args:
            transform_code: Python transformation code
            representatives: List of RuleTriplet objects
            db_paths: Optional dict mapping db_id to database path

        Returns:
            Tuple of (all_passed: bool, results: list)
        """
        results = []
        all_passed = True

        for triplet in representatives:
            # Get database path for this triplet
            db_path = None
            if db_paths and triplet.db_id in db_paths:
                db_path = db_paths[triplet.db_id]

            # Validate transformation
            result = self.validate_transformation_two_tier(
                transform_code=transform_code,
                test_query=triplet.incorrect_query,
                expected_output=triplet.correct_query,
                db_path=db_path
            )

            results.append(result)

            if not result.passed:
                all_passed = False
                logger.warning(
                    f"Validation failed for triplet {triplet.triplet_id}: "
                    f"{result.error_message}"
                )

        logger.info(
            f"Representative validation: {sum(r.passed for r in results)}/{len(results)} passed"
        )

        return all_passed, results
