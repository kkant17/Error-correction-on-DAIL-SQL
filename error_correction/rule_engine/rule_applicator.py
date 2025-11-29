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
        use_llm: bool = False,
        llm_model: str = None
    ) -> str:
        """
        Apply a correction rule to a query using regex-based transformations.
        Falls back to LLM if regex transformation doesn't work.

        Args:
            query: SQL query to correct
            rule: Rule to apply
            use_llm: Whether to use LLM for transformation as fallback
            llm_model: LLM model name to use for fallback transformation

        Returns:
            Corrected query if transformation successful, original query otherwise
        """
        try:
            # Check if pattern matches
            if not self.matches_pattern(query, rule.pattern):
                logger.debug(f"Pattern '{rule.pattern}' does not match query")
                return query

            logger.info(f"Rule {rule.rule_id} pattern matched, attempting transformation")

            # Apply transformation based on error type
            transformed = self._apply_transformation_by_type(query, rule)

            if transformed != query:
                logger.info(f"Successfully transformed query using rule {rule.rule_id}")
                return transformed
            else:
                # If regex transformation didn't work but pattern matched,
                # try LLM-based transformation as fallback
                if use_llm and llm_model:
                    logger.info(f"Regex transformation failed, attempting LLM-based transformation")
                    return self._transform_with_llm(query, rule, llm_model)
                else:
                    logger.warning(f"Rule {rule.rule_id} matched but no transformation applied")
                    return query

        except Exception as e:
            logger.error(f"Error applying rule {rule.rule_id}: {e}")
            return query

    def _transform_with_llm(self, query: str, rule: Rule, model: str) -> str:
        """
        Use LLM to transform the query based on rule correction description.
        
        Args:
            query: SQL query to correct
            rule: Rule with correction description
            model: LLM model name
            
        Returns:
            Transformed query or original if LLM call fails
        """
        try:
            from llm.chatgpt import ask_llm
            
            prompt = f"""You are a SQL expert. Fix the following SQL query based on the error description.

Original (Incorrect) Query:
{query}

Error Description:
{rule.correction}

Error Type: {rule.error_type}

Provide ONLY the corrected SQL query, nothing else. No explanation, no markdown formatting."""

            response = ask_llm(
                model=model,
                batch=[prompt],
                temperature=0.2,
                n=1
            )
            
            if response and isinstance(response, dict):
                corrected = response.get('response', [query])[0] if isinstance(response.get('response'), list) else response.get('response', query)
                corrected = corrected.strip()
                
                # Validate that we got a reasonable response (not empty, still SQL-like)
                if corrected and len(corrected) > 5 and 'select' in corrected.lower():
                    logger.info(f"LLM-based transformation successful")
                    return corrected
            
            logger.warning("LLM-based transformation returned invalid response")
            return query
            
        except Exception as e:
            logger.error(f"LLM-based transformation failed: {e}")
            return query


    def _apply_transformation_by_type(self, query: str, rule: Rule) -> str:
        """
        Apply transformation based on error type.

        Args:
            query: SQL query to transform
            rule: Rule containing error type and correction instructions

        Returns:
            Transformed query
        """
        error_type = rule.error_type
        correction = rule.correction.lower()

        try:
            # Route to appropriate transformation handler
            if error_type == "DISTINCT_ERROR":
                return self._transform_distinct(query, correction)

            elif error_type == "OPERATOR_ERROR":
                return self._transform_operator(query, correction, rule.pattern)

            elif error_type == "ORDERING_ERROR":
                return self._transform_ordering(query, correction)

            elif error_type == "COLUMN_SELECTION":
                return self._transform_column_selection(query, correction, rule.pattern)

            elif error_type == "NULL_HANDLING":
                return self._transform_null_handling(query, correction, rule.pattern)

            elif error_type == "AGGREGATION_ERROR":
                return self._transform_aggregation(query, correction, rule.pattern)

            elif error_type == "FILTER_ERROR":
                return self._transform_filter(query, correction, rule.pattern)

            elif error_type == "JOIN_ERROR":
                return self._transform_join(query, correction, rule.pattern)

            else:
                logger.warning(f"No transformation handler for error type: {error_type}")
                return query

        except Exception as e:
            logger.error(f"Transformation error for {error_type}: {e}")
            return query

    def _transform_distinct(self, query: str, correction: str) -> str:
        """Transform DISTINCT-related errors."""
        if "add distinct" in correction or "insert distinct" in correction:
            # Add DISTINCT after SELECT
            return re.sub(
                r'\bSELECT\s+',
                'SELECT DISTINCT ',
                query,
                count=1,
                flags=re.IGNORECASE
            )

        elif "remove distinct" in correction or "delete distinct" in correction:
            # Remove DISTINCT
            return re.sub(
                r'\bSELECT\s+DISTINCT\s+',
                'SELECT ',
                query,
                flags=re.IGNORECASE
            )

        return query

    def _transform_operator(self, query: str, correction: str, pattern: str) -> str:
        """Transform operator-related errors."""
        # Extract operator change from correction
        # Common patterns: "change = to !=", "replace > with <", etc.

        operator_map = {
            ('=', '!='): (r'=', '!='),
            ('=', '<>'): (r'=', '<>'),
            ('!=', '='): (r'!=', '='),
            ('<>', '='): (r'<>', '='),
            ('>', '<'): (r'>', '<'),
            ('<', '>'): (r'<', '>'),
            ('>=', '<='): (r'>=', '<='),
            ('<=', '>='): (r'<=', '>='),
            ('>', '>='): (r'>', '>='),
            ('<', '<='): (r'<', '<='),
        }

        for (old_op, new_op), (pattern_old, pattern_new) in operator_map.items():
            if old_op in correction and new_op in correction:
                # Try to find and replace in WHERE/HAVING/JOIN conditions
                query = re.sub(
                    r'(WHERE|HAVING|ON|AND|OR)\s+([^\s]+)\s*' + re.escape(pattern_old) + r'\s*',
                    r'\1 \2 ' + pattern_new + ' ',
                    query,
                    flags=re.IGNORECASE
                )
                break

        return query

    def _transform_ordering(self, query: str, correction: str) -> str:
        """Transform ORDER BY-related errors."""
        if "asc" in correction and "desc" in correction:
            # Change ASC to DESC or vice versa
            if "asc to desc" in correction or "asc with desc" in correction:
                return re.sub(
                    r'\bASC\b',
                    'DESC',
                    query,
                    flags=re.IGNORECASE
                )
            elif "desc to asc" in correction or "desc with asc" in correction:
                return re.sub(
                    r'\bDESC\b',
                    'ASC',
                    query,
                    flags=re.IGNORECASE
                )

        if "add order by" in correction:
            # Extract column name from correction if present
            column_match = re.search(r'order by (\w+)', correction, re.IGNORECASE)
            if column_match:
                column = column_match.group(1)
                # Add ORDER BY before LIMIT if exists, otherwise at end
                if re.search(r'\bLIMIT\b', query, re.IGNORECASE):
                    query = re.sub(
                        r'\s*(LIMIT\b)',
                        f' ORDER BY {column} \\1',
                        query,
                        flags=re.IGNORECASE
                    )
                else:
                    query = query.rstrip(';').rstrip() + f' ORDER BY {column}'

        if "remove order by" in correction:
            query = re.sub(
                r'\bORDER\s+BY\s+[^;]+?((?:LIMIT|;|$))',
                r'\1',
                query,
                flags=re.IGNORECASE
            )

        return query

    def _transform_column_selection(self, query: str, correction: str, pattern: str) -> str:
        """Transform column selection errors."""
        # Try to extract column names from correction
        add_match = re.search(r'add column[s]?\s+([^\s,]+)', correction, re.IGNORECASE)
        remove_match = re.search(r'remove column[s]?\s+([^\s,]+)', correction, re.IGNORECASE)
        replace_match = re.search(r'replace (\w+) with (\w+)', correction, re.IGNORECASE)

        if add_match:
            column = add_match.group(1)
            # Add column to SELECT list
            query = re.sub(
                r'(SELECT(?:\s+DISTINCT)?)\s+',
                f'\\1 {column}, ',
                query,
                count=1,
                flags=re.IGNORECASE
            )

        elif remove_match:
            column = remove_match.group(1)
            # Remove column from SELECT list
            query = re.sub(
                rf'\b{column}\s*,\s*',
                '',
                query,
                flags=re.IGNORECASE
            )
            query = re.sub(
                rf',\s*\b{column}\b',
                '',
                query,
                flags=re.IGNORECASE
            )

        elif replace_match:
            old_col = replace_match.group(1)
            new_col = replace_match.group(2)
            # Replace column name
            query = re.sub(
                rf'\b{old_col}\b',
                new_col,
                query,
                flags=re.IGNORECASE
            )

        return query

    def _transform_null_handling(self, query: str, correction: str, pattern: str) -> str:
        """Transform NULL handling errors."""
        if "is null" in correction:
            # Replace = NULL with IS NULL
            query = re.sub(
                r'([^\s]+)\s*=\s*NULL\b',
                r'\1 IS NULL',
                query,
                flags=re.IGNORECASE
            )

        if "is not null" in correction:
            # Replace != NULL with IS NOT NULL
            query = re.sub(
                r'([^\s]+)\s*(?:!=|<>)\s*NULL\b',
                r'\1 IS NOT NULL',
                query,
                flags=re.IGNORECASE
            )

        if "add null check" in correction:
            # Extract column from pattern
            col_match = re.search(r'(\w+)', pattern)
            if col_match:
                column = col_match.group(1)
                # Add IS NOT NULL to WHERE clause
                if "WHERE" in query.upper():
                    query = re.sub(
                        r'(WHERE\s+)',
                        f'\\1{column} IS NOT NULL AND ',
                        query,
                        count=1,
                        flags=re.IGNORECASE
                    )
                else:
                    # Add WHERE clause before ORDER BY or at end
                    if re.search(r'\bORDER\s+BY\b', query, re.IGNORECASE):
                        query = re.sub(
                            r'\s*(ORDER\s+BY)',
                            f' WHERE {column} IS NOT NULL \\1',
                            query,
                            flags=re.IGNORECASE
                        )
                    else:
                        query = query.rstrip(';').rstrip() + f' WHERE {column} IS NOT NULL'

        return query

    def _transform_aggregation(self, query: str, correction: str, pattern: str) -> str:
        """Transform aggregation-related errors."""
        if "add group by" in correction:
            # Extract columns from correction
            col_match = re.search(r'group by ([^\s]+(?:\s*,\s*[^\s]+)*)', correction, re.IGNORECASE)
            if col_match:
                columns = col_match.group(1)
            else:
                # Try to infer from SELECT non-aggregate columns
                select_match = re.search(r'SELECT\s+(?:DISTINCT\s+)?(.*?)\s+FROM', query, re.IGNORECASE | re.DOTALL)
                if select_match:
                    # Simple heuristic: non-aggregate columns
                    columns = re.sub(r'\b(?:COUNT|SUM|AVG|MAX|MIN|GROUP_CONCAT)\s*\([^)]+\)\s*,?\s*', '', select_match.group(1))
                    columns = columns.strip().rstrip(',')

            if columns:
                # Add GROUP BY before HAVING/ORDER BY/LIMIT if exists, otherwise at end
                if re.search(r'\b(?:HAVING|ORDER\s+BY|LIMIT)\b', query, re.IGNORECASE):
                    query = re.sub(
                        r'\s*((?:HAVING|ORDER\s+BY|LIMIT)\b)',
                        f' GROUP BY {columns} \\1',
                        query,
                        count=1,
                        flags=re.IGNORECASE
                    )
                else:
                    query = query.rstrip(';').rstrip() + f' GROUP BY {columns}'

        if "remove group by" in correction:
            query = re.sub(
                r'\bGROUP\s+BY\s+[^;]+?((?:HAVING|ORDER|LIMIT|;|$))',
                r'\1',
                query,
                flags=re.IGNORECASE
            )

        if "add aggregate" in correction:
            # Wrap column in aggregate function
            func_match = re.search(r'(COUNT|SUM|AVG|MAX|MIN)\s*\(([^)]+)\)', correction, re.IGNORECASE)
            if func_match:
                func = func_match.group(1).upper()
                column = func_match.group(2)
                # Replace column with aggregated version in SELECT
                query = re.sub(
                    rf'\b{column}\b',
                    f'{func}({column})',
                    query,
                    count=1,
                    flags=re.IGNORECASE
                )

        return query

    def _transform_filter(self, query: str, correction: str, pattern: str) -> str:
        """Transform filter/WHERE clause errors."""
        if "add where" in correction or "add filter" in correction:
            # Extract condition from correction
            cond_match = re.search(r'where ([^;]+)', correction, re.IGNORECASE)
            if cond_match:
                condition = cond_match.group(1).strip()

                if "WHERE" in query.upper():
                    # Add to existing WHERE with AND
                    query = re.sub(
                        r'(WHERE\s+)',
                        f'\\1{condition} AND ',
                        query,
                        count=1,
                        flags=re.IGNORECASE
                    )
                else:
                    # Add new WHERE clause
                    if re.search(r'\b(?:GROUP\s+BY|ORDER\s+BY|LIMIT)\b', query, re.IGNORECASE):
                        query = re.sub(
                            r'\s*((?:GROUP\s+BY|ORDER\s+BY|LIMIT)\b)',
                            f' WHERE {condition} \\1',
                            query,
                            count=1,
                            flags=re.IGNORECASE
                        )
                    else:
                        query = query.rstrip(';').rstrip() + f' WHERE {condition}'

        if "remove where" in correction:
            # Remove specific condition if mentioned
            cond_match = re.search(r'remove (?:condition |where )?([^;]+)', correction, re.IGNORECASE)
            if cond_match:
                condition_pattern = re.escape(cond_match.group(1).strip())
                query = re.sub(
                    rf'\s*AND\s+{condition_pattern}\b',
                    '',
                    query,
                    flags=re.IGNORECASE
                )
                query = re.sub(
                    rf'\bWHERE\s+{condition_pattern}\s+AND\s+',
                    'WHERE ',
                    query,
                    flags=re.IGNORECASE
                )

        return query

    def _transform_join(self, query: str, correction: str, pattern: str) -> str:
        """Transform JOIN-related errors."""
        # JOINs are complex, so this is a simplified implementation
        if "add join" in correction or "add inner join" in correction:
            # Extract table and condition from correction
            table_match = re.search(r'join (\w+)', correction, re.IGNORECASE)
            on_match = re.search(r'on ([^\s]+\s*=\s*[^\s]+)', correction, re.IGNORECASE)

            if table_match:
                table = table_match.group(1)
                join_type = "INNER JOIN" if "inner" in correction else "JOIN"

                if on_match:
                    on_clause = on_match.group(1)
                    join_clause = f' {join_type} {table} ON {on_clause}'
                else:
                    join_clause = f' {join_type} {table}'

                # Insert JOIN after FROM clause
                query = re.sub(
                    r'(FROM\s+\w+)',
                    f'\\1{join_clause}',
                    query,
                    count=1,
                    flags=re.IGNORECASE
                )

        if "change.*join" in correction:
            # Change JOIN type
            if "left" in correction:
                query = re.sub(r'\b(?:INNER\s+)?JOIN\b', 'LEFT JOIN', query, flags=re.IGNORECASE)
            elif "right" in correction:
                query = re.sub(r'\b(?:INNER\s+)?JOIN\b', 'RIGHT JOIN', query, flags=re.IGNORECASE)
            elif "inner" in correction:
                query = re.sub(r'\b(?:LEFT|RIGHT)\s+JOIN\b', 'INNER JOIN', query, flags=re.IGNORECASE)

        return query

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
