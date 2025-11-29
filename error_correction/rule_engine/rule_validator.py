"""
Rule Validator - Safely executes and validates generated transformation code

This module executes generated Python code in a controlled environment and validates
that it produces the expected output.
"""
import time
import signal
import logging
from typing import Optional, Callable
from contextlib import contextmanager
from error_correction.rule_engine.rule_schema import ValidationResult

logger = logging.getLogger(__name__)


class TimeoutException(Exception):
    """Exception raised when code execution times out."""
    pass


@contextmanager
def time_limit(seconds: int):
    """Context manager to limit execution time."""
    def signal_handler(signum, frame):
        raise TimeoutException(f"Execution timed out after {seconds} seconds")

    # Set the signal handler (Unix-like systems only)
    try:
        signal.signal(signal.SIGALRM, signal_handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
    except AttributeError:
        # Windows doesn't have SIGALRM, use simple timeout
        logger.warning("Timeout not supported on this platform, executing without timeout")
        yield


class RuleValidator:
    """
    Validates generated transformation rules by executing them safely.

    Provides:
    - Safe code execution in restricted namespace
    - Timeout protection
    - Error handling and logging
    - Output validation
    """

    def __init__(
        self,
        execution_timeout: int = 5,
        allow_execution: bool = True
    ):
        """
        Initialize the validator.

        Args:
            execution_timeout: Maximum seconds for code execution
            allow_execution: Whether to actually execute code (safety flag)
        """
        self.execution_timeout = execution_timeout
        self.allow_execution = allow_execution

        if not allow_execution:
            logger.warning("Code execution is DISABLED for safety")

        logger.info(f"RuleValidator initialized with timeout={execution_timeout}s")

    def validate_rule(
        self,
        transform_code: str,
        test_query: str,
        expected_output: str,
        normalize: bool = True
    ) -> ValidationResult:
        """
        Validate a transformation rule by executing it on a test query.

        Args:
            transform_code: Python code containing transform_query function
            test_query: SQL query to transform
            expected_output: Expected result after transformation
            normalize: Whether to normalize queries before comparison

        Returns:
            ValidationResult object with pass/fail status and details
        """
        logger.info("Validating transformation rule")

        if not self.allow_execution:
            return ValidationResult(
                passed=False,
                test_query=test_query,
                expected_output=expected_output,
                actual_output="",
                error_message="Code execution is disabled",
                execution_time_ms=0.0
            )

        start_time = time.time()

        try:
            # Execute code in controlled environment
            actual_output = self._execute_transformation(
                transform_code,
                test_query
            )

            execution_time_ms = (time.time() - start_time) * 1000

            # Normalize queries for comparison if requested
            if normalize:
                expected_norm = self._normalize_sql(expected_output)
                actual_norm = self._normalize_sql(actual_output)
            else:
                expected_norm = expected_output
                actual_norm = actual_output

            # Compare outputs
            passed = (expected_norm == actual_norm)

            if passed:
                logger.info("Validation PASSED")
            else:
                logger.warning(f"Validation FAILED - Expected: {expected_norm}, Got: {actual_norm}")

            return ValidationResult(
                passed=passed,
                test_query=test_query,
                expected_output=expected_output,
                actual_output=actual_output,
                error_message=None if passed else "Output mismatch",
                execution_time_ms=execution_time_ms
            )

        except TimeoutException as e:
            logger.error(f"Validation timed out: {e}")
            return ValidationResult(
                passed=False,
                test_query=test_query,
                expected_output=expected_output,
                actual_output="",
                error_message=f"Execution timeout: {str(e)}",
                execution_time_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return ValidationResult(
                passed=False,
                test_query=test_query,
                expected_output=expected_output,
                actual_output="",
                error_message=f"Execution error: {str(e)}",
                execution_time_ms=(time.time() - start_time) * 1000
            )

    def _execute_transformation(
        self,
        transform_code: str,
        test_query: str
    ) -> str:
        """
        Execute transformation code in a controlled environment.

        Args:
            transform_code: Python code to execute
            test_query: Query to transform

        Returns:
            Transformed query string

        Raises:
            Exception if execution fails
        """
        # Create restricted namespace for execution
        namespace = self._create_safe_namespace()

        try:
            # Use timeout context manager
            with time_limit(self.execution_timeout):
                # Execute the code to define the function
                exec(transform_code, namespace)

                # Get the transform_query function
                if 'transform_query' not in namespace:
                    raise ValueError("transform_query function not found in code")

                transform_func = namespace['transform_query']

                # Call the function
                result = transform_func(test_query)

                # Validate result type
                if not isinstance(result, str):
                    raise TypeError(f"transform_query returned {type(result)}, expected str")

                return result

        except TimeoutException:
            raise
        except Exception as e:
            logger.error(f"Execution error: {e}")
            raise

    def _create_safe_namespace(self) -> dict:
        """
        Create a restricted namespace for code execution.

        Returns:
            Dictionary with safe built-ins and allowed imports
        """
        # Start with minimal builtins
        safe_builtins = {
            '__builtins__': {
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'list': list,
                'dict': dict,
                'tuple': tuple,
                'set': set,
                'len': len,
                'range': range,
                'enumerate': enumerate,
                'zip': zip,
                'map': map,
                'filter': filter,
                'isinstance': isinstance,
                'type': type,
                'Exception': Exception,
                'ValueError': ValueError,
                'TypeError': TypeError,
                'IndexError': IndexError,
                'KeyError': KeyError,
                'AttributeError': AttributeError,
                'True': True,
                'False': False,
                'None': None,
            }
        }

        # Import allowed modules
        try:
            import sqlparse
            safe_builtins['sqlparse'] = sqlparse
        except ImportError:
            logger.warning("sqlparse not available, code execution may fail")

        try:
            import re
            safe_builtins['re'] = re
        except ImportError:
            pass

        return safe_builtins

    def _normalize_sql(self, sql: str) -> str:
        """
        Normalize SQL query for comparison.

        Args:
            sql: SQL query string

        Returns:
            Normalized SQL string
        """
        # Remove extra whitespace
        normalized = ' '.join(sql.split())

        # Strip leading/trailing whitespace
        normalized = normalized.strip()

        # Remove trailing semicolon if present
        if normalized.endswith(';'):
            normalized = normalized[:-1].strip()

        # Convert to lowercase for comparison (optional - can be disabled)
        # normalized = normalized.lower()

        return normalized

    def batch_validate(
        self,
        rules_and_tests: list
    ) -> list:
        """
        Validate multiple rules in batch.

        Args:
            rules_and_tests: List of tuples (transform_code, test_query, expected_output)

        Returns:
            List of ValidationResult objects
        """
        results = []

        for i, (code, query, expected) in enumerate(rules_and_tests):
            logger.info(f"Validating rule {i+1}/{len(rules_and_tests)}")

            result = self.validate_rule(code, query, expected)
            results.append(result)

        # Log summary
        passed_count = sum(1 for r in results if r.passed)
        logger.info(
            f"Batch validation complete: {passed_count}/{len(results)} passed "
            f"({passed_count/len(results)*100:.1f}%)"
        )

        return results

    def get_transformation_function(
        self,
        transform_code: str
    ) -> Optional[Callable]:
        """
        Extract the transformation function from code without executing it on a query.

        Args:
            transform_code: Python code containing transform_query function

        Returns:
            The transform_query function or None if extraction failed
        """
        if not self.allow_execution:
            logger.warning("Code execution disabled, cannot extract function")
            return None

        try:
            namespace = self._create_safe_namespace()
            exec(transform_code, namespace)

            if 'transform_query' not in namespace:
                logger.error("transform_query function not found")
                return None

            return namespace['transform_query']

        except Exception as e:
            logger.error(f"Error extracting function: {e}")
            return None

    def quick_test(
        self,
        transform_code: str,
        test_cases: list
    ) -> dict:
        """
        Quickly test code on multiple test cases.

        Args:
            transform_code: Transformation code
            test_cases: List of (input, expected_output) tuples

        Returns:
            Dictionary with test results and statistics
        """
        results = {
            'passed': 0,
            'failed': 0,
            'errors': 0,
            'details': []
        }

        for input_query, expected in test_cases:
            validation = self.validate_rule(transform_code, input_query, expected)

            if validation.passed:
                results['passed'] += 1
            elif validation.error_message:
                results['errors'] += 1
            else:
                results['failed'] += 1

            results['details'].append({
                'input': input_query,
                'expected': expected,
                'actual': validation.actual_output,
                'passed': validation.passed,
                'error': validation.error_message
            })

        return results
