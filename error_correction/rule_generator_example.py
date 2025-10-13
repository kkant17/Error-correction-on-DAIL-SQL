"""
Rule Generator Example Usage for Error Correction Pipeline

This script demonstrates how to use the RuleGenerator to create formal rules from explanations.
"""

import os
from error_correction import RuleGenerator, ErrorCorrectionConfig, ErrorInfo, Explanation


def main():
    """Demonstrate RuleGenerator usage"""
    
    print("=== Rule Generator Example Usage ===\n")
    
    # Initialize configuration and rule generator
    config = ErrorCorrectionConfig()
    
    # Set up API key (you can also set OPENAI_API_KEY environment variable)
    api_key = os.getenv('OPENAI_API_KEY', 'your-api-key-here')
    
    try:
        rule_generator = RuleGenerator(config, api_key)
        print(f"Initialized Rule Generator with model: {config.LLM_MODEL}")
    except ValueError as e:
        print(f"Error initializing rule generator: {e}")
        print("Please set OPENAI_API_KEY environment variable or update the api_key in this script")
        return
    
    # Example 1: Generate rule from explanation for syntax error
    print("\n1. Generating rule from syntax error explanation...")
    
    # Create explanation for a syntax error
    error_info = ErrorInfo(
        error_message="Syntax error: 'SELCT' is not a valid SQL keyword",
        error_type="syntax_error",
        error_code="SQL_SYNTAX_ERROR",
        severity="high"
    )
    
    explanation = Explanation(
        explanation_id="exp_001",
        nl_query="Find all users with age greater than 25",
        sql_query="SELCT * FROM users WHERE age > 25",
        error_info=error_info,
        root_cause="The SQL query contains a typo in the SELECT keyword",
        violated_pattern="SELCT instead of SELECT",
        correct_pattern="SELECT * FROM users WHERE age > 25",
        general_rule="Always use correct SQL keywords: SELECT, FROM, WHERE, etc.",
        confidence=0.95,
        metadata={'model': 'gpt-4'}
    )
    
    wrong_query = "SELCT * FROM users WHERE age > 25"
    nl_query = "Find all users with age greater than 25"
    
    try:
        result = rule_generator.generate_rule_from_explanation(explanation, wrong_query, nl_query)
        if result:
            print("   Rule Generation Result:")
            print(f"   - Rule ID: {result['generated_rule']['rule_id']}")
            print(f"   - Rule Type: {result['generated_rule']['rule_type']}")
            print(f"   - Pattern: {result['generated_rule']['pattern']}")
            print(f"   - Replacement: {result['generated_rule']['replacement']}")
            print(f"   - Description: {result['generated_rule']['description']}")
            print(f"   - Confidence: {result['generated_rule']['confidence']}")
            print(f"   - Validation Passed: {result['generated_rule']['validation_passed']}")
            print(f"   - Catches Error: {result['validation_result']['catches_error']}")
            print(f"   - Corrected Query: {result['validation_result']['corrected_query']}")
        else:
            print("   Failed to generate rule")
    except Exception as e:
        print(f"   Error generating rule: {e}")
    
    # Example 2: Generate rule from semantic error explanation
    print("\n2. Generating rule from semantic error explanation...")
    
    error_info2 = ErrorInfo(
        error_message="Column 'status' must appear in GROUP BY clause",
        error_type="semantic_error",
        error_code="SQL_GROUP_BY_ERROR",
        severity="medium"
    )
    
    explanation2 = Explanation(
        explanation_id="exp_002",
        nl_query="Get the count of orders by status",
        sql_query="SELECT status, COUNT(*) FROM orders GROUP BY status HAVING COUNT(*) > 1",
        error_info=error_info2,
        root_cause="The query uses HAVING without proper GROUP BY clause",
        violated_pattern="HAVING without proper GROUP BY",
        correct_pattern="SELECT status, COUNT(*) FROM orders GROUP BY status HAVING COUNT(*) > 1",
        general_rule="When using HAVING, ensure all non-aggregated columns are in GROUP BY",
        confidence=0.85,
        metadata={'model': 'gpt-4'}
    )
    
    wrong_query2 = "SELECT status, COUNT(*) FROM orders HAVING COUNT(*) > 1"
    nl_query2 = "Get the count of orders by status"
    
    try:
        result2 = rule_generator.generate_rule_from_explanation(explanation2, wrong_query2, nl_query2)
        if result2:
            print("   Rule Generation Result:")
            print(f"   - Rule ID: {result2['generated_rule']['rule_id']}")
            print(f"   - Rule Type: {result2['generated_rule']['rule_type']}")
            print(f"   - Pattern: {result2['generated_rule']['pattern']}")
            print(f"   - Replacement: {result2['generated_rule']['replacement']}")
            print(f"   - Validation Passed: {result2['generated_rule']['validation_passed']}")
            print(f"   - Catches Error: {result2['validation_result']['catches_error']}")
        else:
            print("   Failed to generate rule")
    except Exception as e:
        print(f"   Error generating rule: {e}")
    
    # Example 3: Test rule validation
    print("\n3. Testing rule validation...")
    
    # Create a test rule
    test_rule = {
        'rule_id': 'test_rule_001',
        'rule_type': 'syntax',
        'pattern': r'\bSELCT\b',
        'replacement': 'SELECT',
        'description': 'Fix SELCT typo to SELECT',
        'confidence': 0.9,
        'conditions': {
            'query_type': 'SELECT',
            'contains_keywords': ['SELECT', 'FROM']
        }
    }
    
    test_query = "SELCT * FROM users WHERE age > 25"
    
    try:
        validation_result = rule_generator.validate_rule_on_query(test_rule, test_query)
        print(f"   Validation Result:")
        print(f"   - Catches Error: {validation_result.catches_error}")
        print(f"   - Corrected Query: {validation_result.corrected_query}")
        print(f"   - Validation Passed: {validation_result.validation_passed}")
        print(f"   - Confidence Score: {validation_result.confidence_score}")
        if validation_result.error_message:
            print(f"   - Error Message: {validation_result.error_message}")
    except Exception as e:
        print(f"   Error in validation: {e}")
    
    # Example 4: Parse rule to executable format
    print("\n4. Parsing rule to executable format...")
    
    rule_definition = {
        'rule_type': 'syntax',
        'pattern': r'\bWERE\b',
        'replacement': 'WHERE',
        'description': 'Fix WERE typo to WHERE',
        'confidence': 0.95,
        'conditions': {
            'query_type': 'SELECT',
            'contains_keywords': ['SELECT']
        },
        'examples': {
            'wrong': 'SELECT * FROM users WERE age > 25',
            'correct': 'SELECT * FROM users WHERE age > 25'
        }
    }
    
    try:
        executable_rule = rule_generator.parse_rule_to_executable(rule_definition)
        if executable_rule:
            print("   Executable Rule:")
            print(f"   - Rule ID: {executable_rule['rule_id']}")
            print(f"   - Pattern: {executable_rule['pattern']}")
            print(f"   - Replacement: {executable_rule['replacement']}")
            print(f"   - Conditions: {executable_rule['conditions']}")
        else:
            print("   Failed to parse rule to executable format")
    except Exception as e:
        print(f"   Error parsing rule: {e}")
    
    # Example 5: Batch rule generation
    print("\n5. Batch rule generation...")
    
    explanation_data = [
        (explanation, wrong_query, nl_query),
        (explanation2, wrong_query2, nl_query2)
    ]
    
    try:
        batch_results = rule_generator.batch_generate_rules(explanation_data)
        print(f"   Generated {len(batch_results)} rules from {len(explanation_data)} explanations")
        
        for i, result in enumerate(batch_results, 1):
            if 'error' in result:
                print(f"   Rule {i}: Error - {result['error']}")
            else:
                print(f"   Rule {i}: {result['generated_rule']['rule_id']} - Validation: {result['generated_rule']['validation_passed']}")
    except Exception as e:
        print(f"   Error in batch generation: {e}")
    
    # Example 6: Get rule statistics
    print("\n6. Getting rule statistics...")
    
    stats = rule_generator.get_rule_statistics()
    print(f"   Total Rules: {stats['total_rules']}")
    print(f"   Rules by Type: {stats['rules_by_type']}")
    print(f"   Average Confidence: {stats['average_confidence']:.2f}")
    print(f"   Validated Rules: {stats['validated_rules']}")
    print(f"   Validation Success Rate: {stats['validation_success_rate']:.2f}")
    
    # Example 7: Get rules by type
    print("\n7. Getting rules by type...")
    
    syntax_rules = rule_generator.get_rules_by_type('syntax')
    semantic_rules = rule_generator.get_rules_by_type('semantic')
    
    print(f"   Syntax Rules: {len(syntax_rules)}")
    print(f"   Semantic Rules: {len(semantic_rules)}")
    
    # Example 8: Get validated rules
    print("\n8. Getting validated rules...")
    
    validated_rules = rule_generator.get_validated_rules()
    print(f"   Validated Rules: {len(validated_rules)}")
    
    for rule in validated_rules:
        print(f"   - {rule.rule_id}: {rule.description} (confidence: {rule.confidence})")
    
    # Example 9: Export rules
    print("\n9. Exporting rules...")
    
    export_file = "error_correction/data/exported_generated_rules.json"
    try:
        rule_generator.export_generated_rules(export_file)
        print(f"   Rules exported to: {export_file}")
    except Exception as e:
        print(f"   Error exporting rules: {e}")
    
    print("\n=== Rule Generator example completed! ===")


def demonstrate_rule_structure():
    """Demonstrate the expected rule structure"""
    print("\n=== Expected Rule Structure ===")
    
    example_rule = {
        "rule_type": "syntax",
        "pattern": r"\bSELCT\b",
        "replacement": "SELECT",
        "description": "Fix SELCT typo to SELECT",
        "confidence": 0.95,
        "conditions": {
            "min_length": 10,
            "max_length": 1000,
            "contains_keywords": ["SELECT", "FROM"],
            "excludes_keywords": ["INSERT", "UPDATE"],
            "query_type": "SELECT"
        },
        "examples": {
            "wrong": "SELCT * FROM users WHERE age > 25",
            "correct": "SELECT * FROM users WHERE age > 25"
        }
    }
    
    print("Example rule structure:")
    import json
    print(json.dumps(example_rule, indent=2))
    
    print("\nRule validation process:")
    print("1. Check rule conditions (query type, length, keywords)")
    print("2. Test pattern matching on the query")
    print("3. Apply replacement pattern")
    print("4. Validate corrected query syntax")
    print("5. Return validation result with confidence score")


if __name__ == "__main__":
    main()
    demonstrate_rule_structure()
