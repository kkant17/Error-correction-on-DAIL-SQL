"""
Rule Engine for Error Correction Pipeline

This module handles rule validation, application, and management for the error correction pipeline.
It provides functionality to validate rules, apply them to queries, and manage rule storage using AST parsing.
"""

import os
import json
import re
import logging
import uuid
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import sqlparse
from sqlparse import sql, tokens
from sqlparse.sql import Statement, TokenList, Token
from .config import ErrorCorrectionConfig


class RuleType(Enum):
    """Enumeration of rule types"""
    SYNTAX = "syntax"
    SEMANTIC = "semantic"
    LOGICAL = "logical"
    PERFORMANCE = "performance"
    GENERAL = "general"


@dataclass
class Rule:
    """Data class for storing rule information"""
    rule_id: str
    description: str
    pattern: str  # regex or AST pattern
    correction: str  # transformation to apply
    confidence_score: float
    created_at: str
    rule_type: str = "general"  # syntax, semantic, logical, performance
    conditions: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    usage_count: int = 0
    success_count: int = 0
    last_used: Optional[str] = None


@dataclass
class RuleApplicationResult:
    """Result of applying rules to a SQL query"""
    is_valid: bool
    applied_rules: List[Rule]
    corrected_sql: Optional[str]
    original_sql: str
    errors: List[str]
    warnings: List[str]
    confidence_score: float


class RuleEngine:
    """Engine for managing and applying correction rules with AST parsing"""
    
    def __init__(self, config: ErrorCorrectionConfig):
        """
        Initialize the RuleEngine
        
        Args:
            config: Configuration object containing parameters
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.rules: List[Rule] = []
        self.rule_index: Dict[str, Rule] = {}
        
        # Load existing rules
        self._load_rules()
        
        # Initialize common SQL patterns for validation
        self._initialize_sql_patterns()
    
    def _initialize_sql_patterns(self):
        """Initialize common SQL patterns for validation"""
        self.sql_keywords = {
            'SELECT', 'FROM', 'WHERE', 'GROUP BY', 'HAVING', 'ORDER BY', 'LIMIT',
            'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'INDEX',
            'JOIN', 'INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'OUTER JOIN',
            'UNION', 'INTERSECT', 'EXCEPT', 'WITH', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END'
        }
        
        self.sql_functions = {
            'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'DISTINCT', 'COALESCE', 'NULLIF',
            'UPPER', 'LOWER', 'LENGTH', 'SUBSTRING', 'TRIM', 'CAST', 'CONVERT'
        }
    
    def _load_rules(self):
        """Load existing rules from the rules directory"""
        try:
            rules_dir = self.config.RULES_DIR
            if not os.path.exists(rules_dir):
                os.makedirs(rules_dir, exist_ok=True)
                self.logger.info(f"Created rules directory: {rules_dir}")
                return
            
            # Load from main rules file
            main_rules_file = os.path.join(rules_dir, "rules.json")
            if os.path.exists(main_rules_file):
                self._load_rules_from_file(main_rules_file)
            
            # Load from individual rule files
            for filename in os.listdir(rules_dir):
                if filename.endswith('.json') and filename != 'rules.json':
                    rule_file = os.path.join(rules_dir, filename)
                    self._load_rules_from_file(rule_file)
            
            self.logger.info(f"Loaded {len(self.rules)} rules from {rules_dir}")
            
        except Exception as e:
            self.logger.error(f"Failed to load rules: {e}")
    
    def _load_rules_from_file(self, file_path: str):
        """Load rules from a specific JSON file"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Handle both single rule and list of rules
            if isinstance(data, dict):
                rules_data = [data]
            else:
                rules_data = data
            
            for rule_data in rules_data:
                rule = Rule(
                    rule_id=rule_data.get('rule_id', str(uuid.uuid4())),
                    description=rule_data.get('description', ''),
                    pattern=rule_data.get('pattern', ''),
                    correction=rule_data.get('correction', ''),
                    confidence_score=rule_data.get('confidence_score', 0.5),
                    created_at=rule_data.get('created_at', datetime.now().isoformat()),
                    rule_type=rule_data.get('rule_type', 'general'),
                    conditions=rule_data.get('conditions'),
                    metadata=rule_data.get('metadata'),
                    usage_count=rule_data.get('usage_count', 0),
                    success_count=rule_data.get('success_count', 0),
                    last_used=rule_data.get('last_used')
                )
                
                if self._validate_rule_structure(rule):
                    self.rules.append(rule)
                    self.rule_index[rule.rule_id] = rule
                    self.logger.debug(f"Loaded rule: {rule.rule_id}")
                else:
                    self.logger.warning(f"Invalid rule structure, skipping: {rule.rule_id}")
        
        except Exception as e:
            self.logger.error(f"Failed to load rules from {file_path}: {e}")
    
    def apply_rules(self, sql_query: str) -> RuleApplicationResult:
        """
        Apply rules to a SQL query
        
        Args:
            sql_query: SQL query to apply rules to
            
        Returns:
            RuleApplicationResult containing validation results and corrections
        """
        self.logger.info(f"Applying rules to query: {sql_query[:100]}...")
        
        original_sql = sql_query.strip()
        current_sql = original_sql
        applied_rules = []
        errors = []
        warnings = []
        total_confidence = 0.0
        
        try:
            # First, validate the original query
            is_original_valid, original_errors = self._validate_sql_syntax(current_sql)
            if not is_original_valid:
                errors.extend(original_errors)
                self.logger.warning(f"Original query has syntax errors: {original_errors}")
            
            # Apply rules in order of confidence
            sorted_rules = sorted(self.rules, key=lambda r: r.confidence_score, reverse=True)
            
            for rule in sorted_rules:
                try:
                    if self._is_rule_applicable(rule, current_sql):
                        corrected_sql = self._apply_rule(rule, current_sql)
                        
                        if corrected_sql != current_sql:
                            # Validate the corrected query
                            is_valid, validation_errors = self._validate_sql_syntax(corrected_sql)
                            
                            if is_valid:
                                self.logger.info(f"Applied rule {rule.rule_id}: {rule.description}")
                                current_sql = corrected_sql
                                applied_rules.append(rule)
                                total_confidence += rule.confidence_score
                                
                                # Update rule usage statistics
                                self._update_rule_usage(rule.rule_id, True)
                            else:
                                self.logger.warning(f"Rule {rule.rule_id} produced invalid SQL: {validation_errors}")
                                warnings.append(f"Rule {rule.rule_id} produced invalid SQL")
                                self._update_rule_usage(rule.rule_id, False)
                
                except Exception as e:
                    self.logger.error(f"Error applying rule {rule.rule_id}: {e}")
                    warnings.append(f"Error applying rule {rule.rule_id}: {str(e)}")
            
            # Final validation
            is_final_valid, final_errors = self._validate_sql_syntax(current_sql)
            if not is_final_valid:
                errors.extend(final_errors)
            
            # Calculate average confidence
            avg_confidence = total_confidence / len(applied_rules) if applied_rules else 0.0
            
            result = RuleApplicationResult(
                is_valid=is_final_valid and len(errors) == 0,
                applied_rules=applied_rules,
                corrected_sql=current_sql if current_sql != original_sql else None,
                original_sql=original_sql,
                errors=errors,
                warnings=warnings,
                confidence_score=avg_confidence
            )
            
            self.logger.info(f"Rule application completed. Applied {len(applied_rules)} rules. Valid: {result.is_valid}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error in rule application: {e}")
            return RuleApplicationResult(
                is_valid=False,
                applied_rules=[],
                corrected_sql=None,
                original_sql=original_sql,
                errors=[f"Rule application failed: {str(e)}"],
                warnings=[],
                confidence_score=0.0
            )
    
    def add_rule(self, rule_definition: Dict[str, Any]) -> str:
        """
        Add a new rule to the engine
        
        Args:
            rule_definition: Dictionary containing rule definition
            
        Returns:
            Rule ID if successful, None if failed
        """
        try:
            # Generate rule ID if not provided
            rule_id = rule_definition.get('rule_id', str(uuid.uuid4()))
            
            # Create rule object
            rule = Rule(
                rule_id=rule_id,
                description=rule_definition.get('description', ''),
                pattern=rule_definition.get('pattern', ''),
                correction=rule_definition.get('correction', ''),
                confidence_score=rule_definition.get('confidence_score', 0.5),
                created_at=rule_definition.get('created_at', datetime.now().isoformat()),
                rule_type=rule_definition.get('rule_type', 'general'),
                conditions=rule_definition.get('conditions'),
                metadata=rule_definition.get('metadata')
            )
            
            # Validate rule
            if not self._validate_rule_structure(rule):
                self.logger.error(f"Invalid rule structure: {rule_id}")
                return None
            
            if not self._validate_rule_logic(rule):
                self.logger.error(f"Invalid rule logic: {rule_id}")
                return None
            
            # Add rule
            self.rules.append(rule)
            self.rule_index[rule_id] = rule
            
            # Save to file
            self._save_rule_to_file(rule)
            
            self.logger.info(f"Added rule: {rule_id}")
            return rule_id
            
        except Exception as e:
            self.logger.error(f"Failed to add rule: {e}")
            return None
    
    def validate_rule(self, rule: Rule, test_query: str) -> bool:
        """
        Validate a rule against a test query
        
        Args:
            rule: Rule to validate
            test_query: SQL query to test the rule against
            
        Returns:
            True if rule is valid, False otherwise
        """
        try:
            # Check if rule is applicable
            if not self._is_rule_applicable(rule, test_query):
                return False
            
            # Apply the rule
            corrected_query = self._apply_rule(rule, test_query)
            
            # Validate the result
            is_valid, errors = self._validate_sql_syntax(corrected_query)
            
            if is_valid:
                self.logger.info(f"Rule {rule.rule_id} validation passed")
                return True
            else:
                self.logger.warning(f"Rule {rule.rule_id} validation failed: {errors}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error validating rule {rule.rule_id}: {e}")
            return False
    
    def get_all_rules(self) -> List[Dict[str, Any]]:
        """
        Get all rules as dictionaries
        
        Returns:
            List of rule dictionaries
        """
        return [asdict(rule) for rule in self.rules]
    
    def get_rule_by_id(self, rule_id: str) -> Optional[Rule]:
        """Get a rule by ID"""
        return self.rule_index.get(rule_id)
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID"""
        if rule_id not in self.rule_index:
            return False
        
        rule = self.rule_index[rule_id]
        self.rules.remove(rule)
        del self.rule_index[rule_id]
        
        # Remove from file
        rule_file = os.path.join(self.config.RULES_DIR, f"{rule_id}.json")
        if os.path.exists(rule_file):
            os.remove(rule_file)
        
        self.logger.info(f"Removed rule: {rule_id}")
        return True
    
    def _validate_sql_syntax(self, sql_query: str) -> Tuple[bool, List[str]]:
        """
        Validate SQL syntax using sqlparse
        
        Args:
            sql_query: SQL query to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        try:
            # Parse the SQL
            parsed = sqlparse.parse(sql_query)
            
            if not parsed:
                errors.append("Empty or unparseable SQL query")
                return False, errors
            
            # Check for basic syntax issues
            for statement in parsed:
                if not self._validate_statement(statement):
                    errors.append(f"Invalid statement: {str(statement)}")
            
            # Check for common SQL issues
            common_errors = self._check_common_sql_errors(sql_query)
            errors.extend(common_errors)
            
            return len(errors) == 0, errors
            
        except Exception as e:
            errors.append(f"SQL parsing error: {str(e)}")
            return False, errors
    
    def _validate_statement(self, statement: Statement) -> bool:
        """Validate a parsed SQL statement"""
        try:
            # Check for basic structure
            tokens_list = list(statement.flatten())
            
            # Must have at least one token
            if not tokens_list:
                return False
            
            # Check for balanced parentheses
            paren_count = 0
            for token in tokens_list:
                if token.ttype is tokens.Punctuation:
                    if token.value == '(':
                        paren_count += 1
                    elif token.value == ')':
                        paren_count -= 1
                        if paren_count < 0:
                            return False
            
            return paren_count == 0
            
        except Exception:
            return False
    
    def _check_common_sql_errors(self, sql_query: str) -> List[str]:
        """Check for common SQL errors"""
        errors = []
        
        # Check for balanced quotes
        single_quotes = sql_query.count("'")
        double_quotes = sql_query.count('"')
        
        if single_quotes % 2 != 0:
            errors.append("Unmatched single quotes")
        if double_quotes % 2 != 0:
            errors.append("Unmatched double quotes")
        
        # Check for common typos
        common_typos = {
            'WERE': 'WHERE',
            'FORM': 'FROM',
            'SELCT': 'SELECT',
            'UPDTE': 'UPDATE',
            'DELTE': 'DELETE'
        }
        
        for typo, correction in common_typos.items():
            if typo in sql_query.upper():
                errors.append(f"Possible typo: '{typo}' should be '{correction}'")
        
        return errors
    
    def _is_rule_applicable(self, rule: Rule, sql_query: str) -> bool:
        """Check if a rule is applicable to a SQL query"""
        try:
            # Check pattern matching
            if rule.pattern:
                if not re.search(rule.pattern, sql_query, re.IGNORECASE):
                    return False
            
            # Check conditions
            if rule.conditions:
                if not self._check_rule_conditions(rule.conditions, sql_query):
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking rule applicability: {e}")
            return False
    
    def _check_rule_conditions(self, conditions: Dict[str, Any], sql_query: str) -> bool:
        """Check rule conditions"""
        for condition_type, condition_value in conditions.items():
            if condition_type == "min_length":
                if len(sql_query) < condition_value:
                    return False
            elif condition_type == "max_length":
                if len(sql_query) > condition_value:
                    return False
            elif condition_type == "contains_keywords":
                keywords = condition_value if isinstance(condition_value, list) else [condition_value]
                if not any(keyword.lower() in sql_query.lower() for keyword in keywords):
                    return False
            elif condition_type == "excludes_keywords":
                keywords = condition_value if isinstance(condition_value, list) else [condition_value]
                if any(keyword.lower() in sql_query.lower() for keyword in keywords):
                    return False
            elif condition_type == "query_type":
                # Check if query matches the specified type
                if not self._matches_query_type(sql_query, condition_value):
                    return False
        
        return True
    
    def _matches_query_type(self, sql_query: str, query_type: str) -> bool:
        """Check if query matches a specific type"""
        sql_upper = sql_query.upper().strip()
        
        if query_type == "SELECT":
            return sql_upper.startswith("SELECT")
        elif query_type == "INSERT":
            return sql_upper.startswith("INSERT")
        elif query_type == "UPDATE":
            return sql_upper.startswith("UPDATE")
        elif query_type == "DELETE":
            return sql_upper.startswith("DELETE")
        elif query_type == "CREATE":
            return sql_upper.startswith("CREATE")
        elif query_type == "DROP":
            return sql_upper.startswith("DROP")
        
        return True
    
    def _apply_rule(self, rule: Rule, sql_query: str) -> str:
        """Apply a rule to a SQL query"""
        try:
            if rule.pattern and rule.correction:
                # Use regex substitution
                return re.sub(rule.pattern, rule.correction, sql_query, flags=re.IGNORECASE)
            else:
                return sql_query
                
        except Exception as e:
            self.logger.error(f"Error applying rule {rule.rule_id}: {e}")
            return sql_query
    
    def _validate_rule_structure(self, rule: Rule) -> bool:
        """Validate rule structure"""
        if not rule.rule_id or not rule.description or not rule.pattern or not rule.correction:
            return False
        
        if not 0 <= rule.confidence_score <= 1:
            return False
        
        return True
    
    def _validate_rule_logic(self, rule: Rule) -> bool:
        """Validate rule logic"""
        try:
            # Test regex pattern
            if rule.pattern:
                re.compile(rule.pattern)
            
            # Test replacement
            if rule.pattern and rule.correction:
                re.sub(rule.pattern, rule.correction, "test")
            
            return True
            
        except Exception:
            return False
    
    def _update_rule_usage(self, rule_id: str, success: bool):
        """Update rule usage statistics"""
        if rule_id in self.rule_index:
            rule = self.rule_index[rule_id]
            rule.usage_count += 1
            if success:
                rule.success_count += 1
            rule.last_used = datetime.now().isoformat()
            
            # Save updated rule
            self._save_rule_to_file(rule)
    
    def _save_rule_to_file(self, rule: Rule):
        """Save a rule to its individual file"""
        try:
            rule_file = os.path.join(self.config.RULES_DIR, f"{rule.rule_id}.json")
            with open(rule_file, 'w') as f:
                json.dump(asdict(rule), f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save rule {rule.rule_id}: {e}")
    
    def get_rule_statistics(self) -> Dict[str, Any]:
        """Get statistics about stored rules"""
        if not self.rules:
            return {
                'total_rules': 0,
                'rules_by_type': {},
                'average_confidence': 0.0,
                'total_usage': 0,
                'success_rate': 0.0
            }
        
        rules_by_type = {}
        total_usage = 0
        total_success = 0
        
        for rule in self.rules:
            rule_type = rule.rule_type
            rules_by_type[rule_type] = rules_by_type.get(rule_type, 0) + 1
            total_usage += rule.usage_count
            total_success += rule.success_count
        
        return {
            'total_rules': len(self.rules),
            'rules_by_type': rules_by_type,
            'average_confidence': sum(rule.confidence_score for rule in self.rules) / len(self.rules),
            'total_usage': total_usage,
            'success_rate': total_success / total_usage if total_usage > 0 else 0.0
        }
    
    def export_rules(self, file_path: str):
        """Export all rules to a file"""
        try:
            with open(file_path, 'w') as f:
                json.dump(self.get_all_rules(), f, indent=2)
            self.logger.info(f"Exported {len(self.rules)} rules to {file_path}")
        except Exception as e:
            self.logger.error(f"Failed to export rules: {e}")
    
    def clear_all_rules(self):
        """Clear all rules"""
        self.rules.clear()
        self.rule_index.clear()
        
        # Remove all rule files
        try:
            for filename in os.listdir(self.config.RULES_DIR):
                if filename.endswith('.json'):
                    os.remove(os.path.join(self.config.RULES_DIR, filename))
        except Exception as e:
            self.logger.error(f"Failed to clear rule files: {e}")
        
        self.logger.info("Cleared all rules")


class RuleTester:
    """Tester for validating rules against correct queries to ensure safety"""
    
    def __init__(self, config: ErrorCorrectionConfig, vector_db_manager):
        """
        Initialize the RuleTester
        
        Args:
            config: Configuration object containing parameters
            vector_db_manager: VectorDBManager instance for accessing correct queries
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.vector_db_manager = vector_db_manager
    
    def test_rule_on_correct_queries(self, rule: Dict[str, Any], sample_size: Optional[int] = None) -> Tuple[float, List[str]]:
        """
        Test a new rule on correct queries to ensure it doesn't break them
        
        Args:
            rule: Rule dictionary to test
            sample_size: Number of correct queries to sample (defaults to X_SAMPLE_SIZE)
            
        Returns:
            Tuple of (pass_rate, failed_queries)
        """
        if sample_size is None:
            sample_size = self.config.X_SAMPLE_SIZE
        
        self.logger.info(f"Testing rule {rule.get('rule_id', 'unknown')} on {sample_size} correct queries")
        
        # Get correct query count
        total_correct_queries = self.vector_db_manager.get_query_count('correct_queries')
        
        if total_correct_queries == 0:
            self.logger.warning("No correct queries available for testing")
            return 0.0, []
        
        # Adjust sample size if we have fewer queries than requested
        actual_sample_size = min(sample_size, total_correct_queries)
        
        if actual_sample_size < sample_size:
            self.logger.warning(f"Only {total_correct_queries} correct queries available, testing on {actual_sample_size}")
        
        # Sample correct queries
        try:
            # Get all correct queries and randomly sample
            all_queries = self.vector_db_manager.get_all_queries('correct_queries')
            
            if len(all_queries) < actual_sample_size:
                sample_queries = all_queries
            else:
                import random
                sample_queries = random.sample(all_queries, actual_sample_size)
            
            self.logger.info(f"Sampled {len(sample_queries)} correct queries for testing")
            
        except Exception as e:
            self.logger.error(f"Failed to sample correct queries: {e}")
            return 0.0, []
        
        # Test rule on each sampled query
        passed_tests = 0
        failed_queries = []
        
        for query_record in sample_queries:
            try:
                # Apply rule to the query
                modified_query = self._apply_rule_to_query(rule, query_record.sql_query)
                
                # Check if rule modified the query (it shouldn't for correct queries)
                if modified_query == query_record.sql_query:
                    # Rule didn't modify the query - this is good
                    passed_tests += 1
                    self.logger.debug(f"Rule passed on query {query_record.query_id}: no modification")
                else:
                    # Rule modified a correct query - this is bad
                    failed_queries.append({
                        'query_id': query_record.query_id,
                        'original_query': query_record.sql_query,
                        'modified_query': modified_query,
                        'reason': 'Rule incorrectly modified a correct query'
                    })
                    self.logger.warning(f"Rule failed on query {query_record.query_id}: modified correct query")
                    self.logger.warning(f"  Original: {query_record.sql_query}")
                    self.logger.warning(f"  Modified: {modified_query}")
                
            except Exception as e:
                # Error applying rule - consider this a failure
                failed_queries.append({
                    'query_id': query_record.query_id,
                    'original_query': query_record.sql_query,
                    'modified_query': None,
                    'reason': f"Error applying rule: {str(e)}"
                })
                self.logger.error(f"Error testing rule on query {query_record.query_id}: {e}")
        
        # Calculate pass rate
        pass_rate = passed_tests / len(sample_queries) if sample_queries else 0.0
        
        self.logger.info(f"Rule testing completed:")
        self.logger.info(f"  - Total queries tested: {len(sample_queries)}")
        self.logger.info(f"  - Passed tests: {passed_tests}")
        self.logger.info(f"  - Failed tests: {len(failed_queries)}")
        self.logger.info(f"  - Pass rate: {pass_rate:.3f}")
        
        return pass_rate, failed_queries
    
    def is_rule_safe(self, rule: Dict[str, Any], sample_size: Optional[int] = None) -> bool:
        """
        Check if a rule is safe to use (doesn't break correct queries)
        
        Args:
            rule: Rule dictionary to test
            sample_size: Number of correct queries to sample (defaults to X_SAMPLE_SIZE)
            
        Returns:
            True if rule is safe (pass_rate > 0.95), False otherwise
        """
        pass_rate, failed_queries = self.test_rule_on_correct_queries(rule, sample_size)
        
        # Rule is safe if it passes 95% of tests
        is_safe = pass_rate >= 0.95
        
        if is_safe:
            self.logger.info(f"Rule {rule.get('rule_id', 'unknown')} is SAFE (pass rate: {pass_rate:.3f})")
        else:
            self.logger.warning(f"Rule {rule.get('rule_id', 'unknown')} is UNSAFE (pass rate: {pass_rate:.3f})")
            self.logger.warning(f"Failed on {len(failed_queries)} queries")
        
        return is_safe
    
    def validate_rule_before_adding(self, rule: Dict[str, Any], rule_engine) -> bool:
        """
        Validate a rule before adding it to the rule engine
        
        Args:
            rule: Rule dictionary to validate
            rule_engine: RuleEngine instance to add the rule to
            
        Returns:
            True if rule is safe and added successfully, False otherwise
        """
        self.logger.info(f"Validating rule {rule.get('rule_id', 'unknown')} before adding to rule engine")
        
        # Test rule safety
        if not self.is_rule_safe(rule):
            self.logger.warning(f"Rule {rule.get('rule_id', 'unknown')} failed safety test - not adding to rule engine")
            return False
        
        # Test rule syntax and logic
        if not rule_engine.validate_rule(rule, "SELECT * FROM test"):
            self.logger.warning(f"Rule {rule.get('rule_id', 'unknown')} failed syntax/logic validation - not adding to rule engine")
            return False
        
        # Add rule to rule engine
        try:
            rule_id = rule_engine.add_rule(rule)
            self.logger.info(f"Successfully added rule {rule_id} to rule engine")
            return True
        except Exception as e:
            self.logger.error(f"Failed to add rule to rule engine: {e}")
            return False
    
    def batch_validate_rules(self, rules: List[Dict[str, Any]], rule_engine) -> List[Dict[str, Any]]:
        """
        Validate multiple rules and return only the safe ones
        
        Args:
            rules: List of rule dictionaries to validate
            rule_engine: RuleEngine instance to add safe rules to
            
        Returns:
            List of dictionaries containing validation results
        """
        self.logger.info(f"Batch validating {len(rules)} rules")
        
        validation_results = []
        safe_rules = []
        
        for i, rule in enumerate(rules, 1):
            self.logger.info(f"Validating rule {i}/{len(rules)}: {rule.get('rule_id', 'unknown')}")
            
            # Test rule safety
            is_safe = self.is_rule_safe(rule)
            
            # Test rule syntax/logic
            syntax_valid = rule_engine.validate_rule(rule, "SELECT * FROM test")
            
            result = {
                'rule_id': rule.get('rule_id', f'rule_{i}'),
                'is_safe': is_safe,
                'syntax_valid': syntax_valid,
                'overall_valid': is_safe and syntax_valid,
                'added_to_engine': False
            }
            
            if result['overall_valid']:
                # Try to add rule to engine
                try:
                    rule_id = rule_engine.add_rule(rule)
                    result['added_to_engine'] = True
                    result['engine_rule_id'] = rule_id
                    safe_rules.append(rule)
                    self.logger.info(f"Rule {rule.get('rule_id', 'unknown')} added to rule engine")
                except Exception as e:
                    result['add_error'] = str(e)
                    self.logger.error(f"Failed to add rule {rule.get('rule_id', 'unknown')}: {e}")
            else:
                self.logger.warning(f"Rule {rule.get('rule_id', 'unknown')} failed validation")
            
            validation_results.append(result)
        
        self.logger.info(f"Batch validation completed:")
        self.logger.info(f"  - Total rules: {len(rules)}")
        self.logger.info(f"  - Safe rules: {len(safe_rules)}")
        self.logger.info(f"  - Added to engine: {sum(1 for r in validation_results if r['added_to_engine'])}")
        
        return validation_results
    
    def _apply_rule_to_query(self, rule: Dict[str, Any], query: str) -> Optional[str]:
        """Apply a rule to a query"""
        if not rule:
            return None
        
        pattern = rule.get('pattern', '')
        replacement = rule.get('replacement', '')
        
        if not pattern or not replacement:
            return None
        
        try:
            import re
            modified_query = re.sub(pattern, replacement, query, flags=re.IGNORECASE)
            return modified_query
        except Exception as e:
            self.logger.error(f"Error applying rule to query: {e}")
            return None
    
    def get_safety_statistics(self) -> Dict[str, Any]:
        """Get statistics about rule safety testing"""
        try:
            total_correct_queries = self.vector_db_manager.get_query_count('correct_queries')
            return {
                'total_correct_queries': total_correct_queries,
                'sample_size': self.config.X_SAMPLE_SIZE,
                'safety_threshold': 0.95,
                'can_test_rules': total_correct_queries > 0
            }
        except Exception as e:
            self.logger.error(f"Failed to get safety statistics: {e}")
            return {
                'total_correct_queries': 0,
                'sample_size': self.config.X_SAMPLE_SIZE,
                'safety_threshold': 0.95,
                'can_test_rules': False,
                'error': str(e)
            }
