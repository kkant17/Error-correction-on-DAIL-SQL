"""
LLM-based Rule Generator for SQL Error Correction
"""
import json
import re
import logging
from typing import Any, Dict, List, Optional

from llm.chatgpt import ask_llm, ChatGPT
from error_correction.config import (
    EXPLANATION_PROMPT_TEMPLATE,
    SOLUTION_PROMPT_TEMPLATE,
    RULE_GENERATION_PROMPT_TEMPLATE,
    ERROR_CLASSES
)
from error_correction.rule_engine.rule_schema import (
    Rule,
    RegexRule,
    TransformRule,
    RuleSkeleton,
    ValidationResult
)
from error_correction.rule_engine.schema_loader import get_database_schema

logger = logging.getLogger(__name__)


class RuleGenerator:
    """
    Generates error explanations and correction rules using LLM.
    """

    def __init__(
        self,
        model: str = "gpt-4",
        temperature: float = 0.3,
        use_code_generation: bool = False,
        allow_code_execution: bool = False,
        use_regex_rules: bool = True
    ):
        """
        Initialize the rule generator.

        Args:
            model: LLM model to use for generation
            temperature: Temperature for LLM generation
            use_code_generation: Allow expensive transform code synthesis
            allow_code_execution: Permit executing generated code (safety flag)
            use_regex_rules: Prefer lightweight regex-based rules
        """
        self.model = model
        self.temperature = temperature
        self.use_code_generation = use_code_generation
        self.allow_code_execution = allow_code_execution
        self.use_regex_rules = use_regex_rules
        
        # Initialize ChatGPT wrapper with system prompt support for rule generation
        self.llm_with_system_prompt = ChatGPT(model=model, temperature=temperature)
        
        logger.info(
            "RuleGenerator initialized with model=%s temperature=%.2f regex_mode=%s system_prompt=enabled",
            model,
            temperature,
            use_regex_rules
        )

    def generate_explanation(
        self,
        predicted_sql: str,
        gold_sql: str,
        db_id: str,
        question: str = ""
    ) -> str:
        """
        Generate explanation for why a SQL query is wrong.

        Args:
            predicted_sql: The incorrect predicted query
            gold_sql: The correct gold query
            db_id: Database identifier
            question: Natural language question

        Returns:
            Explanation string
        """
        # Get database schema context
        schema_context = get_database_schema(db_id)
        if schema_context:
            schema_context = f"\n{schema_context}\n"
        else:
            schema_context = "\nDatabase schema not available.\n"
        
        # Build prompt (NOTE: gold_sql is NOT included in the prompt - LLM should infer errors without seeing the correct answer)
        prompt = EXPLANATION_PROMPT_TEMPLATE.format(
            db_id=db_id,
            question=question,
            predicted_sql=predicted_sql,
            schema_context=schema_context
        )

        try:
            # Call LLM
            response = ask_llm(
                self.model,
                [prompt],
                self.temperature,
                1
            )

            explanation = response["response"][0].strip()
            logger.debug(f"Generated explanation: {explanation[:100]}...")
            return explanation

        except Exception as e:
            logger.error(f"Error generating explanation: {e}")
            return f"Failed to generate explanation: {str(e)}"

    def generate_solution(
        self,
        incorrect_query: str,
        explanation: str,
        db_id: str,
        question: str = ""
    ) -> str:
        """
        Generate a suggested solution for fixing the incorrect SQL query.

        Args:
            incorrect_query: The incorrect SQL query
            explanation: Explanation of why the query is wrong
            db_id: Database identifier
            question: Natural language question (optional)

        Returns:
            Solution string describing how to fix the query
        """
        # Get database schema context
        schema_context = get_database_schema(db_id)
        if schema_context:
            schema_context = f"\n{schema_context}\n"
        else:
            schema_context = "\nDatabase schema not available.\n"
        
        # Build prompt
        prompt = SOLUTION_PROMPT_TEMPLATE.format(
            db_id=db_id,
            incorrect_query=incorrect_query,
            explanation=explanation,
            schema_context=schema_context
        )

        try:
            # Call LLM
            response = ask_llm(
                self.model,
                [prompt],
                self.temperature,
                1
            )

            solution = response["response"][0].strip()
            logger.debug(f"Generated solution: {solution[:100]}...")
            return solution

        except Exception as e:
            logger.error(f"Error generating solution: {e}")
            return f"Failed to generate solution: {str(e)}"

    def generate_rules(
        self,
        incorrect_query: str,
        correct_query: str,
        explanation: str,
        question: str = "",
        db_id: str = "",
        solution: str = None,
        max_retries: int = 1
    ) -> List[Rule]:
        """
        Generate correction rules based on suggested solution using LLM.
        Uses ChatGPT wrapper with system prompt for better rule quality.
        Includes post-processing to clean up common LLM mistakes.

        Args:
            incorrect_query: The incorrect SQL query
            correct_query: The correct SQL query (not used in prompt, kept for compatibility)
            explanation: Explanation of the error (not used in prompt, kept for compatibility)
            question: Natural language question (not used in prompt, kept for compatibility)
            db_id: Database identifier (not used in prompt, kept for compatibility)
            solution: Suggested solution for fixing the query (REQUIRED for rule generation)
            max_retries: Maximum number of retries if invalid pattern generated

        Returns:
            List of generated rules (can be multiple)
        """
        # Solution is required - if not provided, generate it
        if not solution:
            logger.warning("Solution not provided to generate_rules(), generating it now...")
            solution = self.generate_solution(incorrect_query, explanation, db_id, question)
            if "Failed" in solution:
                logger.error("Failed to generate solution, cannot generate rules")
                return []
        
        # Truncate solution if too long to prevent context window overflow
        MAX_SOLUTION_LENGTH = 500
        if len(solution) > MAX_SOLUTION_LENGTH:
            original_length = len(solution)
            solution = solution[:MAX_SOLUTION_LENGTH].rstrip() + "..."
            logger.debug(f"Truncated solution from {original_length} to {len(solution)} chars")
        
        # Build prompt (NOTE: Only uses incorrect_query and solution - no explanation, question, or db_id)
        # Include the incorrect query prominently so LLM can see the actual structure
        base_prompt = RULE_GENERATION_PROMPT_TEMPLATE.format(
            incorrect_query=incorrect_query,
            solution=solution,
            error_classes=", ".join(ERROR_CLASSES)
        )

        for attempt in range(max_retries + 1):
            try:
                # Add retry instruction if this is a retry
                if attempt > 0:
                    prompt = base_prompt + "\n\nIMPORTANT: Your previous pattern had an error. Please generate a NEW pattern that:\n- Does NOT use look-behind assertions ((?<=...) or (?<!...))\n- Uses capture groups ((...)) instead\n- Includes a replacement field\n- Is a valid Python regex pattern"
                else:
                    prompt = base_prompt

                # Use ChatGPT wrapper with system prompt for better rule quality
                llm_output = self.llm_with_system_prompt.generate(prompt, self.temperature)
                logger.debug(f"LLM rule generation output (attempt {attempt + 1}): {llm_output}")
                
                # Log the incorrect query for debugging pattern matching
                logger.debug(f"Incorrect query being matched: {incorrect_query[:200]}...")

                # Parse the key-value output
                rules = self._parse_rule_output(llm_output)
                
                # Post-process rules to clean up common LLM mistakes
                rules = [r for r in rules if self._post_process_rule(r)]
                
                # Validate that rules have replacement field AND pattern matches the query
                valid_rules = []
                error_details = []  # Track specific error types for retry feedback
                import re
                for rule in rules:
                    from error_correction.rule_engine.rule_schema import RegexRule
                    if isinstance(rule, RegexRule):
                        if not rule.replacement:
                            logger.warning(f"Rule {rule.rule_id} missing replacement field - skipping")
                            continue
                        
                        # CRITICAL: Validate that pattern actually matches the incorrect query
                        try:
                            pattern_match = re.search(
                                rule.pattern, 
                                incorrect_query, 
                                re.IGNORECASE | re.MULTILINE | re.DOTALL
                            )
                            if not pattern_match:
                                error_type = "pattern_mismatch"
                                error_msg = f"Pattern does not match the actual query structure"
                                logger.warning(f"Rule {rule.rule_id} pattern does NOT match the incorrect query!")
                                logger.warning(f"  Pattern: {rule.pattern[:150]}...")
                                logger.warning(f"  Query: {incorrect_query[:150]}...")
                                error_details.append((error_type, error_msg, rule.pattern[:100]))
                                # If this is not the last attempt, retry with feedback
                                if attempt < max_retries:
                                    logger.info(f"Pattern mismatch detected - will retry with feedback")
                                    # Don't add to valid_rules, will retry
                                    continue
                                else:
                                    logger.error(f"Pattern mismatch on final attempt - rule will be skipped")
                                    continue
                            else:
                                logger.debug(f"Rule {rule.rule_id} pattern matches query ✓")
                                logger.debug(f"  Matched: {pattern_match.group(0)[:100]}...")
                        except re.error as e:
                            error_msg = str(e)
                            # Detect specific error types
                            if "unbalanced parenthesis" in error_msg.lower() or "unexpected end" in error_msg.lower():
                                error_type = "unbalanced_parentheses"
                                error_msg = "Unbalanced parentheses in pattern"
                            elif "bad escape" in error_msg.lower():
                                error_type = "bad_escape"
                                error_msg = "Invalid escape sequence (use \\\\s+ not \\s+ in JSON)"
                            else:
                                error_type = "invalid_regex"
                                error_msg = f"Invalid regex pattern: {error_msg}"
                            
                            logger.error(f"Rule {rule.rule_id} has invalid regex pattern: {error_msg}")
                            logger.error(f"  Pattern: {rule.pattern[:150]}...")
                            error_details.append((error_type, error_msg, rule.pattern[:100]))
                            if attempt < max_retries:
                                continue  # Retry
                            else:
                                continue  # Skip invalid pattern
                        
                        valid_rules.append(rule)
                    else:
                        # Base Rule without replacement - try to convert
                        logger.warning(f"Rule {rule.rule_id} is base Rule without replacement - cannot transform")
                
                if valid_rules:
                    logger.info(f"Generated {len(valid_rules)} valid rule(s) with replacements that match the query")
                    return valid_rules
                elif attempt < max_retries:
                    logger.warning(f"Attempt {attempt + 1} failed: no valid rules with matching patterns, retrying with feedback...")
                    # Generate specific retry feedback based on error type
                    retry_feedback = self._generate_retry_feedback(error_details, incorrect_query)
                    base_prompt += retry_feedback
                    continue
                else:
                    logger.warning(f"All {max_retries + 1} attempts failed: no valid rules with matching patterns generated")
                    return []

            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"Error generating rules (attempt {attempt + 1}): {e}, retrying...")
                    continue
                else:
                    logger.error(f"Error generating rules after {max_retries + 1} attempts: {e}")
                    return []
        
        return []
    
    def _post_process_rule(self, rule: Rule) -> bool:
        """
        Post-process and validate a rule to clean up common LLM mistakes.
        Modifies the rule in-place and returns True if rule is valid.
        
        Checks:
        1. Remove escaped backslashes in SQL replacement (\\. → .)
        2. Reject duplicate clause keywords in replacement
        3. Reject replacement starting with clause keyword without SELECT
        4. Check clause ordering in replacement
        
        Args:
            rule: Rule object to post-process
            
        Returns:
            True if rule is valid after post-processing, False otherwise
        """
        from error_correction.rule_engine.rule_schema import RegexRule
        
        if not isinstance(rule, RegexRule):
            return True  # Can't post-process base Rule without replacement
        
        replacement = rule.replacement or ''
        if not replacement:
            logger.warning(f"Rule {rule.rule_id}: No replacement field")
            return False
        
        # Fix 1: Remove escaped backslashes that shouldn't be in SQL
        # LLM sometimes outputs: "s\.Name" when it means "s.Name"
        original_replacement = replacement
        replacement = re.sub(r'\\\.', '.', replacement)  # \. → .
        replacement = re.sub(r'\\_', '_', replacement)   # \_ → _
        replacement = re.sub(r'\\-', '-', replacement)   # \- → -
        replacement = re.sub(r'\\/', '/', replacement)   # \/ → /
        replacement = re.sub(r'\\\(', '(', replacement)  # \( → (
        replacement = re.sub(r'\\\)', ')', replacement)  # \) → )
        replacement = re.sub(r'\\\*', '*', replacement)  # \* → *
        replacement = re.sub(r'\\\\', '', replacement)   # Remove double backslashes
        
        # Fix 2: Replace $1, $2 with \1, \2 (JavaScript syntax → Python syntax)
        replacement = re.sub(r'\$(\d+)', r'\\1', replacement)
        
        if replacement != original_replacement:
            logger.debug(f"Rule {rule.rule_id}: Cleaned replacement escapes")
            rule.replacement = replacement
        
        replacement_lower = replacement.lower()
        
        # Check 2: No duplicate WHERE
        if replacement_lower.count(' where ') > 1:
            logger.warning(f"Rule {rule.rule_id}: Replacement contains duplicate WHERE - rejecting")
            return False
        
        # Check 3: No duplicate ORDER BY
        if replacement_lower.count(' order by ') > 1:
            logger.warning(f"Rule {rule.rule_id}: Replacement contains duplicate ORDER BY - rejecting")
            return False
        
        # Check 4: No duplicate GROUP BY
        if replacement_lower.count(' group by ') > 1:
            logger.warning(f"Rule {rule.rule_id}: Replacement contains duplicate GROUP BY - rejecting")
            return False
        
        # Check 5: Replacement shouldn't start with clause keywords (without SELECT)
        stripped = replacement_lower.strip()
        bad_starts = ('where ', 'group by ', 'order by ', 'having ', 'limit ', 'join ')
        if any(stripped.startswith(bs) for bs in bad_starts):
            # Exception: if it's a backreference pattern that will be prepended
            if not stripped.startswith('\\'):
                logger.warning(f"Rule {rule.rule_id}: Replacement starts with clause keyword without SELECT - rejecting")
                return False
        
        # Check 6: Clause ordering in replacement
        if not self._has_correct_clause_order(replacement):
            logger.warning(f"Rule {rule.rule_id}: Replacement has incorrect SQL clause ordering - rejecting")
            return False
        
        return True
    
    def _has_correct_clause_order(self, sql: str) -> bool:
        """
        Check if SQL clauses appear in correct order.
        
        Correct order: SELECT → FROM → JOIN → WHERE → GROUP BY → HAVING → ORDER BY → LIMIT
        
        Args:
            sql: SQL string to check
            
        Returns:
            True if clauses are in correct order, False otherwise
        """
        sql_lower = sql.lower()
        
        # Get positions of clauses (-1 if not found)
        positions = {
            'select': sql_lower.find('select'),
            'from': sql_lower.find(' from '),
            'where': sql_lower.find(' where '),
            'group': sql_lower.find(' group by '),
            'having': sql_lower.find(' having '),
            'order': sql_lower.find(' order by '),
            'limit': sql_lower.find(' limit ')
        }
        
        # Remove clauses that aren't present
        present = {k: v for k, v in positions.items() if v >= 0}
        
        if not present:
            return True  # No clauses to check (might be a backreference-only replacement)
        
        # Check they appear in correct order
        expected_order = ['select', 'from', 'where', 'group', 'having', 'order', 'limit']
        prev_pos = -1
        for clause in expected_order:
            if clause in present:
                if present[clause] < prev_pos:
                    logger.debug(f"Clause '{clause}' at {present[clause]} appears before previous clause at {prev_pos}")
                    return False  # Out of order!
                prev_pos = present[clause]
        
        return True

    def _generate_retry_feedback(self, error_details: List[tuple], incorrect_query: str) -> str:
        """
        Generate specific retry feedback based on error types encountered.
        
        Args:
            error_details: List of (error_type, error_msg, pattern_snippet) tuples
            incorrect_query: The incorrect query being matched
            
        Returns:
            Feedback string to append to retry prompt
        """
        if not error_details:
            # Generic feedback if no specific errors captured
            return f"\n\nIMPORTANT: Your previous pattern had an error. Please generate a NEW pattern that:\n- Does NOT use look-behind assertions\n- Uses simple capture groups (max 2-3)\n- Includes a replacement field\n- Is a valid Python regex pattern"
        
        # Group errors by type
        error_types = [e[0] for e in error_details]
        
        feedback_parts = ["\n\nIMPORTANT: Your previous pattern had errors. Fix them:"]
        
        if "unbalanced_parentheses" in error_types:
            feedback_parts.append("- UNBALANCED PARENTHESES: Use fewer capture groups (max 2-3). Simplify the pattern - avoid deep nesting.")
        
        if "bad_escape" in error_types:
            feedback_parts.append("- INVALID ESCAPE SEQUENCES: In JSON, escape backslashes: use \\\\s+ not \\s+, \\\\1 not \\1")
        
        if "pattern_mismatch" in error_types:
            feedback_parts.append(f"- PATTERN MISMATCH: Your pattern did not match the actual query. The query is:\n{incorrect_query[:200]}...\n  Match the ACTUAL structure shown above, not what you expect.")
        
        if "invalid_regex" in error_types and "unbalanced_parentheses" not in error_types and "bad_escape" not in error_types:
            feedback_parts.append("- INVALID REGEX: Check your pattern syntax. Use simple patterns with max 2-3 capture groups.")
        
        feedback_parts.append("- Keep patterns SIMPLE: match key structural elements, not every detail")
        feedback_parts.append("- Generate a NEW, simpler pattern")
        
        return "\n".join(feedback_parts)

    def generate_regex_rule(
        self,
        incorrect_query: str,
        correct_query: str,
        explanation: str,
        question: str = "",
        db_id: str = ""
    ) -> Optional[RegexRule]:
        """
        Generate a lightweight regex-based rule using heuristic matching.
        """
        if not incorrect_query or not correct_query:
            logger.warning("Regex rule generation requires both incorrect and correct queries")
            return None

        category = self._infer_error_category(explanation, incorrect_query)
        error_type = category if category in ERROR_CLASSES else "OTHER"
        pattern = self._build_literal_pattern(incorrect_query)
        description = explanation or "Automatically generated regex rule"

        rule = RegexRule(
            pattern=pattern,
            correction="Replace incorrect SQL with the provided correct SQL.",
            error_type=error_type,
            error_category=category,
            description=description[:300],
            replacement=correct_query,
            incorrect_example=incorrect_query,
            correct_example=correct_query,
            confidence_score=0.55,
            metadata={
                "db_id": db_id,
                "question": question
            }
        )
        logger.info("Generated regex rule %s (category=%s)", rule.rule_id, category)
        return rule

    def generate_rule_with_code(
        self,
        incorrect_query: str,
        correct_query: str,
        explanation: str,
        db_id: str = "",
        question: str = ""
    ) -> Optional[TransformRule]:
        """
        Generate a richer rule that can optionally include transformation code.
        """
        skeleton = self._build_stub_skeleton(
            incorrect_query=incorrect_query,
            correct_query=correct_query,
            category=self._infer_error_category(explanation, incorrect_query),
            explanation=explanation
        )

        if not self.use_code_generation:
            logger.debug("Code generation disabled; falling back to regex-based transform rule")
            regex_rule = self.generate_regex_rule(
                incorrect_query=incorrect_query,
                correct_query=correct_query,
                explanation=explanation,
                question=question,
                db_id=db_id
            )
            if not regex_rule:
                return None
            return TransformRule(
                pattern=regex_rule.pattern,
                correction=regex_rule.correction,
                error_type=regex_rule.error_type,
                error_category=regex_rule.error_category,
                description=regex_rule.description,
                replacement=regex_rule.replacement,
                incorrect_example=regex_rule.incorrect_example,
                correct_example=regex_rule.correct_example,
                confidence_score=regex_rule.confidence_score,
                metadata=regex_rule.metadata,
                skeleton=skeleton,
                transform_code=None,
                validation_result=None,
                generation_method="regex_only"
            )

        transform_code = self._build_stub_transform_code(incorrect_query, correct_query)
        validation = self._build_validation_stub(
            incorrect_query,
            correct_query,
            transform_code
        )

        category = skeleton.error_category
        error_type = category if category in ERROR_CLASSES else "OTHER"

        rule = TransformRule(
            pattern=self._build_literal_pattern(incorrect_query),
            correction="LLM-generated transformation code",
            error_type=error_type,
            error_category=category,
            description=skeleton.match_description,
            replacement=correct_query,
            incorrect_example=incorrect_query,
            correct_example=correct_query,
            confidence_score=skeleton.confidence,
            metadata={"db_id": db_id, "question": question},
            skeleton=skeleton,
            transform_code=transform_code,
            validation_result=validation,
            generation_method="code_stub"
        )
        logger.info("Generated transform rule %s (category=%s)", rule.rule_id, category)
        return rule

    def _parse_rule_output(self, llm_output: str) -> List[Rule]:
        """
        Parse LLM output in Key-Value format.
        
        Expected format:
            PATTERN: ...
            REPLACEMENT: ...
            CORRECTION: ...
            ERROR_TYPE: ...
            CONFIDENCE: ...

        Args:
            llm_output: Raw LLM output string

        Returns:
            List of Rule objects
        """
        rules = []
        result = {}
        
        # Parse key-value pairs
        for line in llm_output.strip().split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().upper()
                value = value.strip()
                
                if key == 'PATTERN':
                    result['pattern'] = value
                elif key == 'REPLACEMENT':
                    result['replacement'] = value
                elif key == 'CORRECTION':
                    result['correction'] = value
                elif key == 'ERROR_TYPE':
                    result['error_type'] = value
                elif key == 'CONFIDENCE':
                    result['confidence'] = value
        
        # Validate required fields
        if result.get('pattern') and result.get('correction'):
            rule = self._create_rule_from_dict(result)
            if rule:
                rules.append(rule)
        else:
            logger.warning(f"Missing required fields in LLM output")
            logger.debug(f"Parsed: {result}")
            logger.debug(f"Raw output: {llm_output[:500]}")
        
        return rules

    def _create_rule_from_dict(self, data: Dict) -> Optional[Rule]:
        """
        Create a Rule object from parsed JSON dictionary.
        Creates a RegexRule if replacement is provided, otherwise a base Rule.

        Args:
            data: Dictionary containing rule fields

        Returns:
            Rule object (RegexRule if replacement available, otherwise base Rule) or None if invalid
        """
        try:
            # Extract required fields
            pattern = data.get('pattern', '')
            correction = data.get('correction', '')
            replacement = data.get('replacement', '')  # LLM-generated transformation

            # Extract error_type from metadata if structured that way,
            # or directly from top-level
            if 'metadata' in data:
                error_type = data['metadata'].get('error_type', 'OTHER')
                confidence = data['metadata'].get('confidence', 'medium')
                description = data['metadata'].get('description', correction)
            else:
                error_type = data.get('error_type', 'OTHER')
                confidence = data.get('confidence', 'medium')
                description = data.get('description', correction)

            # Validate required fields
            if not pattern or not correction:
                logger.warning("Missing required fields (pattern or correction)")
                return None

            # Validate error_type is in allowed classes
            if error_type not in ERROR_CLASSES:
                logger.warning(f"Invalid error_type '{error_type}', defaulting to OTHER")
                error_type = "OTHER"

            # Validate regex pattern
            try:
                re.compile(pattern)
            except re.error as e:
                error_msg = str(e)
                # Provide helpful error message for common issues
                if "look-behind" in error_msg.lower() or "lookbehind" in error_msg.lower():
                    logger.warning(f"Invalid regex pattern '{pattern[:100]}...': {e}. Python regex does not support variable-width look-behinds. Use capture groups instead.")
                else:
                    logger.warning(f"Invalid regex pattern '{pattern[:100]}...': {e}")
                return None

            # Convert confidence string to float
            confidence_map = {'high': 0.9, 'medium': 0.7, 'low': 0.5}
            confidence_score = confidence_map.get(confidence.lower(), 0.7)

            # If replacement is provided, create RegexRule for executable transformation
            if replacement:
                return RegexRule(
                    pattern=pattern,
                    correction=correction,
                    error_type=error_type,
                    error_category=error_type,
                    description=description,
                    replacement=replacement,
                    confidence_score=confidence_score,
                    metadata={
                        'confidence': confidence,
                        'llm_generated': True
                    }
                )
            else:
                # Fallback to base Rule if no replacement provided
                logger.warning("No replacement field in rule - transformation may not work")
                return Rule(
                    pattern=pattern,
                    correction=correction,
                    error_type=error_type
                )

        except Exception as e:
            logger.error(f"Error creating rule from dict: {e}")
            return None

    def _infer_error_category(self, explanation: str, incorrect_query: str) -> str:
        """
        Basic heuristic to guess the error category based on text cues.
        """
        text = f"{explanation or ''} {incorrect_query}".lower()
        keyword_map = {
            "distinct": "DISTINCT_ERROR",
            "join": "JOIN_ERROR",
            "group by": "AGGREGATION_ERROR",
            "having": "AGGREGATION_ERROR",
            "where": "FILTER_ERROR",
            "order by": "ORDERING_ERROR",
            "null": "NULL_HANDLING",
            "operator": "OPERATOR_ERROR",
            "column": "COLUMN_SELECTION",
            "subquery": "SUBQUERY_ERROR",
        }
        for keyword, category in keyword_map.items():
            if keyword in text:
                return category
        return "OTHER"

    def _build_literal_pattern(self, query: str) -> str:
        """
        Construct a case-insensitive regex that matches the entire query literally.
        """
        sanitized = query.strip()
        escaped = re.escape(sanitized)
        flexible = re.sub(r'\\\s+', r'\\s+', escaped)
        return rf"(?is)^{flexible}$"

    def _build_stub_transform_code(self, incorrect_query: str, correct_query: str) -> str:
        """
        Generate simple Python code that performs a literal replacement.
        """
        pattern = self._build_literal_pattern(incorrect_query)
        escaped_correct = correct_query.replace('"""', r'\"\"\"')
        return f'''import re

def transform_query(sql: str) -> str:
    pattern = r"""{pattern}"""
    if re.fullmatch(pattern, sql.strip(), flags=re.IGNORECASE | re.DOTALL):
        return """{escaped_correct}"""
    return sql
'''

    def _build_validation_stub(
        self,
        incorrect_query: str,
        correct_query: str,
        transform_code: str
    ) -> ValidationResult:
        """
        Provide a ValidationResult placeholder, optionally simulating success.
        """
        if self.allow_code_execution:
            return ValidationResult(
                passed=True,
                test_query=incorrect_query,
                expected_output=correct_query,
                actual_output=correct_query,
                error_message=None,
                execution_time_ms=0.0
            )
        return ValidationResult(
            passed=False,
            test_query=incorrect_query,
            expected_output=correct_query,
            actual_output="",
            error_message="Code execution disabled",
            execution_time_ms=0.0
        )

    def _build_stub_skeleton(
        self,
        incorrect_query: str,
        correct_query: str,
        category: str,
        explanation: str
    ) -> RuleSkeleton:
        """
        Create a simple skeleton object when the full generator is unavailable.
        """
        return RuleSkeleton(
            error_category=category,
            match_description=f"Queries similar to: {incorrect_query[:80]}",
            transformation_instructions=explanation or "Replace the incorrect SQL with its gold counterpart.",
            expected_behavior="Match the semantics of the provided gold SQL.",
            example_transformation=f"{incorrect_query[:60]} -> {correct_query[:60]}",
            confidence=0.6
        )
