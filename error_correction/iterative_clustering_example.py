"""
Iterative Clustering Example for Error Correction Pipeline

This script demonstrates the new iterative cluster merging functionality
with detailed validation and logging.
"""

import os
import logging
from error_correction import ClusteringManager, TripletManager, ErrorCorrectionConfig, TripletData, ErrorInfo, Explanation


def setup_logging():
    """Setup detailed logging for the clustering process"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('error_correction/data/clustering.log')
        ]
    )


def main():
    """Demonstrate iterative cluster merging with detailed logging"""
    
    print("=== Iterative Cluster Merging Example ===\n")
    
    # Setup logging
    setup_logging()
    
    # Initialize configuration and managers
    config = ErrorCorrectionConfig()
    triplet_manager = TripletManager(config)
    clustering_manager = ClusteringManager(config)
    
    print(f"Initialized ClusteringManager with model: {config.LLM_MODEL}")
    print(f"Clustering threshold: {config.CLUSTERING_THRESHOLD}")
    print(f"A percent threshold: {config.A_PERCENT_THRESHOLD}")
    print(f"Max clustering iterations: {config.MAX_CLUSTERING_ITERATIONS}")
    
    # Example 1: Create sample triplets with similar errors
    print("\n1. Creating sample triplets with similar errors...")
    
    sample_triplets = create_similar_error_triplets()
    print(f"   Created {len(sample_triplets)} sample triplets")
    
    # Add triplets to triplet manager
    for triplet in sample_triplets:
        triplet_manager.add_triplet(
            nl_query=triplet['nl_query'],
            sql_query=triplet['sql_query'],
            explanation=triplet['explanation'],
            rule=triplet['rule'],
            database_schema=triplet['database_schema'],
            metadata=triplet['metadata']
        )
    
    print(f"   Added triplets to manager. Total count: {triplet_manager.get_triplet_count()}")
    
    # Example 2: Perform iterative cluster merging
    print("\n2. Performing iterative cluster merging...")
    print("   (Check clustering.log for detailed merge attempts)")
    
    # Convert to TripletData objects for clustering
    triplet_data_objects = []
    for triplet in sample_triplets:
        triplet_data = TripletData(
            triplet_id=triplet['triplet_id'],
            nl_query=triplet['nl_query'],
            sql_query=triplet['sql_query'],
            explanation=triplet['explanation'],
            rule=triplet['rule'],
            error_type=triplet['error_type'],
            timestamp=triplet['timestamp'],
            database_schema=triplet['database_schema'],
            metadata=triplet['metadata']
        )
        triplet_data_objects.append(triplet_data)
    
    # Perform iterative clustering
    clusters = clustering_manager.iterative_cluster_merging(
        triplet_data_objects, 
        a_percent_threshold=config.A_PERCENT_THRESHOLD
    )
    
    print(f"   Clustering completed. Created {len(clusters)} valid clusters")
    
    # Example 3: Analyze clustering results
    print("\n3. Analyzing clustering results...")
    
    if not clusters:
        print("   No valid clusters created (combination percentage below threshold)")
        return
    
    total_triplets = len(triplet_data_objects)
    combined_triplets = sum(len(cluster['triplets']) for cluster in clusters)
    combination_percentage = (combined_triplets / total_triplets) * 100
    
    print(f"   Total triplets: {total_triplets}")
    print(f"   Combined triplets: {combined_triplets}")
    print(f"   Combination percentage: {combination_percentage:.1f}%")
    print(f"   Valid clusters: {len(clusters)}")
    
    # Example 4: Analyze each cluster
    print("\n4. Analyzing individual clusters...")
    
    for i, cluster in enumerate(clusters, 1):
        print(f"   Cluster {i}:")
        print(f"   - Cluster ID: {cluster['cluster_id']}")
        print(f"   - Size: {len(cluster['triplets'])} triplets")
        print(f"   - Merge history: {len(cluster.get('merge_history', []))} merges")
        
        if cluster.get('combined_rule'):
            rule = cluster['combined_rule']
            print(f"   - Combined rule:")
            print(f"     * Pattern: {rule.get('pattern', 'N/A')}")
            print(f"     * Replacement: {rule.get('replacement', 'N/A')}")
            print(f"     * Confidence: {rule.get('confidence', 0):.3f}")
            print(f"     * Source rules: {len(rule.get('source_rules', []))}")
        
        if cluster.get('representative'):
            rep = cluster['representative']
            print(f"   - Representative:")
            print(f"     * NL Query: {rep.get('nl_query', 'N/A')}")
            print(f"     * SQL Query: {rep.get('sql_query', 'N/A')}")
            print(f"     * Error Type: {rep.get('error_type', 'N/A')}")
        
        if cluster.get('final_success_rate') is not None:
            print(f"   - Final success rate: {cluster['final_success_rate']:.3f}")
            print(f"   - Failed queries: {len(cluster.get('final_failed_queries', []))}")
        
        print()
    
    # Example 5: Test cluster representatives
    print("\n5. Testing cluster representatives...")
    
    for i, cluster in enumerate(clusters, 1):
        if len(cluster['triplets']) > 1:
            representative = clustering_manager.get_cluster_representative(cluster)
            print(f"   Cluster {i} representative:")
            print(f"   - Triplet ID: {representative.get('triplet_id', 'N/A')}")
            print(f"   - NL Query: {representative.get('nl_query', 'N/A')}")
            print(f"   - SQL Query: {representative.get('sql_query', 'N/A')}")
            print(f"   - Error Type: {representative.get('error_type', 'N/A')}")
    
    # Example 6: Test combined rules
    print("\n6. Testing combined rules...")
    
    for i, cluster in enumerate(clusters, 1):
        if cluster.get('combined_rule'):
            combined_rule = cluster['combined_rule']
            print(f"   Cluster {i} combined rule:")
            print(f"   - Rule ID: {combined_rule.get('rule_id', 'N/A')}")
            print(f"   - Rule Type: {combined_rule.get('rule_type', 'N/A')}")
            print(f"   - Pattern: {combined_rule.get('pattern', 'N/A')}")
            print(f"   - Replacement: {combined_rule.get('replacement', 'N/A')}")
            print(f"   - Description: {combined_rule.get('description', 'N/A')}")
            print(f"   - Confidence: {combined_rule.get('confidence', 0):.3f}")
            print(f"   - Source rules: {combined_rule.get('source_rules', [])}")
    
    # Example 7: Validate combined rules
    print("\n7. Validating combined rules...")
    
    for i, cluster in enumerate(clusters, 1):
        if cluster.get('combined_rule'):
            success_rate, failed_queries = clustering_manager.validate_combined_rule(
                cluster['combined_rule'], 
                cluster['triplets']
            )
            print(f"   Cluster {i} validation:")
            print(f"   - Success rate: {success_rate:.3f}")
            print(f"   - Failed queries: {len(failed_queries)}")
            if failed_queries:
                print(f"   - Failed query IDs: {failed_queries[:3]}...")  # Show first 3
    
    # Example 8: Export results
    print("\n8. Exporting clustering results...")
    
    export_file = "error_correction/data/iterative_clustering_results.json"
    try:
        clustering_manager.export_generated_rules(export_file)
        print(f"   Exported results to: {export_file}")
    except Exception as e:
        print(f"   Error exporting results: {e}")
    
    print("\n=== Iterative clustering example completed! ===")
    print("Check clustering.log for detailed merge attempt logs")


def create_similar_error_triplets():
    """Create sample triplets with similar errors for clustering"""
    triplets = []
    
    # Group 1: SELCT typos (should cluster together)
    selct_queries = [
        "Find all users with age greater than 25",
        "Get all products from the database", 
        "Show me all customers in the system",
        "List all orders from last month",
        "Display all employees in the company"
    ]
    
    for i, nl_query in enumerate(selct_queries):
        error_info = ErrorInfo(
            error_message="Syntax error: 'SELCT' is not a valid SQL keyword",
            error_type="syntax_error",
            error_code="SQL_SYNTAX_ERROR",
            severity="high"
        )
        
        explanation = Explanation(
            explanation_id=f"exp_selct_{i:03d}",
            query_id=f"query_selct_{i:03d}",
            query_text=nl_query,
            error_type="syntax_error",
            explanation_text=f"The SQL query contains a typo in the SELECT keyword. 'SELCT' should be 'SELECT'.",
            confidence=0.95,
            suggested_fix="Change 'SELCT' to 'SELECT'",
            metadata={'model': 'gpt-4', 'error_group': 'selct_typo'},
            created_at=f"2024-01-01T10:{i:02d}:00Z"
        )
        
        rule = {
            'rule_id': f'rule_selct_{i:03d}',
            'rule_type': 'syntax',
            'pattern': r'\bSELCT\b',
            'replacement': 'SELECT',
            'description': 'Fix SELCT typo to SELECT',
            'confidence': 0.9,
            'conditions': {'query_type': 'SELECT'},
            'created_at': f"2024-01-01T10:{i:02d}:00Z"
        }
        
        triplets.append({
            'triplet_id': f'triplet_selct_{i:03d}',
            'nl_query': nl_query,
            'sql_query': f"SELCT * FROM table_{i} WHERE id > {i}",
            'explanation': explanation,
            'rule': rule,
            'error_type': 'syntax_error',
            'timestamp': f'2024-01-01T10:{i:02d}:00Z',
            'database_schema': f'schema_{i % 2}',
            'metadata': {'source': 'example', 'priority': 'high', 'error_group': 'selct_typo'}
        })
    
    # Group 2: GROUP BY errors (should cluster together)
    groupby_queries = [
        "Get the count of orders by status",
        "Show me the number of users by department",
        "Count products by category",
        "Display order counts by region",
        "List user counts by age group"
    ]
    
    for i, nl_query in enumerate(groupby_queries):
        error_info = ErrorInfo(
            error_message="Column must appear in GROUP BY clause",
            error_type="semantic_error",
            error_code="SQL_GROUP_BY_ERROR",
            severity="medium"
        )
        
        explanation = Explanation(
            explanation_id=f"exp_groupby_{i:03d}",
            query_id=f"query_groupby_{i:03d}",
            query_text=nl_query,
            error_type="semantic_error",
            explanation_text=f"The query uses HAVING without proper GROUP BY clause. All non-aggregated columns must be in GROUP BY.",
            confidence=0.85,
            suggested_fix="Add GROUP BY clause",
            metadata={'model': 'gpt-4', 'error_group': 'groupby_error'},
            created_at=f"2024-01-01T10:{i+5:02d}:00Z"
        )
        
        rule = {
            'rule_id': f'rule_groupby_{i:03d}',
            'rule_type': 'semantic',
            'pattern': r'SELECT\s+([^,]+),\s*COUNT\([^)]+\)\s+FROM\s+(\w+)\s+HAVING',
            'replacement': r'SELECT \1, COUNT(*) FROM \2 GROUP BY \1 HAVING',
            'description': 'Add GROUP BY clause for non-aggregated columns',
            'confidence': 0.8,
            'conditions': {'query_type': 'SELECT', 'contains_keywords': ['COUNT', 'HAVING']},
            'created_at': f"2024-01-01T10:{i+5:02d}:00Z"
        }
        
        triplets.append({
            'triplet_id': f'triplet_groupby_{i:03d}',
            'nl_query': nl_query,
            'sql_query': f"SELECT status, COUNT(*) FROM table_{i} HAVING COUNT(*) > {i}",
            'explanation': explanation,
            'rule': rule,
            'error_type': 'semantic_error',
            'timestamp': f'2024-01-01T10:{i+5:02d}:00Z',
            'database_schema': f'schema_{i % 2}',
            'metadata': {'source': 'example', 'priority': 'medium', 'error_group': 'groupby_error'}
        })
    
    # Add a few more triplets to reach the minimum of 10
    for i in range(10, 15):
        # Create variations of the same error types
        error_type = 'syntax_error' if i % 2 == 0 else 'semantic_error'
        
        if error_type == 'syntax_error':
            # More SELCT typos
            explanation = Explanation(
                explanation_id=f"exp_{i:03d}",
                query_id=f"query_{i:03d}",
                query_text=f"Sample query {i}",
                error_type="syntax_error",
                explanation_text=f"SQL query contains SELCT typo in query {i}",
                confidence=0.9,
                suggested_fix="Change 'SELCT' to 'SELECT'",
                metadata={'model': 'gpt-4', 'error_group': 'selct_typo'},
                created_at=f"2024-01-01T10:{i:02d}:00Z"
            )
            
            rule = {
                'rule_id': f'rule_{i:03d}',
                'rule_type': 'syntax',
                'pattern': r'\bSELCT\b',
                'replacement': 'SELECT',
                'description': 'Fix SELCT typo to SELECT',
                'confidence': 0.9,
                'conditions': {'query_type': 'SELECT'},
                'created_at': f"2024-01-01T10:{i:02d}:00Z"
            }
            
            sql_query = f"SELCT * FROM table_{i} WHERE id > {i}"
        else:
            # More GROUP BY errors
            explanation = Explanation(
                explanation_id=f"exp_{i:03d}",
                query_id=f"query_{i:03d}",
                query_text=f"Sample query {i}",
                error_type="semantic_error",
                explanation_text=f"SQL query missing GROUP BY clause in query {i}",
                confidence=0.8,
                suggested_fix="Add GROUP BY clause",
                metadata={'model': 'gpt-4', 'error_group': 'groupby_error'},
                created_at=f"2024-01-01T10:{i:02d}:00Z"
            )
            
            rule = {
                'rule_id': f'rule_{i:03d}',
                'rule_type': 'semantic',
                'pattern': r'SELECT\s+([^,]+),\s*COUNT\([^)]+\)\s+FROM\s+(\w+)\s+HAVING',
                'replacement': r'SELECT \1, COUNT(*) FROM \2 GROUP BY \1 HAVING',
                'description': 'Add GROUP BY clause for non-aggregated columns',
                'confidence': 0.8,
                'conditions': {'query_type': 'SELECT', 'contains_keywords': ['COUNT', 'HAVING']},
                'created_at': f"2024-01-01T10:{i:02d}:00Z"
            }
            
            sql_query = f"SELECT status, COUNT(*) FROM table_{i} HAVING COUNT(*) > {i}"
        
        triplets.append({
            'triplet_id': f'triplet_{i:03d}',
            'nl_query': f'Sample natural language query {i}',
            'sql_query': sql_query,
            'explanation': explanation,
            'rule': rule,
            'error_type': error_type,
            'timestamp': f'2024-01-01T10:{i:02d}:00Z',
            'database_schema': f'schema_{i % 3}',
            'metadata': {'source': 'example', 'priority': 'medium', 'index': i}
        })
    
    return triplets


def demonstrate_clustering_with_different_thresholds():
    """Demonstrate clustering with different A percent thresholds"""
    print("\n=== Clustering with Different Thresholds ===")
    
    config = ErrorCorrectionConfig()
    clustering_manager = ClusteringManager(config)
    
    # Create triplets
    triplets = create_similar_error_triplets()
    triplet_data_objects = []
    for triplet in triplets:
        triplet_data = TripletData(
            triplet_id=triplet['triplet_id'],
            nl_query=triplet['nl_query'],
            sql_query=triplet['sql_query'],
            explanation=triplet['explanation'],
            rule=triplet['rule'],
            error_type=triplet['error_type'],
            timestamp=triplet['timestamp'],
            database_schema=triplet['database_schema'],
            metadata=triplet['metadata']
        )
        triplet_data_objects.append(triplet_data)
    
    # Test different thresholds
    thresholds = [0.5, 0.7, 0.8, 0.9]
    
    for threshold in thresholds:
        print(f"\nTesting with A percent threshold: {threshold}")
        
        clusters = clustering_manager.iterative_cluster_merging(
            triplet_data_objects, 
            a_percent_threshold=threshold
        )
        
        if clusters:
            total_triplets = len(triplet_data_objects)
            combined_triplets = sum(len(cluster['triplets']) for cluster in clusters)
            combination_percentage = (combined_triplets / total_triplets) * 100
            
            print(f"  - Valid clusters: {len(clusters)}")
            print(f"  - Combined triplets: {combined_triplets}/{total_triplets} ({combination_percentage:.1f}%)")
        else:
            print(f"  - No valid clusters (combination percentage < {threshold})")


if __name__ == "__main__":
    main()
    demonstrate_clustering_with_different_thresholds()
