"""
Unified Rule Validation Service

Applies regex rules and validates using:
1. Exact match (fast) - normalized string comparison
2. Execution match (fallback) - SQLite query execution
3. Partial match (diagnostic) - component-level SQL comparison

Used throughout the pipeline for consistent validation:
- Initial rule generation
- Cluster rule merging
- Final validation before committing rules
"""
import re
import logging
from typing import List, Optional, Tuple, Union, Dict, Any
from dataclasses import dataclass, field

from error_correction.rule_engine.rule_schema import Rule, RegexRule

logger = logging.getLogger(__name__)


@dataclass
class RuleValidationResult:
    """Result of rule validation."""
    passed: bool
    original_query: str
    transformed_query: str
    expected_query: str
    method: str  # "exact_match", "execution_match", "failed", "no_change"
    error: Optional[str] = None
    partial_match_scores: Optional[Dict[str, Dict[str, float]]] = None


class RuleValidationService:
    """
    Unified service for applying and validating regex rules.
    
    Supports:
    - Applying single or multiple rules consecutively
    - Two-tier validation: exact match → execution match
    - Validating on representative triplets from clusters
    """
    
    def __init__(self, db_paths: dict = None):
        """
        Initialize the validation service.
        
        Args:
            db_paths: Dict mapping db_id -> sqlite_path for execution validation
        """
        self.db_paths = db_paths or {}
        logger.info(f"RuleValidationService initialized with {len(self.db_paths)} db paths")
    
    def set_db_paths(self, db_paths: dict) -> None:
        """Update database paths for execution validation."""
        self.db_paths = db_paths or {}
    
    def add_db_path(self, db_id: str, db_path: str) -> None:
        """Add a single database path."""
        self.db_paths[db_id] = db_path
    
    # ==================== SQL Validation ====================

    def _is_valid_sql(self, sql: str) -> bool:
        """
        Validate SQL syntax before accepting transformation.

        Checks:
        1. Starts with SELECT (or valid SQL keyword)
        2. No duplicate clauses
        3. Correct clause ordering
        4. Basic structure validation

        Returns:
            True if valid, False otherwise
        """
        try:
            if not sql or not sql.strip():
                logger.warning("Empty SQL")
                return False

            sql_lower = sql.lower().strip()

            # Check 1: Must start with SELECT (or be a backreference-only pattern)
            valid_starts = ('select', '\\1', '\\2', '\\3')
            if not any(sql_lower.startswith(s) for s in valid_starts):
                logger.warning("SQL doesn't start with SELECT")
                return False

            # Check 2: No duplicate WHERE
            if sql_lower.count(' where ') > 1:
                logger.warning("Multiple WHERE clauses detected")
                return False

            # Check 3: No duplicate ORDER BY
            if sql_lower.count(' order by ') > 1:
                logger.warning("Multiple ORDER BY clauses detected")
                return False

            # Check 4: No duplicate GROUP BY
            if sql_lower.count(' group by ') > 1:
                logger.warning("Multiple GROUP BY clauses detected")
                return False

            # Check 5: WHERE before ORDER BY
            where_pos = sql_lower.find(' where ')
            order_pos = sql_lower.find(' order by ')
            if where_pos > 0 and order_pos > 0 and where_pos > order_pos:
                logger.warning("WHERE after ORDER BY detected")
                return False

            # Check 6: WHERE before GROUP BY
            group_pos = sql_lower.find(' group by ')
            if where_pos > 0 and group_pos > 0 and where_pos > group_pos:
                logger.warning("WHERE after GROUP BY detected")
                return False

            # Check 7: No obvious malformed SQL patterns
            # Check for common LLM mistakes
            if '$1' in sql or '$2' in sql:  # JavaScript backreference syntax
                logger.warning("JavaScript-style backreferences detected ($1, $2)")
                return False

            # Check for explanation text mixed in
            bad_patterns = ['note:', 'example:', 'incorrect:', 'the query', 'this query']
            if any(bp in sql_lower for bp in bad_patterns):
                logger.warning("Explanation text mixed into SQL")
                return False

            # Try to parse with eval module if available (optional)
            try:
                from eval.process_sql import get_sql
                # get_sql returns None if parsing fails
                parsed = get_sql(None, sql)
                if parsed:
                    logger.debug("SQL parsed successfully")
                # Don't fail if parsing fails - our string checks are sufficient
            except Exception:
                pass  # Parsing is optional - string checks are enough

            return True

        except Exception as e:
            logger.warning(f"SQL validation failed: {e}")
            return False

    # ==================== Rule Application ====================

    def apply_rule(self, query: str, rule: Union[Rule, RegexRule]) -> Tuple[str, bool]:
        """
        Apply a single rule to a query with syntax validation.

        Args:
            query: SQL query to transform
            rule: Rule with pattern and replacement

        Returns:
            Tuple of (transformed_query, was_changed)
        """
        if not rule.pattern:
            return query, False

        try:
            replacement = getattr(rule, 'replacement', '') or ''
            
            # Clean escaped characters from replacement before applying
            # LLM sometimes generates regex escapes that shouldn't be in SQL output
            replacement = replacement.replace('\\(', '(')
            replacement = replacement.replace('\\)', ')')
            replacement = replacement.replace('\\*', '*')
            replacement = replacement.replace('\\.', '.')
            replacement = replacement.replace('\\_', '_')
            replacement = replacement.replace('\\-', '-')
            replacement = replacement.replace('\\/', '/')
            # Clean double backslashes (but preserve single backslash for backreferences)
            replacement = re.sub(r'\\\\([^1-9])', r'\1', replacement)
            
            transformed = re.sub(
                rule.pattern,
                replacement,
                query,
                count=1,
                flags=re.IGNORECASE | re.MULTILINE | re.DOTALL
            )
            changed = transformed != query

            if changed:
                # CRITICAL: Validate before accepting transformation
                if not self._is_valid_sql(transformed):
                    logger.warning(f"Rule {rule.rule_id} produced invalid SQL, rejecting transformation")
                    return query, False  # Return original query

                logger.debug(f"Rule {rule.rule_id} transformed query (validated)")

            return transformed, changed
        except re.error as e:
            logger.warning(f"Regex error applying rule {rule.rule_id}: {e}")
            return query, False
    
    def apply_rules_chain(
        self, 
        query: str, 
        rules: List[Union[Rule, RegexRule]]
    ) -> Tuple[str, int, List[str]]:
        """
        Apply multiple rules consecutively to a query.
        
        Args:
            query: SQL query to transform
            rules: List of rules to apply in order
        
        Returns:
            Tuple of (final_query, num_rules_applied, list_of_applied_rule_ids)
        """
        current = query
        applied_count = 0
        applied_ids = []
        
        for rule in rules:
            transformed, was_changed = self.apply_rule(current, rule)
            if was_changed:
                current = transformed
                applied_count += 1
                applied_ids.append(rule.rule_id)
                logger.debug(f"Rule {rule.rule_id} applied, {applied_count} total")
        
        return current, applied_count, applied_ids
    
    # ==================== Matching Methods ====================
    
    def normalize_sql(self, sql: str) -> str:
        """
        Normalize SQL for comparison.
        
        Args:
            sql: SQL query string
        
        Returns:
            Normalized SQL string
        """
        # Remove extra whitespace
        sql = re.sub(r'\s+', ' ', sql.strip())
        # Convert to lowercase
        sql = sql.lower()
        # Remove trailing semicolon
        sql = sql.rstrip(';')
        # Normalize quotes
        sql = sql.replace('"', "'")
        return sql
    
    def check_exact_match(self, actual: str, expected: str) -> bool:
        """
        Check if queries match after normalization.
        
        Args:
            actual: The transformed query
            expected: The expected/gold query
        
        Returns:
            True if exact match after normalization
        """
        match = self.normalize_sql(actual) == self.normalize_sql(expected)
        if match:
            logger.debug("Exact match: PASSED")
        return match
    
    def check_execution_match(self, actual: str, expected: str, db_path: str) -> bool:
        """
        Check if queries produce same results on database.
        
        Args:
            actual: The transformed query
            expected: The expected/gold query
            db_path: Path to SQLite database
        
        Returns:
            True if queries produce same results
        """
        if not db_path:
            logger.debug("Execution match skipped: no db_path")
            return False
        
        try:
            from eval.exec_eval import eval_exec_match
            result = eval_exec_match(
                db=db_path,
                p_str=actual,
                g_str=expected,
                plug_value=False,
                keep_distinct=False,
                progress_bar_for_each_datapoint=False
            )
            match = result == 1
            if match:
                logger.debug("Execution match: PASSED")
            else:
                logger.debug("Execution match: FAILED")
            return match
        except Exception as e:
            logger.warning(f"Execution match error: {e}")
            return False

    def check_partial_match(
        self,
        predicted_sql: str,
        gold_sql: str
    ) -> Dict[str, Dict[str, float]]:
        """
        Compute partial match scores between predicted and gold SQL.

        Compares SQL component by component (SELECT, WHERE, GROUP BY, ORDER BY, etc.)
        and returns accuracy, recall, and F1 scores for each component.

        Args:
            predicted_sql: The transformed/predicted SQL query
            gold_sql: The expected/gold SQL query

        Returns:
            Dictionary with component-level scores:
            {
                'select': {'acc': float, 'rec': float, 'f1': float, 'label_total': int, 'pred_total': int},
                'where': {...},
                'group': {...},
                'order': {...},
                'and/or': {...},
                'IUEN': {...},
                'keywords': {...}
            }
            Returns empty dict {} if parsing fails.
        """
        try:
            from eval.evaluation import Evaluator
            from eval.process_sql import get_sql

            evaluator = Evaluator()

            # Parse both queries (db parameter not needed for parsing)
            db = None
            p_parsed = get_sql(db, predicted_sql)
            g_parsed = get_sql(db, gold_sql)

            if not p_parsed or not g_parsed:
                logger.warning("Failed to parse SQL for partial matching")
                return {}

            # Compute component-level scores
            scores = evaluator.eval_partial_match(p_parsed, g_parsed)
            logger.debug(f"Partial match computed: {len(scores)} components")
            return scores

        except Exception as e:
            logger.warning(f"Partial match computation failed: {e}")
            return {}

    # ==================== Validation Methods ====================
    
    def validate_transformation(
        self,
        original_query: str,
        transformed_query: str,
        expected_query: str,
        db_id: str = None
    ) -> RuleValidationResult:
        """
        Validate a transformation using exact match, then execution match.
        Also computes partial match scores for diagnostic purposes.

        Args:
            original_query: The input incorrect query
            transformed_query: Result after applying rule(s)
            expected_query: The correct/gold query
            db_id: Database ID for execution match

        Returns:
            ValidationResult with pass/fail, method used, and partial match scores
        """
        # Check if transformation changed anything
        if transformed_query == original_query:
            # Still compute partial match for diagnostics
            partial_scores = self.check_partial_match(transformed_query, expected_query)
            return RuleValidationResult(
                passed=False,
                original_query=original_query,
                transformed_query=transformed_query,
                expected_query=expected_query,
                method="no_change",
                error="Rule did not transform the query",
                partial_match_scores=partial_scores
            )

        # Step 1: Try exact match (fast)
        if self.check_exact_match(transformed_query, expected_query):
            # Compute partial match even on success for complete diagnostics
            partial_scores = self.check_partial_match(transformed_query, expected_query)
            return RuleValidationResult(
                passed=True,
                original_query=original_query,
                transformed_query=transformed_query,
                expected_query=expected_query,
                method="exact_match",
                partial_match_scores=partial_scores
            )

        # Step 2: Try execution match (slow) if db available
        db_path = self.db_paths.get(db_id) if db_id else None
        if db_path:
            if self.check_execution_match(transformed_query, expected_query, db_path):
                # Compute partial match even on success for complete diagnostics
                partial_scores = self.check_partial_match(transformed_query, expected_query)
                return RuleValidationResult(
                    passed=True,
                    original_query=original_query,
                    transformed_query=transformed_query,
                    expected_query=expected_query,
                    method="execution_match",
                    partial_match_scores=partial_scores
                )

        # Both failed - compute partial match to show which components are correct
        partial_scores = self.check_partial_match(transformed_query, expected_query)
        return RuleValidationResult(
            passed=False,
            original_query=original_query,
            transformed_query=transformed_query,
            expected_query=expected_query,
            method="failed",
            error="Both exact match and execution match failed",
            partial_match_scores=partial_scores
        )
    
    def validate_rule_on_query(
        self,
        rule: Union[Rule, RegexRule],
        incorrect_query: str,
        correct_query: str,
        db_id: str = None
    ) -> RuleValidationResult:
        """
        Apply rule to incorrect query and validate against correct query.
        
        Args:
            rule: Rule to apply
            incorrect_query: The incorrect SQL query
            correct_query: The expected correct SQL query
            db_id: Database ID for execution match
        
        Returns:
            ValidationResult
        """
        transformed, _ = self.apply_rule(incorrect_query, rule)
        return self.validate_transformation(
            original_query=incorrect_query,
            transformed_query=transformed,
            expected_query=correct_query,
            db_id=db_id
        )
    
    def validate_rule_on_triplet(
        self,
        rule: Union[Rule, RegexRule],
        triplet,  # RuleTriplet
    ) -> RuleValidationResult:
        """
        Apply rule to triplet's incorrect query and validate against correct query.
        
        Args:
            rule: Rule to apply
            triplet: RuleTriplet with incorrect_query, correct_query, db_id
        
        Returns:
            ValidationResult
        """
        return self.validate_rule_on_query(
            rule=rule,
            incorrect_query=triplet.incorrect_query,
            correct_query=triplet.correct_query,
            db_id=triplet.db_id
        )
    
    def validate_rule_on_representatives(
        self,
        rule: Union[Rule, RegexRule],
        triplets: List,  # List[RuleTriplet]
    ) -> Tuple[bool, List[RuleValidationResult]]:
        """
        Validate rule on all representative triplets.
        
        Args:
            rule: Rule to validate
            triplets: List of RuleTriplet objects
        
        Returns:
            Tuple of (all_passed, list_of_results)
        """
        results = []
        all_passed = True
        
        for triplet in triplets:
            result = self.validate_rule_on_triplet(rule, triplet)
            results.append(result)
            if not result.passed:
                all_passed = False
                logger.debug(
                    f"Validation failed for triplet {triplet.triplet_id}: "
                    f"{result.method} - {result.error}"
                )
        
        passed_count = sum(r.passed for r in results)
        logger.info(f"Representative validation: {passed_count}/{len(results)} passed")
        return all_passed, results
    
    def validate_rules_chain_on_query(
        self,
        rules: List[Union[Rule, RegexRule]],
        incorrect_query: str,
        correct_query: str,
        db_id: str = None
    ) -> RuleValidationResult:
        """
        Apply multiple rules consecutively and validate final result.
        
        Args:
            rules: List of rules to apply in order
            incorrect_query: The incorrect SQL query
            correct_query: The expected correct SQL query
            db_id: Database ID for execution match
        
        Returns:
            ValidationResult
        """
        transformed, num_applied, applied_ids = self.apply_rules_chain(incorrect_query, rules)
        
        result = self.validate_transformation(
            original_query=incorrect_query,
            transformed_query=transformed,
            expected_query=correct_query,
            db_id=db_id
        )
        
        # Add info about which rules were applied
        if applied_ids:
            logger.debug(f"Applied {num_applied} rules: {applied_ids}")
        
        return result

