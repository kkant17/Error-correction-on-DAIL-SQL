"""
Rule Generator for Error Correction Pipeline

This module handles generating correction rules from explanations using LLM analysis.
It provides functionality to analyze explanations and generate actionable rules.
"""

import os
import json
import re
import logging
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import openai
from .config import ErrorCorrectionConfig
from .rule_engine import Rule, RuleType
from .llm_explainer import Explanation, ErrorInfo


@dataclass
class RuleGenerationRequest:
    """Data class for rule generation requests"""
    request_id: str
    explanation_id: str
    nl_query: str
    sql_query: str
    error_info: ErrorInfo
    root_cause: str
    violated_pattern: str
    correct_pattern: str
    general_rule: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class GeneratedRule:
    """Data class for generated rules"""
    rule_id: str
    request_id: str
    explanation_id: str
    rule_type: str
    pattern: str
    replacement: str
    description: str
    confidence: float
    conditions: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    validation_passed: bool = False
    test_results: Optional[Dict[str, Any]] = None


@dataclass
class RuleValidationResult:
    """Result of rule validation"""
    catches_error: bool
    corrected_query: Optional[str]
    original_query: str
    validation_passed: bool
    error_message: Optional[str] = None
    confidence_score: float = 0.0


class RuleGenerator:
    """Generator for creating correction rules from explanations with comprehensive validation"""
    
    def __init__(self, config: ErrorCorrectionConfig, api_key: Optional[str] = None):
        """
        Initialize the RuleGenerator
        
        Args:
            config: Configuration object containing parameters
            api_key: OpenAI API key (if None, will use environment variable)
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.api_key = api_key or os.getenv('OPENAI_API_KEY') or config.LLM_API_KEY
        
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
        
        # Initialize OpenAI client
        openai.api_key = self.api_key
        
        # Load existing generated rules
        self.generated_rules: List[GeneratedRule] = []
        self._load_generated_rules()
    
    def _load_generated_rules(self):
        """Load existing generated rules from disk"""
        rules_file = os.path.join(self.config.RULES_DIR, "generated_rules.json")
        if os.path.exists(rules_file):
            try:
                with open(rules_file, 'r') as f:
                    data = json.load(f)
                    for rule_data in data:
                        rule = GeneratedRule(
                            rule_id=rule_data['rule_id'],
                            request_id=rule_data['request_id'],
                            explanation_id=rule_data['explanation_id'],
                            rule_type=rule_data['rule_type'],
                            pattern=rule_data['pattern'],
                            replacement=rule_data['replacement'],
                            description=rule_data['description'],
                            confidence=rule_data['confidence'],
                            conditions=rule_data.get('conditions'),
                            metadata=rule_data.get('metadata'),
                            created_at=rule_data.get('created_at'),
                            validation_passed=rule_data.get('validation_passed', False),
                            test_results=rule_data.get('test_results')
                        )
                        self.generated_rules.append(rule)
            except Exception as e:
                self.logger.warning(f"Could not load generated rules: {e}")
    
    def generate_rule_from_explanation(self, explanation: Explanation, wrong_query: str, nl_query: str) -> Optional[Dict[str, Any]]:
        """
        Generate a rule from an explanation
        
        Args:
            explanation: Explanation object to generate rule from
            wrong_query: The original wrong SQL query
            nl_query: The natural language query
            
        Returns:
            Dictionary containing the generated rule or None if generation fails
        """
        self.logger.info(f"Generating rule from explanation: {explanation.explanation_id}")
        
        # Create rule generation request
        request = RuleGenerationRequest(
            request_id=f"req_{len(self.generated_rules)}_{int(time.time())}",
            explanation_id=explanation.explanation_id,
            nl_query=nl_query,
            sql_query=wrong_query,
            error_info=explanation.error_info,
            root_cause=explanation.root_cause,
            violated_pattern=explanation.violated_pattern,
            correct_pattern=explanation.correct_pattern,
            general_rule=explanation.general_rule,
            metadata=explanation.metadata
        )
        
        # Generate rule using LLM
        rule_definition = self._generate_rule_definition(request)
        if not rule_definition:
            self.logger.error("Failed to generate rule definition")
            return None
        
        # Parse rule to executable format
        executable_rule = self.parse_rule_to_executable(rule_definition)
        if not executable_rule:
            self.logger.error("Failed to parse rule to executable format")
            return None
        
        # Validate rule on the original wrong query
        validation_result = self.validate_rule_on_query(executable_rule, wrong_query)
        
        # Create generated rule object
        generated_rule = GeneratedRule(
            rule_id=f"gen_rule_{len(self.generated_rules)}_{int(time.time())}",
            request_id=request.request_id,
            explanation_id=explanation.explanation_id,
            rule_type=rule_definition.get('rule_type', 'syntax'),
            pattern=rule_definition.get('pattern', ''),
            replacement=rule_definition.get('replacement', ''),
            description=rule_definition.get('description', ''),
            confidence=rule_definition.get('confidence', 0.5),
            conditions=rule_definition.get('conditions'),
            metadata={
                'original_nl_query': nl_query,
                'original_sql_query': wrong_query,
                'root_cause': explanation.root_cause,
                'violated_pattern': explanation.violated_pattern,
                'correct_pattern': explanation.correct_pattern,
                'general_rule': explanation.general_rule,
                'model': self.config.LLM_MODEL,
                'generation_time': datetime.now().isoformat()
            },
            created_at=datetime.now().isoformat(),
            validation_passed=validation_result.validation_passed,
            test_results={
                'catches_error': validation_result.catches_error,
                'corrected_query': validation_result.corrected_query,
                'confidence_score': validation_result.confidence_score
            }
        )
        
        # Store the rule
        self.generated_rules.append(generated_rule)
        self._save_generated_rules()
        
        self.logger.info(f"Generated rule {generated_rule.rule_id} with validation: {validation_result.validation_passed}")
        
        return {
            'rule_definition': rule_definition,
            'executable_rule': executable_rule,
            'validation_result': asdict(validation_result),
            'generated_rule': asdict(generated_rule)
        }
    
    def _generate_rule_definition(self, request: RuleGenerationRequest) -> Optional[Dict[str, Any]]:
        """Generate rule definition using LLM"""
        prompt = self._build_rule_generation_prompt(request)
        
        try:
            response = openai.ChatCompletion.create(
                model=self.config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.config.MAX_TOKENS,
                temperature=self.config.TEMPERATURE
            )
            
            response_text = response.choices[0].message.content.strip()
            return self._parse_rule_response(response_text)
            
        except Exception as e:
            self.logger.error(f"Error generating rule definition: {e}")
            return None
    
    def _build_rule_generation_prompt(self, request: RuleGenerationRequest) -> str:
        """Build the prompt for rule generation"""
        prompt = f"""Based on the following SQL error analysis, generate a formal correction rule:

Natural Language Query: {request.nl_query}
Wrong SQL Query: {request.sql_query}
Error Message: {request.error_info.error_message}
Error Type: {request.error_info.error_type}

Analysis:
- Root Cause: {request.root_cause}
- Violated Pattern: {request.violated_pattern}
- Correct Pattern: {request.correct_pattern}
- General Rule: {request.general_rule}

Generate a formal rule that can automatically detect and correct this type of error. The rule should:

1. Use regex patterns to identify the problematic SQL pattern
2. Provide a replacement pattern that fixes the error
3. Include conditions to ensure the rule is applied safely
4. Be specific enough to avoid false positives

Format your response as JSON with the following structure:
{{
    "rule_type": "syntax|semantic|logical|performance",
    "pattern": "regex pattern to match the problematic code",
    "replacement": "replacement pattern (can use regex groups)",
    "description": "Human-readable description of what this rule does",
    "confidence": 0.0-1.0,
    "conditions": {{
        "min_length": optional_minimum_query_length,
        "max_length": optional_maximum_query_length,
        "contains_keywords": ["keyword1", "keyword2"],
        "excludes_keywords": ["keyword3", "keyword4"],
        "query_type": "SELECT|INSERT|UPDATE|DELETE|CREATE|DROP"
    }},
    "examples": {{
        "wrong": "example of wrong SQL that this rule would catch",
        "correct": "example of corrected SQL after applying this rule"
    }}
}}

Focus on creating rules that are:
- Precise and specific to avoid false positives
- Safe to apply automatically
- Cover the most common cases of this error type
- Include appropriate conditions for safe application"""
        
        return prompt
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for rule generation"""
        return """You are an expert SQL analyst and rule generation specialist. Your task is to create precise, safe, and effective correction rules based on SQL error analysis.

Key guidelines for rule generation:
1. Create regex patterns that are specific and avoid false positives
2. Use appropriate rule types (syntax, semantic, logical, performance)
3. Include conditions to ensure rules are applied safely
4. Provide clear, descriptive rule descriptions
5. Set realistic confidence scores based on rule specificity
6. Consider edge cases and potential side effects
7. Always include examples of wrong and correct SQL

Your rules should be:
- Precise: Match only the intended problematic patterns
- Safe: Include conditions to prevent incorrect applications
- Effective: Address the root cause of the error
- Maintainable: Clear and well-documented
- Testable: Include examples for validation"""
    
    def _parse_rule_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse the LLM response to extract rule information"""
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                parsed = json.loads(json_str)
                
                # Validate required fields
                required_fields = ['rule_type', 'pattern', 'replacement', 'description', 'confidence']
                if all(field in parsed for field in required_fields):
                    return parsed
        except Exception as e:
            self.logger.warning(f"Failed to parse rule response: {e}")
        
        return None
    
    def parse_rule_to_executable(self, rule_definition: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse rule definition to executable format
        
        Args:
            rule_definition: Dictionary containing rule definition
            
        Returns:
            Executable rule dictionary or None if parsing fails
        """
        try:
            # Validate regex pattern
            pattern = rule_definition.get('pattern', '')
            replacement = rule_definition.get('replacement', '')
            
            # Test regex compilation
            re.compile(pattern)
            
            # Test replacement
            re.sub(pattern, replacement, "test")
            
            # Create executable rule
            executable_rule = {
                'rule_id': rule_definition.get('rule_id', f"rule_{int(time.time())}"),
                'rule_type': rule_definition.get('rule_type', 'syntax'),
                'pattern': pattern,
                'replacement': replacement,
                'description': rule_definition.get('description', ''),
                'confidence': rule_definition.get('confidence', 0.5),
                'conditions': rule_definition.get('conditions', {}),
                'examples': rule_definition.get('examples', {}),
                'metadata': rule_definition.get('metadata', {})
            }
            
            return executable_rule
            
        except Exception as e:
            self.logger.error(f"Failed to parse rule to executable format: {e}")
            return None
    
    def validate_rule_on_query(self, rule: Dict[str, Any], query: str) -> RuleValidationResult:
        """
        Validate a rule on a specific query
        
        Args:
            rule: Executable rule dictionary
            query: SQL query to test the rule on
            
        Returns:
            RuleValidationResult containing validation results
        """
        try:
            pattern = rule.get('pattern', '')
            replacement = rule.get('replacement', '')
            conditions = rule.get('conditions', {})
            
            # Check if rule conditions are met
            if not self._check_rule_conditions(conditions, query):
                return RuleValidationResult(
                    catches_error=False,
                    corrected_query=None,
                    original_query=query,
                    validation_passed=False,
                    error_message="Rule conditions not met",
                    confidence_score=0.0
                )
            
            # Check if pattern matches
            if not re.search(pattern, query, re.IGNORECASE):
                return RuleValidationResult(
                    catches_error=False,
                    corrected_query=None,
                    original_query=query,
                    validation_passed=False,
                    error_message="Pattern does not match query",
                    confidence_score=0.0
                )
            
            # Apply the rule
            corrected_query = re.sub(pattern, replacement, query, flags=re.IGNORECASE)
            
            # Check if the rule actually changed the query
            if corrected_query == query:
                return RuleValidationResult(
                    catches_error=False,
                    corrected_query=corrected_query,
                    original_query=query,
                    validation_passed=False,
                    error_message="Rule did not modify the query",
                    confidence_score=0.0
                )
            
            # Validate the corrected query syntax
            is_valid, errors = self._validate_sql_syntax(corrected_query)
            
            if is_valid:
                return RuleValidationResult(
                    catches_error=True,
                    corrected_query=corrected_query,
                    original_query=query,
                    validation_passed=True,
                    confidence_score=rule.get('confidence', 0.5)
                )
            else:
                return RuleValidationResult(
                    catches_error=True,
                    corrected_query=corrected_query,
                    original_query=query,
                    validation_passed=False,
                    error_message=f"Corrected query has syntax errors: {errors}",
                    confidence_score=0.0
                )
                
        except Exception as e:
            self.logger.error(f"Error validating rule on query: {e}")
            return RuleValidationResult(
                catches_error=False,
                corrected_query=None,
                original_query=query,
                validation_passed=False,
                error_message=f"Validation error: {str(e)}",
                confidence_score=0.0
            )
    
    def _check_rule_conditions(self, conditions: Dict[str, Any], query: str) -> bool:
        """Check if rule conditions are met"""
        for condition_type, condition_value in conditions.items():
            if condition_type == "min_length":
                if len(query) < condition_value:
                    return False
            elif condition_type == "max_length":
                if len(query) > condition_value:
                    return False
            elif condition_type == "contains_keywords":
                keywords = condition_value if isinstance(condition_value, list) else [condition_value]
                if not any(keyword.lower() in query.lower() for keyword in keywords):
                    return False
            elif condition_type == "excludes_keywords":
                keywords = condition_value if isinstance(condition_value, list) else [condition_value]
                if any(keyword.lower() in query.lower() for keyword in keywords):
                    return False
            elif condition_type == "query_type":
                if not self._matches_query_type(query, condition_value):
                    return False
        
        return True
    
    def _matches_query_type(self, query: str, query_type: str) -> bool:
        """Check if query matches a specific type"""
        query_upper = query.upper().strip()
        
        if query_type == "SELECT":
            return query_upper.startswith("SELECT")
        elif query_type == "INSERT":
            return query_upper.startswith("INSERT")
        elif query_type == "UPDATE":
            return query_upper.startswith("UPDATE")
        elif query_type == "DELETE":
            return query_upper.startswith("DELETE")
        elif query_type == "CREATE":
            return query_upper.startswith("CREATE")
        elif query_type == "DROP":
            return query_upper.startswith("DROP")
        
        return True
    
    def _validate_sql_syntax(self, sql_query: str) -> Tuple[bool, List[str]]:
        """Validate SQL syntax (simplified version)"""
        errors = []
        
        try:
            # Basic syntax checks
            if not sql_query.strip():
                errors.append("Empty query")
                return False, errors
            
            # Check for balanced quotes
            single_quotes = sql_query.count("'")
            double_quotes = sql_query.count('"')
            
            if single_quotes % 2 != 0:
                errors.append("Unmatched single quotes")
            if double_quotes % 2 != 0:
                errors.append("Unmatched double quotes")
            
            # Check for balanced parentheses
            paren_count = 0
            for char in sql_query:
                if char == '(':
                    paren_count += 1
                elif char == ')':
                    paren_count -= 1
                    if paren_count < 0:
                        errors.append("Unmatched closing parenthesis")
                        break
            
            if paren_count != 0:
                errors.append("Unmatched parentheses")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            errors.append(f"Syntax validation error: {str(e)}")
            return False, errors
    
    def batch_generate_rules(self, explanation_data: List[Tuple[Explanation, str, str]]) -> List[Dict[str, Any]]:
        """
        Generate rules from multiple explanations
        
        Args:
            explanation_data: List of tuples containing (explanation, wrong_query, nl_query)
            
        Returns:
            List of rule generation results
        """
        results = []
        
        for explanation, wrong_query, nl_query in explanation_data:
            try:
                result = self.generate_rule_from_explanation(explanation, wrong_query, nl_query)
                if result:
                    results.append(result)
                else:
                    results.append({
                        'error': f"Failed to generate rule for explanation {explanation.explanation_id}",
                        'explanation_id': explanation.explanation_id
                    })
            except Exception as e:
                self.logger.error(f"Error generating rule for explanation {explanation.explanation_id}: {e}")
                results.append({
                    'error': str(e),
                    'explanation_id': explanation.explanation_id
                })
        
        return results
    
    def get_rules_by_explanation_id(self, explanation_id: str) -> List[GeneratedRule]:
        """Get all rules generated from a specific explanation"""
        return [rule for rule in self.generated_rules if rule.explanation_id == explanation_id]
    
    def get_rules_by_type(self, rule_type: str) -> List[GeneratedRule]:
        """Get all rules of a specific type"""
        return [rule for rule in self.generated_rules if rule.rule_type == rule_type]
    
    def get_validated_rules(self) -> List[GeneratedRule]:
        """Get rules that have passed validation"""
        return [rule for rule in self.generated_rules if rule.validation_passed]
    
    def get_rule_statistics(self) -> Dict[str, Any]:
        """Get statistics about generated rules"""
        if not self.generated_rules:
            return {
                'total_rules': 0,
                'rules_by_type': {},
                'average_confidence': 0.0,
                'validated_rules': 0,
                'validation_success_rate': 0.0
            }
        
        rules_by_type = {}
        validated_rules = 0
        
        for rule in self.generated_rules:
            rule_type = rule.rule_type
            rules_by_type[rule_type] = rules_by_type.get(rule_type, 0) + 1
            
            if rule.validation_passed:
                validated_rules += 1
        
        return {
            'total_rules': len(self.generated_rules),
            'rules_by_type': rules_by_type,
            'average_confidence': sum(rule.confidence for rule in self.generated_rules) / len(self.generated_rules),
            'validated_rules': validated_rules,
            'validation_success_rate': validated_rules / len(self.generated_rules) if self.generated_rules else 0.0
        }
    
    def _save_generated_rules(self):
        """Save generated rules to disk"""
        data = []
        for rule in self.generated_rules:
            rule_data = {
                'rule_id': rule.rule_id,
                'request_id': rule.request_id,
                'explanation_id': rule.explanation_id,
                'rule_type': rule.rule_type,
                'pattern': rule.pattern,
                'replacement': rule.replacement,
                'description': rule.description,
                'confidence': rule.confidence,
                'conditions': rule.conditions,
                'metadata': rule.metadata,
                'created_at': rule.created_at,
                'validation_passed': rule.validation_passed,
                'test_results': rule.test_results
            }
            data.append(rule_data)
        
        with open(os.path.join(self.config.RULES_DIR, "generated_rules.json"), 'w') as f:
            json.dump(data, f, indent=2)
    
    def export_generated_rules(self, file_path: str):
        """Export generated rules to a file"""
        with open(file_path, 'w') as f:
            json.dump([asdict(rule) for rule in self.generated_rules], f, indent=2)
    
    def clear_generated_rules(self):
        """Clear all generated rules"""
        self.generated_rules = []
        rules_file = os.path.join(self.config.RULES_DIR, "generated_rules.json")
        if os.path.exists(rules_file):
            os.remove(rules_file)
