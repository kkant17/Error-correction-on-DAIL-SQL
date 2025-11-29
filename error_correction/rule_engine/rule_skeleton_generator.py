"""
Rule Skeleton Generator - LLM-based natural language rule generation

This module generates natural language "skeleton" rules from query pairs and explanations.
The skeleton describes WHAT to do before we synthesize HOW to do it in code.
"""
import json
import re
import logging
from typing import Optional, List
from llm.chatgpt import ask_llm
from error_correction.rule_engine.rule_schema import RuleSkeleton

logger = logging.getLogger(__name__)

# Suggested error categories (LLM can choose or create new ones)
DEFAULT_ERROR_CATEGORIES = [
    "DISTINCT_ERROR",
    "JOIN_ERROR",
    "AGGREGATION_ERROR",
    "FILTER_ERROR",
    "COLUMN_SELECTION",
    "ORDERING_ERROR",
    "SUBQUERY_ERROR",
    "NULL_HANDLING",
    "OPERATOR_ERROR",
    "TABLE_REFERENCE",
    "GROUPING_ERROR",
    "HAVING_ERROR",
    "LIMIT_ERROR",
    "UNION_ERROR",
    "OTHER"
]


class RuleSkeletonGenerator:
    """
    Generates natural language rule skeletons using LLM.

    The skeleton represents an intermediate form between explanation and executable code:
    - Error category (dynamic, can be new or from suggestions)
    - Match description (what patterns to look for)
    - Transformation instructions (step-by-step in natural language)
    - Expected behavior (what should happen after transformation)
    """

    def __init__(
        self,
        model: str = "gpt-4",
        temperature: float = 0.3,
        suggested_categories: List[str] = None
    ):
        """
        Initialize the skeleton generator.

        Args:
            model: LLM model to use
            temperature: Temperature for generation (lower = more focused)
            suggested_categories: List of suggested error categories
        """
        self.model = model
        self.temperature = temperature
        self.suggested_categories = suggested_categories or DEFAULT_ERROR_CATEGORIES

        logger.info(f"RuleSkeletonGenerator initialized with model={model}")

    def generate_skeleton(
        self,
        incorrect_query: str,
        correct_query: str = None,
        explanation: str = "",
        db_id: str = "",
        question: str = ""
    ) -> Optional[RuleSkeleton]:
        """
        Generate a rule skeleton from incorrect query and explanation.

        Args:
            incorrect_query: The incorrect SQL query
            correct_query: The correct SQL query (OPTIONAL - not used in skeleton generation)
            explanation: LLM-generated explanation of the error
            db_id: Database identifier (optional context)
            question: Natural language question (optional context)

        Returns:
            RuleSkeleton object or None if generation failed
        """
        logger.info("Generating rule skeleton")

        try:
            # Build the prompt (note: correct_query is ignored)
            prompt = self._build_skeleton_prompt(
                incorrect_query, explanation, db_id, question
            )

            # Call LLM (correct signature: model, batch, temperature, n)
            response = ask_llm(
                self.model,
                [prompt],
                self.temperature,
                1
            )
            # Extract the response text
            llm_output = response["response"][0] if isinstance(response["response"], list) else response["response"]

            # Parse response
            skeleton = self._parse_skeleton_response(llm_output)

            if skeleton:
                logger.info(f"Generated skeleton with category: {skeleton.error_category}")
            else:
                logger.warning("Failed to parse skeleton from LLM response")

            return skeleton

        except Exception as e:
            logger.error(f"Error generating skeleton: {e}")
            return None

    def _build_skeleton_prompt(
        self,
        incorrect_query: str,
        explanation: str,
        db_id: str,
        question: str
    ) -> str:
        """
        Build the prompt for skeleton generation.

        Args:
            incorrect_query: Incorrect SQL query
            explanation: Error explanation
            db_id: Database ID
            question: Natural language question

        Returns:
            Formatted prompt string
        """
        # Format suggested categories as a readable list
        categories_list = "\n".join([f"  - {cat}" for cat in self.suggested_categories])

        prompt = f"""You are an expert SQL analyst. Your task is to create a natural language "rule skeleton" that describes how to correct a specific SQL error.

**Context:**
Database: {db_id if db_id else "N/A"}
Question: {question if question else "N/A"}

**Error Analysis:**
Incorrect Query:
{incorrect_query}

Explanation of Error:
{explanation}

**Your Task:**
Create a rule skeleton with the following components:

1. **Error Category**: Choose the most appropriate category from the suggestions below, OR create a NEW category if none fit well:
{categories_list}

2. **Match Description**: Describe in natural language what query patterns this error applies to. Be specific about SQL structure, keywords, and conditions that identify this error.

3. **Transformation Instructions**: Provide step-by-step natural language instructions for how to transform the incorrect query into a correct one based on the error explanation. Be clear and specific.

4. **Expected Behavior**: Describe what the corrected query should accomplish based on the natural language question.

5. **Example Transformation**: Provide a concise before/after example showing the transformation pattern (use generic placeholders if needed).

6. **Confidence**: Rate your confidence in this skeleton (0.0 to 1.0).

**Output Format (JSON only, no additional text):**
{{
  "error_category": "<category name - can be from suggestions or NEW>",
  "match_description": "<natural language description of what queries this applies to>",
  "transformation_instructions": "<step-by-step natural language transformation guide>",
  "expected_behavior": "<description of what corrected query should do>",
  "example_transformation": "<before: ... → after: ...>",
  "confidence": <float between 0.0 and 1.0>
}}

**Important Guidelines:**
- Be specific and actionable in your instructions
- Use natural language (no code yet!)
- If creating a new category, make it descriptive and unique
- Focus on the WHAT, not the HOW (code comes later)
- Keep instructions clear enough that a developer could implement them
- You do NOT have access to the correct query - infer the correction from the question and explanation
- Use only ASCII characters in your response. Do not include any non-ASCII characters (such as special symbols, emojis, or Unicode characters)

Generate the JSON skeleton now:"""

        return prompt

    def _parse_skeleton_response(self, response: str) -> Optional[RuleSkeleton]:
        """
        Parse LLM response into a RuleSkeleton object.

        Args:
            response: Raw LLM response string

        Returns:
            RuleSkeleton or None if parsing failed
        """
        try:
            # Try to extract JSON from response (LLM might add extra text)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                logger.error("No JSON found in LLM response")
                return None

            json_str = json_match.group(0)
            data = json.loads(json_str)

            # Validate required fields
            required_fields = [
                'error_category',
                'match_description',
                'transformation_instructions',
                'expected_behavior',
                'example_transformation'
            ]

            for field in required_fields:
                if field not in data or not data[field]:
                    logger.error(f"Missing required field: {field}")
                    return None

            # Create skeleton
            skeleton = RuleSkeleton(
                error_category=data['error_category'].strip(),
                match_description=data['match_description'].strip(),
                transformation_instructions=data['transformation_instructions'].strip(),
                expected_behavior=data['expected_behavior'].strip(),
                example_transformation=data['example_transformation'].strip(),
                suggested_categories=self.suggested_categories,
                confidence=float(data.get('confidence', 0.8))
            )

            # Log if LLM created a new category
            if skeleton.error_category not in self.suggested_categories:
                logger.info(
                    f"LLM created new error category: '{skeleton.error_category}' "
                    f"(not in suggested list)"
                )

            return skeleton

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            logger.debug(f"Response was: {response}")
            return None
        except Exception as e:
            logger.error(f"Error parsing skeleton: {e}")
            return None

    def batch_generate_skeletons(
        self,
        query_pairs: List[dict]
    ) -> List[Optional[RuleSkeleton]]:
        """
        Generate skeletons for multiple query pairs.

        Args:
            query_pairs: List of dicts with keys:
                - incorrect_query
                - correct_query
                - explanation
                - db_id (optional)
                - question (optional)

        Returns:
            List of RuleSkeleton objects (None for failed generations)
        """
        skeletons = []

        for i, pair in enumerate(query_pairs):
            logger.info(f"Generating skeleton {i+1}/{len(query_pairs)}")

            skeleton = self.generate_skeleton(
                incorrect_query=pair['incorrect_query'],
                correct_query=pair['correct_query'],
                explanation=pair['explanation'],
                db_id=pair.get('db_id', ''),
                question=pair.get('question', '')
            )

            skeletons.append(skeleton)

        success_count = sum(1 for s in skeletons if s is not None)
        logger.info(
            f"Batch generation complete: {success_count}/{len(query_pairs)} successful"
        )

        return skeletons

    def regenerate_skeleton(
        self,
        previous_skeleton: RuleSkeleton,
        feedback: str
    ) -> Optional[RuleSkeleton]:
        """
        Regenerate a skeleton based on feedback (e.g., if validation failed).

        Args:
            previous_skeleton: The previous skeleton that failed
            feedback: Feedback on why it failed

        Returns:
            New RuleSkeleton or None
        """
        logger.info("Regenerating skeleton based on feedback")

        prompt = f"""The previous rule skeleton did not work correctly. Please create an improved version.

**Previous Skeleton:**
Error Category: {previous_skeleton.error_category}
Match Description: {previous_skeleton.match_description}
Transformation Instructions: {previous_skeleton.transformation_instructions}
Expected Behavior: {previous_skeleton.expected_behavior}

**Feedback/Problem:**
{feedback}

**Your Task:**
Create an IMPROVED skeleton that addresses the feedback. Use the same JSON format as before:
{{
  "error_category": "<category>",
  "match_description": "<description>",
  "transformation_instructions": "<instructions>",
  "expected_behavior": "<behavior>",
  "example_transformation": "<example>",
  "confidence": <0.0-1.0>
}}

**IMPORTANT:** Use only ASCII characters in your response. Do not include any non-ASCII characters (such as special symbols, emojis, or Unicode characters).

Generate the improved skeleton:"""

        try:
            response = ask_llm(self.model, [prompt], self.temperature, 1)
            llm_output = response["response"][0] if isinstance(response["response"], list) else response["response"]
            return self._parse_skeleton_response(llm_output)
        except Exception as e:
            logger.error(f"Error regenerating skeleton: {e}")
            return None
