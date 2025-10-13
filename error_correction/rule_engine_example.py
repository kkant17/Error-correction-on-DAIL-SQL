"""
Rule Engine Example Usage for Error Correction Pipeline

This script demonstrates how to use the RuleEngine to apply SQL correction rules.
"""

import os
import json
from error_correction import RuleEngine, ErrorCorrectionConfig


def main():
    """Demonstrate RuleEngine usage"""
    
    print("=== Rule Engine Example Usage ===\n")
    
    # Initialize configuration and rule engine
    config = ErrorCorrectionConfig()
    rule_engine = RuleEngine(config)
    
    # Example 1: Add some correction rules
    print("1. Adding correction rules...")
    
    rules_to_add = [
        {
            "rule_id": "fix_where_typo",
            "description": "Fix 'WERE' typo to 'WHERE'",
            "pattern": r"\bWERE\b",
            "correction": "WHERE",
            "confidence_score": 0.9,
            "rule_type": "syntax",
            "conditions": {
                "query_type": "SELECT",
                "contains_keywords": ["SELECT"]
            }
        },
        {
            "rule_id": "fix_from_typo",
            "description": "Fix 'FORM' typo to 'FROM'",
            "pattern": r"\bFORM\b",
            "correction": "FROM",
            "confidence_score": 0.9,
            "rule_type": "syntax",
            "conditions": {
                "query_type": "SELECT"
            }
        },
        {
            "rule_id": "add_missing_where",
            "description": "Add WHERE clause for UPDATE statements without WHERE",
            "pattern": r"(UPDATE\s+\w+\s+SET\s+[^W]+)(?=\s*;?\s*$)",
            "correction": r"\1 WHERE 1=0",  # Safe default
            "confidence_score": 0.7,
            "rule_type": "semantic",
            "conditions": {
                "query_type": "UPDATE",
                "excludes_keywords": ["WHERE"]
            }
        },
        {
            "rule_id": "fix_select_typo",
            "description": "Fix 'SELCT' typo to 'SELECT'",
            "pattern": r"\bSELCT\b",
            "correction": "SELECT",
            "confidence_score": 0.95,
            "rule_type": "syntax"
        }
    ]
    
    for rule_def in rules_to_add:
        rule_id = rule_engine.add_rule(rule_def)
        if rule_id:
            print(f"   Added rule: {rule_id}")
        else:
            print(f"   Failed to add rule: {rule_def['rule_id']}")
    
    # Example 2: Test queries with errors
    print("\n2. Testing queries with errors...")
    
    test_queries = [
        "SELCT * FROM users WERE age > 25",
        "SELECT * FORM users WHERE age > 25",
        "UPDATE users SET name = 'John'",
        "SELCT name, age FROM users WERE age > 30",
        "SELECT * FROM users WHERE age > 25"  # This one is correct
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n   Test Query {i}: {query}")
        
        # Apply rules
        result = rule_engine.apply_rules(query)
        
        print(f"   Valid: {result.is_valid}")
        print(f"   Applied Rules: {len(result.applied_rules)}")
        print(f"   Confidence: {result.confidence_score:.2f}")
        
        if result.applied_rules:
            print("   Rules Applied:")
            for rule in result.applied_rules:
                print(f"     - {rule.description} (confidence: {rule.confidence_score})")
        
        if result.corrected_sql:
            print(f"   Corrected SQL: {result.corrected_sql}")
        
        if result.errors:
            print("   Errors:")
            for error in result.errors:
                print(f"     - {error}")
        
        if result.warnings:
            print("   Warnings:")
            for warning in result.warnings:
                print(f"     - {warning}")
    
    # Example 3: Get all rules
    print("\n3. Getting all rules...")
    all_rules = rule_engine.get_all_rules()
    print(f"   Total rules: {len(all_rules)}")
    
    for rule in all_rules:
        print(f"   - {rule['rule_id']}: {rule['description']} (confidence: {rule['confidence_score']})")
    
    # Example 4: Rule statistics
    print("\n4. Rule statistics...")
    stats = rule_engine.get_rule_statistics()
    print(f"   Total rules: {stats['total_rules']}")
    print(f"   Rules by type: {stats['rules_by_type']}")
    print(f"   Average confidence: {stats['average_confidence']:.2f}")
    print(f"   Total usage: {stats['total_usage']}")
    print(f"   Success rate: {stats['success_rate']:.2f}")
    
    # Example 5: Validate a specific rule
    print("\n5. Validating a specific rule...")
    if all_rules:
        rule_to_test = all_rules[0]
        test_query = "SELCT * FROM users"
        
        # Get the rule object
        rule_obj = rule_engine.get_rule_by_id(rule_to_test['rule_id'])
        if rule_obj:
            is_valid = rule_engine.validate_rule(rule_obj, test_query)
            print(f"   Rule {rule_to_test['rule_id']} validation: {'PASSED' if is_valid else 'FAILED'}")
    
    # Example 6: Export rules
    print("\n6. Exporting rules...")
    export_file = "error_correction/data/exported_rules.json"
    rule_engine.export_rules(export_file)
    print(f"   Rules exported to: {export_file}")
    
    # Example 7: Create a sample rule file
    print("\n7. Creating sample rule files...")
    
    # Create individual rule files
    sample_rules = [
        {
            "rule_id": "fix_common_typos",
            "description": "Fix common SQL typos",
            "pattern": r"\b(UPDTE|DELTE|INSRT)\b",
            "correction": lambda m: {"UPDTE": "UPDATE", "DELTE": "DELETE", "INSRT": "INSERT"}.get(m.group(1), m.group(1)),
            "confidence_score": 0.8,
            "rule_type": "syntax"
        }
    ]
    
    for rule_def in sample_rules:
        rule_file = os.path.join(config.RULES_DIR, f"{rule_def['rule_id']}.json")
        with open(rule_file, 'w') as f:
            json.dump(rule_def, f, indent=2)
        print(f"   Created rule file: {rule_file}")
    
    print("\n=== Rule Engine example completed! ===")


if __name__ == "__main__":
    main()
