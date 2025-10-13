"""
TripletManager Example Usage for Error Correction Pipeline

This script demonstrates how to use the TripletManager to store and manage
query-explanation-rule triplets in JSON format.
"""

import os
from error_correction import TripletManager, ErrorCorrectionConfig, ErrorInfo, Explanation, GeneratedRule


def main():
    """Demonstrate TripletManager usage"""
    
    print("=== TripletManager Example Usage ===\n")
    
    # Initialize configuration and triplet manager
    config = ErrorCorrectionConfig()
    triplet_manager = TripletManager(config)
    
    print(f"Initialized TripletManager")
    print(f"Current triplet count: {triplet_manager.get_triplet_count()}")
    
    # Example 1: Add a triplet with syntax error
    print("\n1. Adding triplet with syntax error...")
    
    # Create error info
    error_info = ErrorInfo(
        error_message="Syntax error: 'SELCT' is not a valid SQL keyword",
        error_type="syntax_error",
        error_code="SQL_SYNTAX_ERROR",
        severity="high"
    )
    
    # Create explanation
    explanation = Explanation(
        explanation_id="exp_001",
        query_id="query_001",
        query_text="Find all users with age greater than 25",
        error_type="syntax_error",
        explanation_text="The SQL query contains a typo in the SELECT keyword. 'SELCT' should be 'SELECT'.",
        confidence=0.95,
        suggested_fix="Change 'SELCT' to 'SELECT'",
        metadata={'model': 'gpt-4'},
        created_at="2024-01-01T10:00:00Z"
    )
    
    # Create generated rule
    rule = GeneratedRule(
        rule_id="rule_001",
        request_id="req_001",
        explanation_id="exp_001",
        rule_type="syntax",
        pattern=r"\bSELCT\b",
        replacement="SELECT",
        description="Fix SELCT typo to SELECT",
        confidence=0.9,
        conditions={'query_type': 'SELECT'},
        metadata={'model': 'gpt-4'},
        created_at="2024-01-01T10:01:00Z",
        validation_passed=True,
        test_results={'catches_error': True, 'corrected_query': 'SELECT * FROM users WHERE age > 25'}
    )
    
    # Add triplet
    triplet_id = triplet_manager.add_triplet(
        nl_query="Find all users with age greater than 25",
        sql_query="SELCT * FROM users WHERE age > 25",
        explanation=explanation,
        rule=rule,
        database_schema="user_management",
        metadata={'source': 'example', 'priority': 'high'}
    )
    
    print(f"   Added triplet: {triplet_id}")
    print(f"   Current count: {triplet_manager.get_triplet_count()}")
    
    # Example 2: Add a triplet with semantic error
    print("\n2. Adding triplet with semantic error...")
    
    error_info2 = ErrorInfo(
        error_message="Column 'status' must appear in GROUP BY clause",
        error_type="semantic_error",
        error_code="SQL_GROUP_BY_ERROR",
        severity="medium"
    )
    
    explanation2 = Explanation(
        explanation_id="exp_002",
        query_id="query_002",
        query_text="Get the count of orders by status",
        error_type="semantic_error",
        explanation_text="The query uses HAVING without proper GROUP BY clause. All non-aggregated columns must be in GROUP BY.",
        confidence=0.85,
        suggested_fix="Add GROUP BY status clause",
        metadata={'model': 'gpt-4'},
        created_at="2024-01-01T10:05:00Z"
    )
    
    rule2 = GeneratedRule(
        rule_id="rule_002",
        request_id="req_002",
        explanation_id="exp_002",
        rule_type="semantic",
        pattern=r"SELECT\s+([^,]+),\s*COUNT\([^)]+\)\s+FROM\s+(\w+)\s+HAVING",
        replacement=r"SELECT \1, COUNT(*) FROM \2 GROUP BY \1 HAVING",
        description="Add GROUP BY clause for non-aggregated columns",
        confidence=0.8,
        conditions={'query_type': 'SELECT', 'contains_keywords': ['COUNT', 'HAVING']},
        metadata={'model': 'gpt-4'},
        created_at="2024-01-01T10:06:00Z",
        validation_passed=True,
        test_results={'catches_error': True, 'corrected_query': 'SELECT status, COUNT(*) FROM orders GROUP BY status HAVING COUNT(*) > 1'}
    )
    
    triplet_id2 = triplet_manager.add_triplet(
        nl_query="Get the count of orders by status",
        sql_query="SELECT status, COUNT(*) FROM orders HAVING COUNT(*) > 1",
        explanation=explanation2,
        rule=rule2,
        database_schema="ecommerce",
        metadata={'source': 'example', 'priority': 'medium'}
    )
    
    print(f"   Added triplet: {triplet_id2}")
    print(f"   Current count: {triplet_manager.get_triplet_count()}")
    
    # Example 3: Add a triplet without rule
    print("\n3. Adding triplet without rule...")
    
    error_info3 = ErrorInfo(
        error_message="Table 'users' doesn't exist",
        error_type="table_not_found",
        error_code="SQL_TABLE_NOT_FOUND",
        severity="high"
    )
    
    explanation3 = Explanation(
        explanation_id="exp_003",
        query_id="query_003",
        query_text="Get all user information",
        error_type="table_not_found",
        explanation_text="The table 'users' does not exist in the database. Check the table name or create the table.",
        confidence=0.9,
        suggested_fix="Verify table name or create the 'users' table",
        metadata={'model': 'gpt-4'},
        created_at="2024-01-01T10:10:00Z"
    )
    
    triplet_id3 = triplet_manager.add_triplet(
        nl_query="Get all user information",
        sql_query="SELECT * FROM users",
        explanation=explanation3,
        rule=None,  # No rule generated yet
        database_schema="user_management",
        metadata={'source': 'example', 'priority': 'high', 'needs_rule': True}
    )
    
    print(f"   Added triplet: {triplet_id3}")
    print(f"   Current count: {triplet_manager.get_triplet_count()}")
    
    # Example 4: Get all triplets
    print("\n4. Getting all triplets...")
    
    all_triplets = triplet_manager.get_all_triplets()
    print(f"   Total triplets: {len(all_triplets)}")
    
    for i, triplet in enumerate(all_triplets, 1):
        print(f"   Triplet {i}: {triplet['triplet_id']} - {triplet['error_type']} - Has rule: {triplet['rule'] is not None}")
    
    # Example 5: Get triplets by error type
    print("\n5. Getting triplets by error type...")
    
    syntax_triplets = triplet_manager.get_triplets_by_error_type("syntax_error")
    semantic_triplets = triplet_manager.get_triplets_by_error_type("semantic_error")
    table_not_found_triplets = triplet_manager.get_triplets_by_error_type("table_not_found")
    
    print(f"   Syntax error triplets: {len(syntax_triplets)}")
    print(f"   Semantic error triplets: {len(semantic_triplets)}")
    print(f"   Table not found triplets: {len(table_not_found_triplets)}")
    
    # Example 6: Get triplets by database schema
    print("\n6. Getting triplets by database schema...")
    
    user_mgmt_triplets = triplet_manager.get_triplets_by_database_schema("user_management")
    ecommerce_triplets = triplet_manager.get_triplets_by_database_schema("ecommerce")
    
    print(f"   User management triplets: {len(user_mgmt_triplets)}")
    print(f"   E-commerce triplets: {len(ecommerce_triplets)}")
    
    # Example 7: Get specific triplet by ID
    print("\n7. Getting specific triplet by ID...")
    
    specific_triplet = triplet_manager.get_triplet_by_id(triplet_id)
    if specific_triplet:
        print(f"   Found triplet: {specific_triplet['triplet_id']}")
        print(f"   NL Query: {specific_triplet['nl_query']}")
        print(f"   SQL Query: {specific_triplet['sql_query']}")
        print(f"   Error Type: {specific_triplet['error_type']}")
        print(f"   Has Rule: {specific_triplet['rule'] is not None}")
    else:
        print("   Triplet not found")
    
    # Example 8: Get triplet statistics
    print("\n8. Getting triplet statistics...")
    
    stats = triplet_manager.get_triplet_statistics()
    print(f"   Total triplets: {stats['total_triplets']}")
    print(f"   Triplets by error type: {stats['triplets_by_error_type']}")
    print(f"   Triplets by database schema: {stats['triplets_by_database_schema']}")
    print(f"   Triplets with rules: {stats['triplets_with_rules']}")
    print(f"   Triplets without rules: {stats['triplets_without_rules']}")
    print(f"   Rule coverage: {stats['rule_coverage_percentage']:.1f}%")
    
    # Example 9: Save triplets to custom file
    print("\n9. Saving triplets to custom file...")
    
    custom_file = "error_correction/data/custom_triplets.json"
    success = triplet_manager.save_triplets_to_disk(custom_file)
    if success:
        print(f"   Saved triplets to: {custom_file}")
    else:
        print("   Failed to save triplets")
    
    # Example 10: Export triplets to CSV
    print("\n10. Exporting triplets to CSV...")
    
    csv_file = "error_correction/data/triplets_export.csv"
    success = triplet_manager.export_triplets(csv_file, format='csv')
    if success:
        print(f"   Exported triplets to CSV: {csv_file}")
    else:
        print("   Failed to export triplets to CSV")
    
    # Example 11: Load triplets from custom file
    print("\n11. Loading triplets from custom file...")
    
    # Clear current triplets
    triplet_manager.clear_triplets()
    print(f"   Cleared triplets. Current count: {triplet_manager.get_triplet_count()}")
    
    # Load from custom file
    success = triplet_manager.load_triplets_from_disk(custom_file)
    if success:
        print(f"   Loaded triplets from: {custom_file}")
        print(f"   Current count: {triplet_manager.get_triplet_count()}")
    else:
        print("   Failed to load triplets")
    
    # Example 12: Demonstrate triplet structure
    print("\n12. Triplet structure example...")
    
    if triplet_manager.get_triplet_count() > 0:
        example_triplet = triplet_manager.get_all_triplets()[0]
        print("   Example triplet structure:")
        print(f"   - Triplet ID: {example_triplet['triplet_id']}")
        print(f"   - NL Query: {example_triplet['nl_query']}")
        print(f"   - SQL Query: {example_triplet['sql_query']}")
        print(f"   - Error Type: {example_triplet['error_type']}")
        print(f"   - Timestamp: {example_triplet['timestamp']}")
        print(f"   - Database Schema: {example_triplet['database_schema']}")
        print(f"   - Has Rule: {example_triplet['rule'] is not None}")
        print(f"   - Explanation ID: {example_triplet['explanation']['explanation_id']}")
        if example_triplet['rule']:
            print(f"   - Rule ID: {example_triplet['rule']['rule_id']}")
            print(f"   - Rule Pattern: {example_triplet['rule']['pattern']}")
            print(f"   - Rule Replacement: {example_triplet['rule']['replacement']}")
    
    print("\n=== TripletManager example completed! ===")


def demonstrate_triplet_workflow():
    """Demonstrate a complete triplet workflow"""
    print("\n=== Complete Triplet Workflow ===")
    
    config = ErrorCorrectionConfig()
    triplet_manager = TripletManager(config)
    
    print("1. Collecting triplets from error correction pipeline...")
    
    # Simulate collecting triplets
    error_types = ["syntax_error", "semantic_error", "table_not_found", "column_not_found"]
    database_schemas = ["user_management", "ecommerce", "inventory", "analytics"]
    
    for i in range(5):
        error_type = error_types[i % len(error_types)]
        schema = database_schemas[i % len(database_schemas)]
        
        # Create mock explanation
        explanation = Explanation(
            explanation_id=f"exp_{i:03d}",
            query_id=f"query_{i:03d}",
            query_text=f"Sample query {i}",
            error_type=error_type,
            explanation_text=f"Explanation for error {i}",
            confidence=0.8 + (i * 0.05),
            suggested_fix=f"Fix for error {i}",
            metadata={'model': 'gpt-4'},
            created_at=f"2024-01-01T10:{i:02d}:00Z"
        )
        
        # Add triplet
        triplet_id = triplet_manager.add_triplet(
            nl_query=f"Sample natural language query {i}",
            sql_query=f"SELECT * FROM table_{i}",
            explanation=explanation,
            rule=None,  # No rule for now
            database_schema=schema,
            metadata={'batch': 'workflow_demo', 'index': i}
        )
        
        print(f"   Added triplet {i+1}: {triplet_id}")
    
    print(f"\n2. Collected {triplet_manager.get_triplet_count()} triplets")
    
    # Show statistics
    stats = triplet_manager.get_triplet_statistics()
    print(f"   Statistics: {stats}")
    
    print("\n3. Saving triplets for clustering...")
    
    # Save to disk
    triplets_file = "error_correction/data/workflow_triplets.json"
    success = triplet_manager.save_triplets_to_disk(triplets_file)
    if success:
        print(f"   Saved to: {triplets_file}")
    
    print("\n4. After clustering, clearing triplets...")
    
    # Clear triplets (typically done after successful clustering)
    triplet_manager.clear_triplets()
    print(f"   Cleared triplets. Current count: {triplet_manager.get_triplet_count()}")
    
    print("\n=== Workflow completed! ===")


if __name__ == "__main__":
    main()
    demonstrate_triplet_workflow()
