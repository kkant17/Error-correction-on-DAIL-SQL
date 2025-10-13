"""
LLM Explainer Example Usage for Error Correction Pipeline

This script demonstrates how to use the LLMExplainer to generate explanations for SQL errors.
"""

import os
from error_correction import LLMExplainer, ErrorCorrectionConfig, ErrorInfo


def main():
    """Demonstrate LLMExplainer usage"""
    
    print("=== LLM Explainer Example Usage ===\n")
    
    # Initialize configuration and explainer
    config = ErrorCorrectionConfig()
    
    # Set up API key (you can also set OPENAI_API_KEY environment variable)
    api_key = os.getenv('OPENAI_API_KEY', 'your-api-key-here')
    
    try:
        explainer = LLMExplainer(config, api_key)
        print(f"Initialized LLM Explainer with model: {config.LLM_MODEL}")
        print(f"LLM Type: {explainer.llm_type}")
    except ValueError as e:
        print(f"Error initializing explainer: {e}")
        print("Please set OPENAI_API_KEY environment variable or update the api_key in this script")
        return
    
    # Example 1: Generate explanation for a syntax error
    print("\n1. Generating explanation for syntax error...")
    
    nl_query = "Find all users with age greater than 25"
    sql_query = "SELCT * FROM users WERE age > 25"
    error_info = ErrorInfo(
        error_message="Syntax error: 'SELCT' is not a valid SQL keyword",
        error_type="syntax_error",
        error_code="SQL_SYNTAX_ERROR",
        severity="high"
    )
    
    try:
        explanation = explainer.generate_explanation(nl_query, sql_query, error_info)
        print(f"   Root Cause: {explanation['root_cause']}")
        print(f"   Violated Pattern: {explanation['violated_pattern']}")
        print(f"   Correct Pattern: {explanation['correct_pattern']}")
        print(f"   General Rule: {explanation['general_rule']}")
        print(f"   Confidence: {explanation['confidence']}")
    except Exception as e:
        print(f"   Error generating explanation: {e}")
    
    # Example 2: Generate explanation for a semantic error
    print("\n2. Generating explanation for semantic error...")
    
    nl_query = "Get the count of orders by status"
    sql_query = "SELECT status, COUNT(*) FROM orders GROUP BY status HAVING COUNT(*) > 1"
    error_info = ErrorInfo(
        error_message="Column 'status' must appear in GROUP BY clause",
        error_type="semantic_error",
        error_code="SQL_GROUP_BY_ERROR",
        severity="medium"
    )
    
    try:
        explanation = explainer.generate_explanation(nl_query, sql_query, error_info)
        print(f"   Root Cause: {explanation['root_cause']}")
        print(f"   Violated Pattern: {explanation['violated_pattern']}")
        print(f"   Correct Pattern: {explanation['correct_pattern']}")
        print(f"   General Rule: {explanation['general_rule']}")
        print(f"   Confidence: {explanation['confidence']}")
    except Exception as e:
        print(f"   Error generating explanation: {e}")
    
    # Example 3: Batch explanation generation
    print("\n3. Batch explanation generation...")
    
    query_data = [
        (
            "Find users with age greater than 30",
            "SELECT * FROM users WERE age > 30",
            ErrorInfo(
                error_message="Syntax error: 'WERE' should be 'WHERE'",
                error_type="syntax_error",
                severity="high"
            )
        ),
        (
            "Get all products with price less than 100",
            "SELECT * FORM products WHERE price < 100",
            ErrorInfo(
                error_message="Syntax error: 'FORM' should be 'FROM'",
                error_type="syntax_error",
                severity="high"
            )
        ),
        (
            "Update user email",
            "UPDATE users SET email = 'new@email.com'",
            ErrorInfo(
                error_message="UPDATE statement without WHERE clause",
                error_type="semantic_error",
                severity="critical"
            )
        )
    ]
    
    try:
        explanations = explainer.batch_generate_explanations(query_data)
        print(f"   Generated {len(explanations)} explanations")
        
        for i, explanation in enumerate(explanations, 1):
            print(f"   Explanation {i}:")
            print(f"     Root Cause: {explanation['root_cause']}")
            print(f"     Confidence: {explanation['confidence']}")
    except Exception as e:
        print(f"   Error in batch generation: {e}")
    
    # Example 4: Validate explanation format
    print("\n4. Validating explanation format...")
    
    valid_explanation = {
        'root_cause': 'SQL syntax error',
        'violated_pattern': 'Invalid keyword',
        'correct_pattern': 'Valid SQL keyword',
        'general_rule': 'Use correct SQL syntax',
        'confidence': 0.8
    }
    
    invalid_explanation = {
        'root_cause': 'SQL syntax error',
        'violated_pattern': '',  # Empty field
        'correct_pattern': 'Valid SQL keyword',
        'general_rule': 'Use correct SQL syntax',
        'confidence': 0.8
    }
    
    is_valid1 = explainer.validate_explanation_format(valid_explanation)
    is_valid2 = explainer.validate_explanation_format(invalid_explanation)
    
    print(f"   Valid explanation format: {is_valid1}")
    print(f"   Invalid explanation format: {is_valid2}")
    
    # Example 5: Get explanation statistics
    print("\n5. Getting explanation statistics...")
    
    stats = explainer.get_explanation_statistics()
    print(f"   Total explanations: {stats['total_explanations']}")
    print(f"   Explanations by error type: {stats['explanations_by_error_type']}")
    print(f"   Average confidence: {stats['average_confidence']:.2f}")
    print(f"   High confidence count: {stats['high_confidence_count']}")
    
    # Example 6: Export explanations
    print("\n6. Exporting explanations...")
    
    export_file = "error_correction/data/exported_explanations.json"
    try:
        explainer.export_explanations(export_file)
        print(f"   Explanations exported to: {export_file}")
    except Exception as e:
        print(f"   Error exporting explanations: {e}")
    
    # Example 7: Test with different LLM backends (if available)
    print("\n7. Testing different LLM backends...")
    
    # Test with Ollama (if available)
    try:
        config_ollama = ErrorCorrectionConfig()
        config_ollama.LLM_MODEL = "llama3:8b"
        explainer_ollama = LLMExplainer(config_ollama)
        print(f"   Ollama explainer initialized: {explainer_ollama.llm_type}")
    except Exception as e:
        print(f"   Ollama not available: {e}")
    
    # Test with vLLM (if available)
    try:
        config_vllm = ErrorCorrectionConfig()
        config_vllm.LLM_MODEL = "vllm-model"
        explainer_vllm = LLMExplainer(config_vllm)
        print(f"   vLLM explainer initialized: {explainer_vllm.llm_type}")
    except Exception as e:
        print(f"   vLLM not available: {e}")
    
    print("\n=== LLM Explainer example completed! ===")


def demonstrate_structured_prompt():
    """Demonstrate the structured prompt format"""
    print("\n=== Structured Prompt Format ===")
    
    nl_query = "Find all users with age greater than 25"
    sql_query = "SELCT * FROM users WERE age > 25"
    error_info = ErrorInfo(
        error_message="Syntax error: 'SELCT' is not a valid SQL keyword",
        error_type="syntax_error"
    )
    
    # This is the prompt that would be sent to the LLM
    prompt = f"""Given the natural language query: '{nl_query}'
The generated SQL query: '{sql_query}'
Resulted in error: '{error_info.error_message}'

Analyze why this SQL query is incorrect. Provide:
1. Root cause of the error
2. What SQL pattern was violated
3. The correct SQL pattern that should be used
4. General rule to prevent this error in future queries

Format your response as JSON with keys: 
'root_cause', 'violated_pattern', 'correct_pattern', 'general_rule', 'confidence'

Be specific and technical in your analysis. Focus on SQL syntax, semantics, and best practices."""
    
    print("Example prompt:")
    print(prompt)
    
    print("\nExpected JSON response format:")
    expected_response = {
        "root_cause": "The SQL query contains a typo in the SELECT keyword",
        "violated_pattern": "SELCT instead of SELECT",
        "correct_pattern": "SELECT * FROM users WHERE age > 25",
        "general_rule": "Always use correct SQL keywords: SELECT, FROM, WHERE, etc.",
        "confidence": 0.95
    }
    
    import json
    print(json.dumps(expected_response, indent=2))


if __name__ == "__main__":
    main()
    demonstrate_structured_prompt()
