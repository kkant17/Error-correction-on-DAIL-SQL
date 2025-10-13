"""
RuleTester Example Usage for Error Correction Pipeline

This script demonstrates how to use the RuleTester to validate rules
against correct queries to ensure they don't break working queries.
"""

import os
import logging
from error_correction import RuleTester, RuleEngine, VectorDBManager, ErrorCorrectionConfig, QueryRecord, ErrorInfo


def setup_logging():
    """Setup detailed logging for the rule testing process"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('error_correction/data/rule_testing.log')
        ]
    )


def main():
    """Demonstrate RuleTester usage"""
    
    print("=== RuleTester Example Usage ===\n")
    
    # Setup logging
    setup_logging()
    
    # Initialize configuration and managers
    config = ErrorCorrectionConfig()
    vector_db_manager = VectorDBManager(config)
    rule_engine = RuleEngine(config)
    rule_tester = RuleTester(config, vector_db_manager)
    
    print(f"Initialized RuleTester with X_SAMPLE_SIZE: {config.X_SAMPLE_SIZE}")
    
    # Example 1: Populate vector DB with correct queries
    print("\n1. Populating vector DB with correct queries...")
    
    correct_queries = create_sample_correct_queries()
    for query_data in correct_queries:
        vector_db_manager.store_correct_query(
            nl_query=query_data['nl_query'],
            sql_query=query_data['sql_query'],
            metadata=query_data['metadata']
        )
    
    total_correct = vector_db_manager.get_query_count('correct_queries')
    print(f"   Stored {total_correct} correct queries")
    
    # Example 2: Create test rules
    print("\n2. Creating test rules...")
    
    test_rules = create_test_rules()
    print(f"   Created {len(test_rules)} test rules")
    
    for i, rule in enumerate(test_rules, 1):
        print(f"   Rule {i}: {rule['rule_id']} - {rule['description']}")
    
    # Example 3: Test individual rules
    print("\n3. Testing individual rules...")
    
    for i, rule in enumerate(test_rules, 1):
        print(f"\n   Testing Rule {i}: {rule['rule_id']}")
        
        # Test rule on correct queries
        pass_rate, failed_queries = rule_tester.test_rule_on_correct_queries(rule)
        
        print(f"   - Pass rate: {pass_rate:.3f}")
        print(f"   - Failed queries: {len(failed_queries)}")
        
        if failed_queries:
            print(f"   - First failed query: {failed_queries[0]['query_id']}")
            print(f"     Original: {failed_queries[0]['original_query']}")
            print(f"     Modified: {failed_queries[0]['modified_query']}")
            print(f"     Reason: {failed_queries[0]['reason']}")
        
        # Check if rule is safe
        is_safe = rule_tester.is_rule_safe(rule)
        print(f"   - Is safe: {is_safe}")
    
    # Example 4: Validate rules before adding to engine
    print("\n4. Validating rules before adding to rule engine...")
    
    safe_rules = []
    unsafe_rules = []
    
    for i, rule in enumerate(test_rules, 1):
        print(f"\n   Validating Rule {i}: {rule['rule_id']}")
        
        # Validate rule before adding
        is_valid = rule_tester.validate_rule_before_adding(rule, rule_engine)
        
        if is_valid:
            safe_rules.append(rule)
            print(f"   - ✅ Rule added to engine successfully")
        else:
            unsafe_rules.append(rule)
            print(f"   - ❌ Rule failed validation - not added to engine")
    
    print(f"\n   Validation summary:")
    print(f"   - Safe rules: {len(safe_rules)}")
    print(f"   - Unsafe rules: {len(unsafe_rules)}")
    print(f"   - Total rules in engine: {len(rule_engine.get_all_rules())}")
    
    # Example 5: Batch validation
    print("\n5. Batch validation of rules...")
    
    # Create more test rules for batch validation
    batch_rules = create_batch_test_rules()
    print(f"   Created {len(batch_rules)} rules for batch validation")
    
    # Perform batch validation
    validation_results = rule_tester.batch_validate_rules(batch_rules, rule_engine)
    
    print(f"   Batch validation results:")
    for result in validation_results:
        status = "✅" if result['overall_valid'] else "❌"
        print(f"   - {status} {result['rule_id']}: Safe={result['is_safe']}, Syntax={result['syntax_valid']}, Added={result['added_to_engine']}")
    
    # Example 6: Get safety statistics
    print("\n6. Getting safety statistics...")
    
    stats = rule_tester.get_safety_statistics()
    print(f"   Safety statistics:")
    print(f"   - Total correct queries: {stats['total_correct_queries']}")
    print(f"   - Sample size: {stats['sample_size']}")
    print(f"   - Safety threshold: {stats['safety_threshold']}")
    print(f"   - Can test rules: {stats['can_test_rules']}")
    
    # Example 7: Test edge cases
    print("\n7. Testing edge cases...")
    
    # Test with no correct queries
    print("   Testing with empty vector DB...")
    empty_vector_db = VectorDBManager(config)
    empty_rule_tester = RuleTester(config, empty_vector_db)
    
    test_rule = test_rules[0]
    pass_rate, failed_queries = empty_rule_tester.test_rule_on_correct_queries(test_rule)
    print(f"   - Pass rate with no queries: {pass_rate}")
    
    # Test with very small sample
    print("   Testing with small sample size...")
    pass_rate, failed_queries = rule_tester.test_rule_on_correct_queries(test_rule, sample_size=2)
    print(f"   - Pass rate with sample size 2: {pass_rate}")
    
    # Example 8: Export results
    print("\n8. Exporting rule testing results...")
    
    export_file = "error_correction/data/rule_testing_results.json"
    try:
        import json
        results = {
            'test_rules': test_rules,
            'batch_rules': batch_rules,
            'validation_results': validation_results,
            'safety_statistics': stats
        }
        
        with open(export_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"   Exported results to: {export_file}")
    except Exception as e:
        print(f"   Error exporting results: {e}")
    
    print("\n=== RuleTester example completed! ===")
    print("Check rule_testing.log for detailed testing logs")


def create_sample_correct_queries():
    """Create sample correct queries for testing"""
    queries = []
    
    # Basic SELECT queries
    basic_queries = [
        ("Find all users", "SELECT * FROM users"),
        ("Get user by ID", "SELECT * FROM users WHERE id = 1"),
        ("Count users", "SELECT COUNT(*) FROM users"),
        ("Get users with age", "SELECT name, age FROM users WHERE age > 25"),
        ("Join users and orders", "SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id")
    ]
    
    for i, (nl_query, sql_query) in enumerate(basic_queries):
        queries.append({
            'nl_query': nl_query,
            'sql_query': sql_query,
            'metadata': {'type': 'basic_select', 'index': i}
        })
    
    # Complex queries
    complex_queries = [
        ("Aggregate with GROUP BY", "SELECT department, COUNT(*) FROM employees GROUP BY department"),
        ("Subquery example", "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)"),
        ("Multiple joins", "SELECT u.name, o.total, p.name FROM users u JOIN orders o ON u.id = o.user_id JOIN products p ON o.product_id = p.id"),
        ("Window function", "SELECT name, salary, ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC) FROM employees"),
        ("CTE example", "WITH high_earners AS (SELECT * FROM employees WHERE salary > 50000) SELECT * FROM high_earners")
    ]
    
    for i, (nl_query, sql_query) in enumerate(complex_queries):
        queries.append({
            'nl_query': nl_query,
            'sql_query': sql_query,
            'metadata': {'type': 'complex', 'index': i}
        })
    
    # INSERT/UPDATE/DELETE queries
    dml_queries = [
        ("Insert user", "INSERT INTO users (name, email) VALUES ('John', 'john@example.com')"),
        ("Update user", "UPDATE users SET email = 'newemail@example.com' WHERE id = 1"),
        ("Delete user", "DELETE FROM users WHERE id = 1"),
        ("Insert with subquery", "INSERT INTO orders (user_id, total) SELECT id, 100 FROM users WHERE name = 'John'")
    ]
    
    for i, (nl_query, sql_query) in enumerate(dml_queries):
        queries.append({
            'nl_query': nl_query,
            'sql_query': sql_query,
            'metadata': {'type': 'dml', 'index': i}
        })
    
    return queries


def create_test_rules():
    """Create test rules with different safety profiles"""
    rules = []
    
    # Safe rule - only matches specific error patterns
    safe_rule = {
        'rule_id': 'safe_rule_001',
        'rule_type': 'syntax',
        'pattern': r'\bSELCT\b',
        'replacement': 'SELECT',
        'description': 'Fix SELCT typo to SELECT',
        'confidence': 0.9,
        'conditions': {'query_type': 'SELECT'},
        'created_at': '2024-01-01T10:00:00Z'
    }
    rules.append(safe_rule)
    
    # Unsafe rule - too broad pattern
    unsafe_rule = {
        'rule_id': 'unsafe_rule_001',
        'rule_type': 'syntax',
        'pattern': r'\bFROM\b',
        'replacement': 'FROM',
        'description': 'Replace FROM with FROM (redundant rule)',
        'confidence': 0.5,
        'conditions': {},
        'created_at': '2024-01-01T10:01:00Z'
    }
    rules.append(unsafe_rule)
    
    # Moderately safe rule - specific but might have edge cases
    moderate_rule = {
        'rule_id': 'moderate_rule_001',
        'rule_type': 'semantic',
        'pattern': r'SELECT\s+([^,]+),\s*COUNT\([^)]+\)\s+FROM\s+(\w+)\s+HAVING',
        'replacement': r'SELECT \1, COUNT(*) FROM \2 GROUP BY \1 HAVING',
        'description': 'Add GROUP BY clause for non-aggregated columns',
        'confidence': 0.8,
        'conditions': {'query_type': 'SELECT', 'contains_keywords': ['COUNT', 'HAVING']},
        'created_at': '2024-01-01T10:02:00Z'
    }
    rules.append(moderate_rule)
    
    return rules


def create_batch_test_rules():
    """Create rules for batch testing"""
    rules = []
    
    # Create multiple rules with different patterns
    rule_patterns = [
        (r'\bWERE\b', 'WHERE', 'Fix WERE typo to WHERE'),
        (r'\bTHEN\b', 'THEN', 'Fix THEN typo (redundant)'),
        (r'\bAND\b', 'AND', 'Fix AND typo (redundant)'),
        (r'\bOR\b', 'OR', 'Fix OR typo (redundant)'),
        (r'\bGROUP\s+BY\b', 'GROUP BY', 'Fix GROUP BY spacing'),
    ]
    
    for i, (pattern, replacement, description) in enumerate(rule_patterns):
        rule = {
            'rule_id': f'batch_rule_{i:03d}',
            'rule_type': 'syntax',
            'pattern': pattern,
            'replacement': replacement,
            'description': description,
            'confidence': 0.7,
            'conditions': {'query_type': 'SELECT'},
            'created_at': f'2024-01-01T10:{i:02d}:00Z'
        }
        rules.append(rule)
    
    return rules


def demonstrate_rule_safety_workflow():
    """Demonstrate a complete rule safety workflow"""
    print("\n=== Complete Rule Safety Workflow ===")
    
    config = ErrorCorrectionConfig()
    vector_db_manager = VectorDBManager(config)
    rule_engine = RuleEngine(config)
    rule_tester = RuleTester(config, vector_db_manager)
    
    print("1. Setting up test environment...")
    
    # Add some correct queries
    correct_queries = create_sample_correct_queries()
    for query_data in correct_queries[:5]:  # Use only first 5 for demo
        vector_db_manager.store_correct_query(
            nl_query=query_data['nl_query'],
            sql_query=query_data['sql_query'],
            metadata=query_data['metadata']
        )
    
    print(f"   Added {vector_db_manager.get_query_count('correct_queries')} correct queries")
    
    print("\n2. Testing new rules for safety...")
    
    # Create some new rules
    new_rules = [
        {
            'rule_id': 'new_rule_001',
            'rule_type': 'syntax',
            'pattern': r'\bSELCT\b',
            'replacement': 'SELECT',
            'description': 'Fix SELCT typo',
            'confidence': 0.9,
            'conditions': {'query_type': 'SELECT'},
            'created_at': '2024-01-01T10:00:00Z'
        },
        {
            'rule_id': 'new_rule_002',
            'rule_type': 'syntax',
            'pattern': r'\bSELECT\b',
            'replacement': 'SELECT',
            'description': 'Redundant SELECT rule',
            'confidence': 0.5,
            'conditions': {},
            'created_at': '2024-01-01T10:01:00Z'
        }
    ]
    
    safe_rules = []
    for rule in new_rules:
        print(f"   Testing rule: {rule['rule_id']}")
        
        if rule_tester.is_rule_safe(rule):
            print(f"   ✅ Rule is safe")
            if rule_tester.validate_rule_before_adding(rule, rule_engine):
                safe_rules.append(rule)
                print(f"   ✅ Rule added to engine")
            else:
                print(f"   ❌ Rule failed validation")
        else:
            print(f"   ❌ Rule is unsafe")
    
    print(f"\n3. Workflow completed!")
    print(f"   - Total rules tested: {len(new_rules)}")
    print(f"   - Safe rules: {len(safe_rules)}")
    print(f"   - Rules in engine: {len(rule_engine.get_all_rules())}")
    
    return safe_rules


if __name__ == "__main__":
    main()
    demonstrate_rule_safety_workflow()
