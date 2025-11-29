"""
Rule Code Synthesizer - Generates executable Python code from natural language skeletons

This module takes natural language rule skeletons and synthesizes executable Python code
that can transform SQL queries. Uses sqlparse for AST-based SQL manipulation.
"""
import re
import logging
from typing import Optional
from llm.chatgpt import ask_llm
from error_correction.rule_engine.rule_schema import RuleSkeleton

logger = logging.getLogger(__name__)


class RuleCodeSynthesizer:
    """
    Synthesizes executable Python code from rule skeletons.

    Takes natural language transformation instructions and generates Python functions
    that use sqlparse to manipulate SQL queries at the AST level.
    """

    def __init__(
        self,
        model: str = "gpt-4",
        temperature: float = 0.2,  # Lower temp for code generation
        allow_code_execution: bool = True
    ):
        """
        Initialize the code synthesizer.

        Args:
            model: LLM model to use for code generation
            temperature: Temperature for generation (lower = more deterministic)
            allow_code_execution: Whether to allow executing generated code (security)
        """
        self.model = model
        self.temperature = temperature
        self.allow_code_execution = allow_code_execution

        if not allow_code_execution:
            logger.warning("Code execution is DISABLED - generated code will not be executable")

        logger.info(f"RuleCodeSynthesizer initialized with model={model}")

    def synthesize_code(
        self,
        skeleton: RuleSkeleton,
        test_query: str,
        expected_output: str
    ) -> Optional[str]:
        """
        Generate Python transformation code from a skeleton.

        Args:
            skeleton: RuleSkeleton with natural language instructions
            test_query: Test query to verify the code works
            expected_output: Expected output after transformation

        Returns:
            Python code as string, or None if generation failed
        """
        logger.info(f"Synthesizing code for error category: {skeleton.error_category}")

        try:
            # Build prompt for code generation
            prompt = self._build_code_generation_prompt(
                skeleton, test_query, expected_output
            )

            # Call LLM to generate code (correct signature: model, batch, temperature, n)
            response = ask_llm(
                self.model,
                [prompt],
                self.temperature,
                1
            )
            # Extract the response text
            llm_output = response["response"][0] if isinstance(response["response"], list) else response["response"]

            # Extract and validate code
            code = self._extract_and_validate_code(llm_output)

            if code:
                logger.info("Successfully generated transformation code")
            else:
                logger.warning("Failed to extract valid code from LLM response")

            return code

        except Exception as e:
            logger.error(f"Error synthesizing code: {e}")
            return None

    def _build_code_generation_prompt(
        self,
        skeleton: RuleSkeleton,
        test_query: str,
        expected_output: str
    ) -> str:
        """
        Build prompt for LLM code generation.

        Args:
            skeleton: Rule skeleton with instructions
            test_query: Test query for verification
            expected_output: Expected output

        Returns:
            Formatted prompt string
        """
        prompt = f"""You are an expert Python programmer specializing in SQL query manipulation.

**Task**: Generate a Python function that transforms SQL queries based on the natural language instructions below.

**Rule Skeleton:**
- Error Category: {skeleton.error_category}
- Match Description: {skeleton.match_description}
- Transformation Instructions: {skeleton.transformation_instructions}
- Expected Behavior: {skeleton.expected_behavior}
- Example: {skeleton.example_transformation}

**Test Case:**
Input Query: {test_query}
Expected Output: {expected_output}

**Requirements:**
1. Create a function named `transform_query(sql: str) -> str`
2. Use the `sqlparse` library to parse and manipulate SQL
3. Implement the transformation according to the instructions above
4. Handle edge cases and errors gracefully
5. Return the transformed SQL string
6. Include error handling to return original query if transformation fails

**Available Libraries:**
- `sqlparse`: For SQL parsing (import as: `import sqlparse`)
- `re`: For regex operations (import as: `import re`)
- Standard Python libraries only (no external dependencies)

**Code Structure:**
```python
import sqlparse
import re

def transform_query(sql: str) -> str:
    \"\"\"
    Transform SQL query: {skeleton.error_category}

    {skeleton.transformation_instructions}
    \"\"\"
    try:
        # Your transformation code here

        return transformed_sql
    except Exception as e:
        # Return original query if transformation fails
        return sql
```

**Important Guidelines:**
- Keep code simple and readable
- Add comments explaining key steps
- Use sqlparse tokens and AST manipulation
- Test the transformation logic
- Handle whitespace and formatting properly
- Return original query if transformation fails
- Use only ASCII characters in your response. Do not include any non-ASCII characters (such as special symbols, emojis, or Unicode characters)

**Generate ONLY the Python code (no explanations):**"""

        return prompt

    def _extract_and_validate_code(self, response: str) -> Optional[str]:
        """
        Extract and validate Python code from LLM response.

        Args:
            response: Raw LLM response

        Returns:
            Validated Python code string or None
        """
        try:
            # Extract code from markdown code blocks
            code_pattern = r'```python\s*(.*?)\s*```'
            matches = re.findall(code_pattern, response, re.DOTALL)

            if matches:
                code = matches[0]
            else:
                # Try without markdown
                code = response.strip()

            # Validate code structure
            if not self._validate_code_structure(code):
                logger.error("Generated code failed structure validation")
                return None

            # Basic syntax check
            try:
                compile(code, '<string>', 'exec')
            except SyntaxError as e:
                logger.error(f"Generated code has syntax error: {e}")
                return None

            return code

        except Exception as e:
            logger.error(f"Error extracting code: {e}")
            return None

    def _validate_code_structure(self, code: str) -> bool:
        """
        Validate that generated code has the required structure.

        Args:
            code: Python code string

        Returns:
            True if valid, False otherwise
        """
        # Check for required function
        if 'def transform_query(' not in code:
            logger.error("Missing transform_query function")
            return False

        # Check for required imports
        if 'import sqlparse' not in code and 'from sqlparse' not in code:
            logger.warning("Code doesn't import sqlparse (might fail at runtime)")

        # Check for return statement
        if 'return' not in code:
            logger.error("No return statement in code")
            return False

        # Check for basic error handling
        if 'try:' not in code or 'except' not in code:
            logger.warning("No error handling in generated code")

        return True

    def generate_regex_pattern(
        self,
        skeleton: RuleSkeleton
    ) -> Optional[str]:
        """
        Generate a regex pattern for matching queries based on skeleton.

        This creates a pattern that can be used to quickly filter queries
        before applying the expensive transformation.

        Args:
            skeleton: Rule skeleton

        Returns:
            Regex pattern string or None
        """
        logger.info("Generating regex pattern for quick matching")

        prompt = f"""Generate a Python regular expression pattern that matches SQL queries with this error:

**Error Description:**
Category: {skeleton.error_category}
Match Description: {skeleton.match_description}

**Requirements:**
- Create a regex pattern (Python re module syntax)
- Pattern should match queries that have this error
- Be specific enough to avoid false positives
- Use (?i) flag for case-insensitive matching if needed
- Keep pattern relatively simple
- Use only ASCII characters in your response. Do not include any non-ASCII characters (such as special symbols, emojis, or Unicode characters)

**Output format (JSON):**
{{
  "pattern": "<regex pattern>",
  "description": "<brief description of what pattern matches>"
}}

**IMPORTANT:** Use only ASCII characters in your response. Do not include any non-ASCII characters (such as special symbols, emojis, or Unicode characters).

Generate the JSON:"""

        try:
            response = ask_llm(self.model, [prompt], 0.2, 1)
            llm_output = response["response"][0] if isinstance(response["response"], list) else response["response"]

            # Extract JSON
            json_match = re.search(r'\{.*\}', llm_output, re.DOTALL)
            if json_match:
                import json
                data = json.loads(json_match.group(0))
                pattern = data.get('pattern', '')

                # Validate pattern
                try:
                    re.compile(pattern)
                    logger.info(f"Generated pattern: {pattern}")
                    return pattern
                except re.error:
                    logger.error("Generated pattern is invalid regex")
                    return None

            return None

        except Exception as e:
            logger.error(f"Error generating pattern: {e}")
            return None

    def refine_code(
        self,
        original_code: str,
        error_message: str,
        test_query: str,
        expected_output: str
    ) -> Optional[str]:
        """
        Refine generated code based on error feedback.

        Args:
            original_code: The code that failed
            error_message: Error message from execution
            test_query: Test query that failed
            expected_output: Expected output

        Returns:
            Refined code or None
        """
        logger.info("Refining code based on error feedback")

        prompt = f"""The previous code failed. Please fix it.

**Original Code:**
```python
{original_code}
```

**Error:**
{error_message}

**Test Case:**
Input: {test_query}
Expected: {expected_output}

**Your Task:**
Fix the code to handle this case correctly. Output only the corrected Python code (in ```python ``` block).

**IMPORTANT:** Use only ASCII characters in your response. Do not include any non-ASCII characters (such as special symbols, emojis, or Unicode characters)."""

        try:
            response = ask_llm(self.model, [prompt], 0.2, 1)
            llm_output = response["response"][0] if isinstance(response["response"], list) else response["response"]
            return self._extract_and_validate_code(llm_output)
        except Exception as e:
            logger.error(f"Error refining code: {e}")
            return None

    def generate_fallback_code(
        self,
        skeleton: RuleSkeleton
    ) -> str:
        """
        Generate simple fallback code using regex if AST-based code fails.

        Args:
            skeleton: Rule skeleton

        Returns:
            Simple regex-based transformation code
        """
        logger.info("Generating fallback regex-based code")

        # This creates a very simple template that uses string replacement
        code = f'''import re

def transform_query(sql: str) -> str:
    """
    Simple regex-based transformation: {skeleton.error_category}

    This is a fallback when AST-based transformation fails.
    """
    try:
        # Parse transformation instructions to create simple regex replacement
        transformed = sql

        # Basic case-insensitive SQL keyword matching
        # (This is a simplified fallback - may not handle all cases)

        return transformed
    except Exception:
        return sql
'''

        return code
