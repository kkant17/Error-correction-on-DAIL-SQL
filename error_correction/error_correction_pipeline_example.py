"""
ErrorCorrectionPipeline Example Usage

This script demonstrates how to use the ErrorCorrectionPipeline to run
the complete error correction workflow from natural language to corrected SQL.
"""

import os
import logging
from error_correction import ErrorCorrectionPipeline, ErrorCorrectionConfig


def setup_logging():
    """Setup detailed logging for the pipeline"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('error_correction/data/pipeline.log')
        ]
    )


def main():
    """Demonstrate ErrorCorrectionPipeline usage"""
    
    print("=== ErrorCorrectionPipeline Example Usage ===\n")
    
    # Setup logging
    setup_logging()
    
    # Initialize configuration and pipeline
    config = ErrorCorrectionConfig()
    pipeline = ErrorCorrectionPipeline(config)
    
    print(f"Initialized ErrorCorrectionPipeline")
    print(f"Vector backend: {config.VECTOR_BACKEND}")
    print(f"Configuration:")
    print(f"  - MIN_TRIPLET_COUNT: {config.MIN_TRIPLET_COUNT}")
    print(f"  - A_PERCENT_THRESHOLD: {config.A_PERCENT_THRESHOLD}")
    print(f"  - X_SAMPLE_SIZE: {config.X_SAMPLE_SIZE}")
    print(f"  - LLM_MODEL: {config.LLM_MODEL}")
    
    # Example 1: Run pipeline with correct query
    print("\n1. Running pipeline with correct query...")
    
    nl_query1 = "Find all users with age greater than 25"
    ground_truth_sql1 = "SELECT * FROM users WHERE age > 25"
    
    final_sql1, is_correct1 = pipeline.run_pipeline(nl_query1, ground_truth_sql1)
    
    print(f"   Input: {nl_query1}")
    print(f"   Ground truth: {ground_truth_sql1}")
    print(f"   Final SQL: {final_sql1}")
    print(f"   Is correct: {is_correct1}")
    
    # Example 2: Run pipeline with incorrect query
    print("\n2. Running pipeline with incorrect query...")
    
    nl_query2 = "Find all users with age greater than 25"
    ground_truth_sql2 = "SELECT * FROM users WHERE age > 25"
    # Simulate incorrect SQL generation
    pipeline._call_dail_sql = lambda x: "SELCT * FROM users WHERE age > 25"  # Typo in SELECT
    
    final_sql2, is_correct2 = pipeline.run_pipeline(nl_query2, ground_truth_sql2)
    
    print(f"   Input: {nl_query2}")
    print(f"   Ground truth: {ground_truth_sql2}")
    print(f"   Final SQL: {final_sql2}")
    print(f"   Is correct: {is_correct2}")
    
    # Example 3: Run multiple queries to build up triplets
    print("\n3. Running multiple queries to build up triplets...")
    
    test_queries = [
        ("Get all products", "SELECT * FROM products", "SELCT * FROM products"),
        ("Count users by department", "SELECT department, COUNT(*) FROM users GROUP BY department", "SELECT department, COUNT(*) FROM users HAVING COUNT(*) > 1"),
        ("Find orders by user", "SELECT * FROM orders WHERE user_id = 1", "SELCT * FROM orders WHERE user_id = 1"),
        ("Get user details", "SELECT name, email FROM users WHERE id = 1", "SELCT name, email FROM users WHERE id = 1"),
        ("List all categories", "SELECT * FROM categories", "SELCT * FROM categories"),
        ("Count products", "SELECT COUNT(*) FROM products", "SELCT COUNT(*) FROM products"),
        ("Get user orders", "SELECT o.* FROM orders o JOIN users u ON o.user_id = u.id", "SELCT o.* FROM orders o JOIN users u ON o.user_id = u.id"),
        ("Find active users", "SELECT * FROM users WHERE status = 'active'", "SELCT * FROM users WHERE status = 'active'"),
        ("Get product details", "SELECT p.name, p.price FROM products p WHERE p.id = 1", "SELCT p.name, p.price FROM products p WHERE p.id = 1"),
        ("List all orders", "SELECT * FROM orders ORDER BY created_at DESC", "SELCT * FROM orders ORDER BY created_at DESC")
    ]
    
    for i, (nl_query, correct_sql, wrong_sql) in enumerate(test_queries, 1):
        print(f"   Query {i}: {nl_query}")
        
        # Simulate wrong SQL generation
        pipeline._call_dail_sql = lambda x, sql=wrong_sql: sql
        
        final_sql, is_correct = pipeline.run_pipeline(nl_query, correct_sql)
        
        print(f"     Final SQL: {final_sql}")
        print(f"     Is correct: {is_correct}")
        
        # Check triplet count
        triplet_count = pipeline.triplet_manager.get_triplet_count()
        print(f"     Triplet count: {triplet_count}")
        
        if triplet_count >= config.MIN_TRIPLET_COUNT:
            print(f"     ✅ Clustering threshold reached!")
            break
    
    # Example 4: Get pipeline statistics
    print("\n4. Getting pipeline statistics...")
    
    stats = pipeline.get_pipeline_statistics()
    
    print(f"   Vector DB Stats:")
    print(f"     - Correct queries: {stats['vector_db_stats'].get('correct_queries', 0)}")
    print(f"     - Wrong queries: {stats['vector_db_stats'].get('wrong_queries', 0)}")
    
    print(f"   Rule Engine Stats:")
    print(f"     - Total rules: {stats['rule_engine_stats'].get('total_rules', 0)}")
    print(f"     - Rules by type: {stats['rule_engine_stats'].get('rules_by_type', {})}")
    
    print(f"   Triplet Stats:")
    print(f"     - Total triplets: {stats['triplet_stats'].get('total_triplets', 0)}")
    print(f"     - Triplets with rules: {stats['triplet_stats'].get('triplets_with_rules', 0)}")
    print(f"     - Rule coverage: {stats['triplet_stats'].get('rule_coverage_percentage', 0):.1f}%")
    
    # Example 5: Check pipeline health
    print("\n5. Checking pipeline health...")
    
    health = pipeline.get_health_status()
    print(f"   Overall health: {health['overall_health']}")
    
    if health['issues']:
        print(f"   Issues found:")
        for issue in health['issues']:
            print(f"     - {issue}")
    else:
        print(f"   All components healthy")
    
    # Example 6: Export pipeline data
    print("\n6. Exporting pipeline data...")
    
    export_dir = "error_correction/data/pipeline_export"
    pipeline.export_pipeline_data(export_dir)
    print(f"   Exported pipeline data to: {export_dir}")
    
    # Example 7: Demonstrate batch processing
    print("\n7. Demonstrating batch processing...")
    
    batch_queries = [
        ("Get all users", "SELECT * FROM users", "SELCT * FROM users"),
        ("Count products", "SELECT COUNT(*) FROM products", "SELCT COUNT(*) FROM products"),
        ("Find orders", "SELECT * FROM orders", "SELCT * FROM orders")
    ]
    
    results = []
    for nl_query, correct_sql, wrong_sql in batch_queries:
        # Simulate wrong SQL generation
        pipeline._call_dail_sql = lambda x, sql=wrong_sql: sql
        
        final_sql, is_correct = pipeline.run_pipeline(nl_query, correct_sql)
        results.append({
            'nl_query': nl_query,
            'final_sql': final_sql,
            'is_correct': is_correct
        })
    
    print(f"   Batch processing results:")
    for i, result in enumerate(results, 1):
        print(f"     {i}. {result['nl_query']} -> {result['is_correct']}")
    
    print("\n=== ErrorCorrectionPipeline example completed! ===")
    print("Check pipeline.log for detailed execution logs")


def demonstrate_pipeline_workflow():
    """Demonstrate a complete pipeline workflow"""
    print("\n=== Complete Pipeline Workflow ===")
    
    config = ErrorCorrectionConfig()
    pipeline = ErrorCorrectionPipeline(config)
    
    print("1. Initializing pipeline...")
    print(f"   Components initialized: {len(pipeline.__dict__)}")
    
    print("\n2. Processing queries through pipeline...")
    
    # Simulate a series of queries with errors
    queries_with_errors = [
        ("Find all users", "SELECT * FROM users", "SELCT * FROM users"),
        ("Get product count", "SELECT COUNT(*) FROM products", "SELCT COUNT(*) FROM products"),
        ("List orders", "SELECT * FROM orders", "SELCT * FROM orders"),
        ("Find active users", "SELECT * FROM users WHERE status = 'active'", "SELCT * FROM users WHERE status = 'active'"),
        ("Get user details", "SELECT name, email FROM users WHERE id = 1", "SELCT name, email FROM users WHERE id = 1")
    ]
    
    for i, (nl_query, correct_sql, wrong_sql) in enumerate(queries_with_errors, 1):
        print(f"   Processing query {i}: {nl_query}")
        
        # Simulate wrong SQL generation
        pipeline._call_dail_sql = lambda x, sql=wrong_sql: sql
        
        final_sql, is_correct = pipeline.run_pipeline(nl_query, correct_sql)
        
        print(f"     Result: {final_sql} (correct: {is_correct})")
        
        # Check if clustering was triggered
        triplet_count = pipeline.triplet_manager.get_triplet_count()
        if triplet_count >= config.MIN_TRIPLET_COUNT:
            print(f"     ✅ Clustering threshold reached ({triplet_count} triplets)")
            break
    
    print("\n3. Workflow completed!")
    
    # Get final statistics
    stats = pipeline.get_pipeline_statistics()
    print(f"   Final statistics:")
    print(f"     - Correct queries: {stats['vector_db_stats'].get('correct_queries', 0)}")
    print(f"     - Wrong queries: {stats['vector_db_stats'].get('wrong_queries', 0)}")
    print(f"     - Total rules: {stats['rule_engine_stats'].get('total_rules', 0)}")
    print(f"     - Triplets: {stats['triplet_stats'].get('total_triplets', 0)}")
    
    return pipeline


def demonstrate_dail_sql_integration():
    """Demonstrate how to integrate with actual DAIL SQL"""
    print("\n=== DAIL SQL Integration Example ===")
    
    config = ErrorCorrectionConfig()
    pipeline = ErrorCorrectionPipeline(config)
    
    # Override the _call_dail_sql method to show integration
    def mock_dail_sql_call(nl_query: str) -> str:
        """Mock DAIL SQL call - replace with actual DAIL SQL integration"""
        print(f"   Calling DAIL SQL for: {nl_query}")
        
        # This is where you would integrate with the actual DAIL SQL model
        # For example:
        # import dail_sql_model
        # return dail_sql_model.generate_sql(nl_query)
        
        # Mock response for demonstration
        if "users" in nl_query.lower():
            return "SELCT * FROM users WHERE age > 25"  # Intentional typo
        elif "products" in nl_query.lower():
            return "SELCT COUNT(*) FROM products"  # Intentional typo
        else:
            return "SELECT * FROM table WHERE id = 1"
    
    # Replace the method
    pipeline._call_dail_sql = mock_dail_sql_call
    
    print("1. Testing with user query...")
    final_sql1, is_correct1 = pipeline.run_pipeline("Find all users with age greater than 25", "SELECT * FROM users WHERE age > 25")
    print(f"   Result: {final_sql1} (correct: {is_correct1})")
    
    print("\n2. Testing with product query...")
    final_sql2, is_correct2 = pipeline.run_pipeline("Count all products", "SELECT COUNT(*) FROM products")
    print(f"   Result: {final_sql2} (correct: {is_correct2})")
    
    print("\n3. Integration example completed!")
    print("   In production, replace mock_dail_sql_call with actual DAIL SQL model calls")


if __name__ == "__main__":
    main()
    demonstrate_pipeline_workflow()
    demonstrate_dail_sql_integration()
