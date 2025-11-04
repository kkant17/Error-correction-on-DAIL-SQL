"""
LLM-based Rule Generator for SQL Error Correction
"""
import json
import re
import logging
from typing import Dict, List, Optional

from llm.chatgpt import ask_llm
from error_correction.config import (
    EXPLANATION_PROMPT_TEMPLATE,
    RULE_GENERATION_PROMPT_TEMPLATE,
    ERROR_CLASSES
)
from error_correction.rule_engine.rule_schema import Rule

logger = logging.getLogger(__name__)


class RuleGenerator:
    """
    Generates error explanations and correction rules using LLM.
    """

    def __init__(self, model: str = "gpt-4", temperature: float = 0.3):
        """
        Initialize the rule generator.

        Args:
            model: LLM model to use for generation
            temperature: Temperature for LLM generation
        """
        self.model = model
        self.temperature = temperature
        logger.info(f"RuleGenerator initialized with model={model}, temperature={temperature}")

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
        # Build prompt
        prompt = EXPLANATION_PROMPT_TEMPLATE.format(
            db_id=db_id,
            question=question,
            gold_sql=gold_sql,
            predicted_sql=predicted_sql
        )

        try:
            # Call LLM
            response = ask_llm(
                model_name=self.model,
                prompts=[prompt],
                temperature=self.temperature,
                n=1
            )

            explanation = response["response"][0].strip()
            logger.debug(f"Generated explanation: {explanation[:100]}...")
            return explanation

        except Exception as e:
            logger.error(f"Error generating explanation: {e}")
            return f"Failed to generate explanation: {str(e)}"

    def generate_rules(
        self,
        incorrect_query: str,
        correct_query: str,
        explanation: str
    ) -> List[Rule]:
        """
        Generate correction rules based on explanation.

        Args:
            incorrect_query: The incorrect SQL query
            correct_query: The correct SQL query
            explanation: Explanation of the error

        Returns:
            List of generated rules (can be multiple)
        """
        # Build prompt
        prompt = RULE_GENERATION_PROMPT_TEMPLATE.format(
            incorrect_query=incorrect_query,
            correct_query=correct_query,
            explanation=explanation,
            error_classes=", ".join(ERROR_CLASSES)
        )

        try:
            # Call LLM
            response = ask_llm(
                model_name=self.model,
                prompts=[prompt],
                temperature=self.temperature,
                n=1
            )

            llm_output = response["response"][0].strip()
            logger.debug(f"LLM rule generation output: {llm_output}")

            # Parse the JSON output
            rules = self._parse_rule_output(llm_output)
            logger.info(f"Generated {len(rules)} rule(s)")
            return rules

        except Exception as e:
            logger.error(f"Error generating rules: {e}")
            return []

    def _parse_rule_output(self, llm_output: str) -> List[Rule]:
        """
        Parse LLM output to extract rules.
        Handles both single rule and multiple rules in JSON format.

        Args:
            llm_output: Raw LLM output string

        Returns:
            List of Rule objects
        """
        rules = []

        try:
            # Try to extract JSON from the output
            # Sometimes LLM adds extra text, so we need to extract JSON
            json_match = re.search(r'\{.*\}', llm_output, re.DOTALL)
            if not json_match:
                logger.warning("No JSON found in LLM output")
                return rules

            json_str = json_match.group(0)
            data = json.loads(json_str)

            # Check if it's a single rule or multiple rules
            if isinstance(data, dict):
                # Single rule
                rule = self._create_rule_from_dict(data)
                if rule:
                    rules.append(rule)
            elif isinstance(data, list):
                # Multiple rules
                for rule_data in data:
                    rule = self._create_rule_from_dict(rule_data)
                    if rule:
                        rules.append(rule)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM output: {e}")
            logger.debug(f"Raw output: {llm_output}")
        except Exception as e:
            logger.error(f"Error parsing rule output: {e}")

        return rules

    def _create_rule_from_dict(self, data: Dict) -> Optional[Rule]:
        """
        Create a Rule object from parsed JSON dictionary.

        Args:
            data: Dictionary containing rule fields

        Returns:
            Rule object or None if invalid
        """
        try:
            # Extract required fields
            pattern = data.get('pattern', '')
            correction = data.get('correction', '')

            # Extract error_type from metadata if structured that way,
            # or directly from top-level
            if 'metadata' in data:
                error_type = data['metadata'].get('error_type', 'OTHER')
            else:
                error_type = data.get('error_type', 'OTHER')

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
                logger.warning(f"Invalid regex pattern '{pattern}': {e}")
                return None

            return Rule(
                pattern=pattern,
                correction=correction,
                error_type=error_type
            )

        except Exception as e:
            logger.error(f"Error creating rule from dict: {e}")
            return None
