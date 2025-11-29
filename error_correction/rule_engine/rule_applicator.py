"""
Rule Applicator for SQL Error Correction
Applies rules using regex pattern matching and transformations
"""
import re
import logging
from typing import List, Optional, Tuple
import signal
from contextlib import contextmanager

from error_correction.rule_engine.rule_schema import Rule
from error_correction.config import RULE_APPLICATION_TIMEOUT

logger = logging.getLogger(__name__)


class TimeoutException(Exception):
    """Exception raised when rule application times out."""
    pass


@contextmanager
def time_limit(seconds):
    """Context manager to limit execution time."""
    def signal_handler(signum, frame):
        raise TimeoutException("Rule application timed out")

    # Set the signal handler
    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)


class RuleApplicator:
    """
    Applies correction rules to SQL queries using regex pattern matching.
    """

    def __init__(self, timeout: int = RULE_APPLICATION_TIMEOUT):
        """
        Initialize the rule applicator.

        Args:
            timeout: Maximum time in seconds for applying a single rule
        """
        self.timeout = timeout
        logger.info(f"RuleApplicator initialized with timeout={timeout}s")

    def matches_pattern(self, query: str, pattern: str) -> bool:
        """
        Check if a query matches a regex pattern.

        Args:
            query: SQL query string
            pattern: Regular expression pattern

        Returns:
            True if query matches pattern, False otherwise
        """
        try:
            compiled_pattern = re.compile(pattern, re.IGNORECASE)
            match = compiled_pattern.search(query)
            return match is not None
        except re.error as e:
            logger.error(f"Invalid regex pattern '{pattern}': {e}")
            return False
        except Exception as e:
            logger.error(f"Error matching pattern: {e}")
            return False

    def apply_rule(
        self,
        query: str,
        rule: Rule,
        use_llm: bool = False
    ) -> str:
        """
        Apply a correction rule to a query using LLM-generated regex transformations only.
        No heuristic fallbacks - all transformations must be LLM-generated.

        Args:
            query: SQL query to correct
            rule: Rule to apply (must be RegexRule with replacement field)
            use_llm: Whether to use LLM for transformation (not implemented yet)

        Returns:
            Corrected query if transformation successful, original query otherwise
        """
        try:
            # Check if pattern matches
            if not self.matches_pattern(query, rule.pattern):
                logger.debug(f"Pattern '{rule.pattern}' does not match query")
                return query

            logger.info(f"Rule {rule.rule_id} pattern matched, attempting transformation")

            # Only use LLM-generated replacement (no heuristic fallbacks)
            from error_correction.rule_engine.rule_schema import RegexRule
            if isinstance(rule, RegexRule) and rule.replacement:
                try:
                    # Process replacement string - handle escaped backslashes from JSON
                    # JSON unescapes backslashes, so \\1 in JSON becomes \1 in Python
                    # But we need \1 for regex backreferences, so this should be fine
                    replacement = rule.replacement
                    
                    # Debug: log pattern and replacement
                    logger.info(f"Applying rule {rule.rule_id}")
                    logger.debug(f"Pattern: {rule.pattern}")
                    logger.debug(f"Replacement: {replacement}")
                    logger.debug(f"Query (first 200 chars): {query[:200]}")
                    
                    # First check if pattern matches
                    match = re.search(rule.pattern, query, re.IGNORECASE | re.MULTILINE | re.DOTALL)
                    if not match:
                        logger.warning(f"Pattern does not match query")
                        logger.debug(f"Pattern: {rule.pattern[:150]}")
                        logger.debug(f"Query start: {query[:150]}")
                        return query
                    
                    logger.debug(f"Pattern matched: {match.group(0)[:100]}...")
                    
                    # Apply transformation
                    transformed = re.sub(
                        rule.pattern,
                        replacement,
                        query,
                        count=1,
                        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL
                    )
                    
                    if transformed != query:
                        logger.info(f"Successfully transformed query using LLM-generated replacement")
                        logger.debug(f"Original: {query[:150]}...")
                        logger.debug(f"Transformed: {transformed[:150]}...")
                        return transformed
                    else:
                        logger.warning(f"LLM replacement did not change query - pattern matched but replacement had no effect")
                        logger.warning(f"Matched text: {match.group(0)[:100]}...")
                        logger.warning(f"Replacement would produce: {re.sub(rule.pattern, replacement, match.group(0), flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)}")
                        return query
                except re.error as e:
                    logger.error(f"Invalid regex in rule {rule.rule_id}: {e}")
                    logger.error(f"Pattern: {rule.pattern[:200]}")
                    logger.error(f"Replacement: {rule.replacement[:200]}")
                    return query
                except Exception as e:
                    logger.error(f"Error applying LLM replacement for rule {rule.rule_id}: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    return query
            else:
                # No LLM-generated replacement available
                logger.warning(f"Rule {rule.rule_id} has no replacement field - LLM did not generate transformation")
                return query

        except Exception as e:
            logger.error(f"Error applying rule {rule.rule_id}: {e}")
            return query

# All heuristic transformation methods removed - only LLM-generated transformations are used

    def apply_rules(
        self,
        query: str,
        rules: List[Rule],
        apply_all: bool = False
    ) -> Tuple[List[Rule], str]:
        """
        Apply multiple rules to a query.

        Args:
            query: SQL query to correct
            rules: List of rules to try
            apply_all: If True, apply all matching rules; if False, stop at first match

        Returns:
            Tuple of (matched_rules, corrected_query)
            - matched_rules: List of rules that matched and were applied
            - corrected_query: Corrected query, or original if no rules matched
        """
        matched_rules = []
        current_query = query

        for rule in rules:
            # Try to apply rule
            transformed = self.apply_rule(current_query, rule)

            # Check if transformation was successful (query changed)
            if transformed != current_query:
                matched_rules.append(rule)
                current_query = transformed
                logger.info(f"Rule {rule.rule_id} successfully applied")

                if not apply_all:
                    # Stop at first successful transformation
                    break
            elif self.matches_pattern(current_query, rule.pattern):
                # Pattern matched but no transformation applied
                logger.debug(f"Rule {rule.rule_id} matched but transformation failed")

        if matched_rules:
            logger.info(f"Applied {len(matched_rules)} rule(s) to query")
        else:
            logger.debug("No rules successfully applied")

        return matched_rules, current_query

    def verify_rule(
        self,
        incorrect_query: str,
        rule: Rule,
        expected_corrected: str = None
    ) -> bool:
        """
        Verify that a rule correctly identifies an error pattern.

        Args:
            incorrect_query: The incorrect query
            rule: Rule to verify
            expected_corrected: Expected corrected query (optional)

        Returns:
            True if rule matches the incorrect query, False otherwise
        """
        matches = self.matches_pattern(incorrect_query, rule.pattern)

        if not matches:
            logger.warning(f"Rule {rule.rule_id} does not match the incorrect query it was generated for")
            return False

        logger.info(f"Rule {rule.rule_id} successfully verified")
        return True

    def test_rule_on_queries(
        self,
        rule: Rule,
        test_queries: List[str]
    ) -> Tuple[int, int]:
        """
        Test a rule on multiple queries to see how many it matches.

        Args:
            rule: Rule to test
            test_queries: List of queries to test on

        Returns:
            Tuple of (num_matches, total_queries)
        """
        num_matches = 0

        for query in test_queries:
            if self.matches_pattern(query, rule.pattern):
                num_matches += 1

        logger.info(f"Rule {rule.rule_id} matched {num_matches}/{len(test_queries)} queries")
        return num_matches, len(test_queries)

    def find_matching_rules(
        self,
        query: str,
        rules: List[Rule],
        error_type_filter: Optional[str] = None
    ) -> List[Rule]:
        """
        Find all rules that match a given query.

        Args:
            query: SQL query
            rules: List of rules to check
            error_type_filter: Only return rules of this error type (optional)

        Returns:
            List of matching rules
        """
        matching_rules = []

        for rule in rules:
            # Filter by error type if specified
            if error_type_filter and rule.error_type != error_type_filter:
                continue

            if self.matches_pattern(query, rule.pattern):
                matching_rules.append(rule)

        logger.info(f"Found {len(matching_rules)} matching rules for query")
        return matching_rules
