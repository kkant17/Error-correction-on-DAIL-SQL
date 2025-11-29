"""
In-memory store for committed (validated) rules.
"""
import re
import logging
from typing import List, Optional, Union
from datetime import datetime

from error_correction.rule_engine.rule_schema import Rule, RegexRule

logger = logging.getLogger(__name__)


class CommittedRulesStore:
    """
    In-memory store for validated rules that passed the pipeline.

    Rules are stored sorted by created_at timestamp (most recent first)
    for fast retrieval when applying to new queries.
    """

    def __init__(self):
        """Initialize empty rules store."""
        self.rules: List[Union[Rule, RegexRule]] = []
        logger.info("CommittedRulesStore initialized")

    def add_rule(self, rule: Union[Rule, RegexRule]) -> None:
        """
        Add validated rule to store and maintain sort order.

        Args:
            rule: Rule or RegexRule that passed validation
        """
        self.rules.append(rule)
        # Sort by created_at timestamp (most recent first) - handle both Rule and RegexRule
        self.rules.sort(
            key=lambda r: getattr(r, 'created_at', datetime.now()),
            reverse=True
        )
        logger.info(f"Added rule {rule.rule_id} to committed store (total: {len(self.rules)} rules)")

    def find_matching_rule(self, query: str) -> Optional[Union[Rule, RegexRule]]:
        """
        Find first rule (most recent) whose pattern matches the query.

        Uses O(n) linear scan with regex pattern matching.
        For < 100 rules, this is fast enough (< 100ms).

        Args:
            query: SQL query to match against rule patterns

        Returns:
            First matching Rule or None if no match
        """
        for rule in self.rules:
            if rule.pattern:
                try:
                    match = re.search(
                        rule.pattern,
                        query,
                        re.IGNORECASE | re.MULTILINE
                    )
                    if match:
                        logger.info(f"Found matching rule: {rule.rule_id}")
                        return rule
                except re.error as e:
                    logger.warning(f"Invalid pattern in rule {rule.rule_id}: {e}")
                    continue

        logger.debug(f"No matching rule found for query (checked {len(self.rules)} rules)")
        return None

    def get_all_rules(self) -> List[Union[Rule, RegexRule]]:
        """
        Return all committed rules.

        Returns:
            Copy of rules list
        """
        return self.rules.copy()

    def get_rule_by_id(self, rule_id: str) -> Optional[Union[Rule, RegexRule]]:
        """
        Get rule by ID.

        Args:
            rule_id: Rule identifier

        Returns:
            Rule or None if not found
        """
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    def size(self) -> int:
        """
        Get number of committed rules.

        Returns:
            Number of rules in store
        """
        return len(self.rules)

    def clear(self) -> None:
        """Clear all rules from store."""
        count = len(self.rules)
        self.rules.clear()
        logger.info(f"Cleared {count} rules from committed store")
