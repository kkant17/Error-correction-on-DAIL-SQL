"""
ClusteringManager Example Usage for Error Correction Pipeline

This script demonstrates how to use the ClusteringManager to cluster
query-explanation-rule triplets and combine rules.
"""

import os
import numpy as np
from error_correction import ClusteringManager, TripletManager, ErrorCorrectionConfig, TripletData, ErrorInfo, Explanation, GeneratedRule


def main():
    """Demonstrate ClusteringManager usage"""
    
    print("=== ClusteringManager Example Usage ===\n")
    
    # Initialize configuration and managers
    config = ErrorCorrectionConfig()
    triplet_manager = TripletManager(config)
    clustering_manager = ClusteringManager(config)
    
    print(f"Initialized ClusteringManager with model: {config.LLM_MODEL}")
    print(f"Clustering threshold: {config.CLUSTERING_THRESHOLD}")
    print(f"A percent threshold: {config.A_PERCENT_THRESHOLD}")
    
    # Example 1: Create sample triplets for clustering
    print("\n1. Creating sample triplets for clustering...")
    
    sample_triplets = create_sample_triplets()
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
    
    # Example 2: Cluster triplets
    print("\n2. Clustering triplets...")
    
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
    
    # Perform clustering
    clusters = clustering_manager.cluster_triplets(triplet_data_objects, n_clusters=3)
    print(f"   Created {len(clusters)} clusters")
    
    # Example 3: Analyze clusters
    print("\n3. Analyzing clusters...")
    
    for i, cluster in enumerate(clusters, 1):
        print(f"   Cluster {i}:")
        print(f"   - Cluster ID: {cluster['cluster_id']}")
        print(f"   - Number of triplets: {len(cluster['triplets'])}")
        print(f"   - Success rate: {cluster.get('success_rate', 0):.2f}")
        print(f"   - Has combined rule: {cluster.get('combined_rule') is not None}")
        
        if cluster.get('representative'):
            rep = cluster['representative']
            print(f"   - Representative query: {rep.get('nl_query', 'N/A')}")
        
        if cluster.get('combined_rule'):
            rule = cluster['combined_rule']
            print(f"   - Combined rule pattern: {rule.get('pattern', 'N/A')}")
            print(f"   - Combined rule replacement: {rule.get('replacement', 'N/A')}")
            print(f"   - Combined rule confidence: {rule.get('confidence', 0):.2f}")
        
        print()
    
    # Example 4: Test cluster representative selection
    print("\n4. Testing cluster representative selection...")
    
    for i, cluster in enumerate(clusters, 1):
        if len(cluster['triplets']) > 1:
            representative = clustering_manager.get_cluster_representative(cluster)
            print(f"   Cluster {i} representative:")
            print(f"   - Triplet ID: {representative.get('triplet_id', 'N/A')}")
            print(f"   - NL Query: {representative.get('nl_query', 'N/A')}")
            print(f"   - SQL Query: {representative.get('sql_query', 'N/A')}")
            print(f"   - Error Type: {representative.get('error_type', 'N/A')}")
    
    # Example 5: Test rule combination
    print("\n5. Testing rule combination...")
    
    for i, cluster in enumerate(clusters, 1):
        if len(cluster['triplets']) > 1:
            combined_rule = clustering_manager.combine_rules_in_cluster(cluster)
            if combined_rule:
                print(f"   Cluster {i} combined rule:")
                print(f"   - Rule ID: {combined_rule.get('rule_id', 'N/A')}")
                print(f"   - Rule Type: {combined_rule.get('rule_type', 'N/A')}")
                print(f"   - Pattern: {combined_rule.get('pattern', 'N/A')}")
                print(f"   - Replacement: {combined_rule.get('replacement', 'N/A')}")
                print(f"   - Description: {combined_rule.get('description', 'N/A')}")
                print(f"   - Confidence: {combined_rule.get('confidence', 0):.2f}")
                print(f"   - Source rules: {combined_rule.get('source_rules', [])}")
            else:
                print(f"   Cluster {i}: No rules to combine")
    
    # Example 6: Test rule validation
    print("\n6. Testing rule validation...")
    
    for i, cluster in enumerate(clusters, 1):
        if cluster.get('combined_rule'):
            success_rate, failed_queries = clustering_manager.validate_combined_rule(
                cluster['combined_rule'], 
                cluster['triplets']
            )
            print(f"   Cluster {i} validation:")
            print(f"   - Success rate: {success_rate:.2f}")
            print(f"   - Failed queries: {len(failed_queries)}")
            if failed_queries:
                print(f"   - Failed query IDs: {failed_queries[:3]}...")  # Show first 3
    
    # Example 7: Get clustering statistics
    print("\n7. Getting clustering statistics...")
    
    stats = clustering_manager.get_clustering_statistics()
    print(f"   Total clusters: {stats['total_clusters']}")
    print(f"   Total triplets: {stats['total_triplets']}")
    print(f"   Average cluster size: {stats['average_cluster_size']:.2f}")
    print(f"   Clusters by error type: {stats['clusters_by_error_type']}")
    print(f"   Largest cluster size: {stats['largest_cluster_size']}")
    print(f"   Smallest cluster size: {stats['smallest_cluster_size']}")
    
    # Example 8: Export clusters
    print("\n8. Exporting clusters...")
    
    export_file = "error_correction/data/clusters_export.json"
    try:
        clustering_manager.export_generated_rules(export_file)
        print(f"   Exported clusters to: {export_file}")
    except Exception as e:
        print(f"   Error exporting clusters: {e}")
    
    print("\n=== ClusteringManager example completed! ===")


def create_sample_triplets():
    """Create sample triplets for testing"""
    triplets = []
    
    # Triplet 1: Syntax error - SELCT typo
    error_info1 = ErrorInfo(
        error_message="Syntax error: 'SELCT' is not a valid SQL keyword",
        error_type="syntax_error",
        error_code="SQL_SYNTAX_ERROR",
        severity="high"
    )
    
    explanation1 = Explanation(
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
    
    rule1 = {
        'rule_id': 'rule_001',
        'rule_type': 'syntax',
        'pattern': r'\bSELCT\b',
        'replacement': 'SELECT',
        'description': 'Fix SELCT typo to SELECT',
        'confidence': 0.9,
        'conditions': {'query_type': 'SELECT'},
        'created_at': '2024-01-01T10:01:00Z'
    }
    
    triplets.append({
        'triplet_id': 'triplet_001',
        'nl_query': 'Find all users with age greater than 25',
        'sql_query': 'SELCT * FROM users WHERE age > 25',
        'explanation': explanation1,
        'rule': rule1,
        'error_type': 'syntax_error',
        'timestamp': '2024-01-01T10:00:00Z',
        'database_schema': 'user_management',
        'metadata': {'source': 'example', 'priority': 'high'}
    })
    
    # Triplet 2: Similar syntax error - SELCT typo
    error_info2 = ErrorInfo(
        error_message="Syntax error: 'SELCT' is not a valid SQL keyword",
        error_type="syntax_error",
        error_code="SQL_SYNTAX_ERROR",
        severity="high"
    )
    
    explanation2 = Explanation(
        explanation_id="exp_002",
        query_id="query_002",
        query_text="Get all products from the database",
        error_type="syntax_error",
        explanation_text="The SQL query contains a typo in the SELECT keyword. 'SELCT' should be 'SELECT'.",
        confidence=0.95,
        suggested_fix="Change 'SELCT' to 'SELECT'",
        metadata={'model': 'gpt-4'},
        created_at="2024-01-01T10:02:00Z"
    )
    
    rule2 = {
        'rule_id': 'rule_002',
        'rule_type': 'syntax',
        'pattern': r'\bSELCT\b',
        'replacement': 'SELECT',
        'description': 'Fix SELCT typo to SELECT',
        'confidence': 0.9,
        'conditions': {'query_type': 'SELECT'},
        'created_at': '2024-01-01T10:03:00Z'
    }
    
    triplets.append({
        'triplet_id': 'triplet_002',
        'nl_query': 'Get all products from the database',
        'sql_query': 'SELCT * FROM products WHERE price > 100',
        'explanation': explanation2,
        'rule': rule2,
        'error_type': 'syntax_error',
        'timestamp': '2024-01-01T10:02:00Z',
        'database_schema': 'ecommerce',
        'metadata': {'source': 'example', 'priority': 'high'}
    })
    
    # Triplet 3: Semantic error - GROUP BY
    error_info3 = ErrorInfo(
        error_message="Column 'status' must appear in GROUP BY clause",
        error_type="semantic_error",
        error_code="SQL_GROUP_BY_ERROR",
        severity="medium"
    )
    
    explanation3 = Explanation(
        explanation_id="exp_003",
        query_id="query_003",
        query_text="Get the count of orders by status",
        error_type="semantic_error",
        explanation_text="The query uses HAVING without proper GROUP BY clause. All non-aggregated columns must be in GROUP BY.",
        confidence=0.85,
        suggested_fix="Add GROUP BY status clause",
        metadata={'model': 'gpt-4'},
        created_at="2024-01-01T10:05:00Z"
    )
    
    rule3 = {
        'rule_id': 'rule_003',
        'rule_type': 'semantic',
        'pattern': r'SELECT\s+([^,]+),\s*COUNT\([^)]+\)\s+FROM\s+(\w+)\s+HAVING',
        'replacement': r'SELECT \1, COUNT(*) FROM \2 GROUP BY \1 HAVING',
        'description': 'Add GROUP BY clause for non-aggregated columns',
        'confidence': 0.8,
        'conditions': {'query_type': 'SELECT', 'contains_keywords': ['COUNT', 'HAVING']},
        'created_at': '2024-01-01T10:06:00Z'
    }
    
    triplets.append({
        'triplet_id': 'triplet_003',
        'nl_query': 'Get the count of orders by status',
        'sql_query': 'SELECT status, COUNT(*) FROM orders HAVING COUNT(*) > 1',
        'explanation': explanation3,
        'rule': rule3,
        'error_type': 'semantic_error',
        'timestamp': '2024-01-01T10:05:00Z',
        'database_schema': 'ecommerce',
        'metadata': {'source': 'example', 'priority': 'medium'}
    })
    
    # Add more triplets to reach the minimum of 10
    for i in range(4, 12):
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
                metadata={'model': 'gpt-4'},
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
                metadata={'model': 'gpt-4'},
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


def demonstrate_clustering_workflow():
    """Demonstrate a complete clustering workflow"""
    print("\n=== Complete Clustering Workflow ===")
    
    config = ErrorCorrectionConfig()
    clustering_manager = ClusteringManager(config)
    
    print("1. Creating triplets for clustering...")
    
    # Create triplets with similar errors
    triplets = create_sample_triplets()
    print(f"   Created {len(triplets)} triplets")
    
    # Convert to TripletData objects
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
    
    print("\n2. Performing clustering...")
    
    # Cluster the triplets
    clusters = clustering_manager.cluster_triplets(triplet_data_objects, n_clusters=3)
    print(f"   Created {len(clusters)} clusters")
    
    print("\n3. Analyzing cluster quality...")
    
    for i, cluster in enumerate(clusters, 1):
        print(f"   Cluster {i}:")
        print(f"   - Size: {len(cluster['triplets'])}")
        print(f"   - Success rate: {cluster.get('success_rate', 0):.2f}")
        print(f"   - Representative: {cluster.get('representative', {}).get('nl_query', 'N/A')}")
        
        if cluster.get('combined_rule'):
            rule = cluster['combined_rule']
            print(f"   - Combined rule: {rule.get('pattern', 'N/A')} -> {rule.get('replacement', 'N/A')}")
            print(f"   - Rule confidence: {rule.get('confidence', 0):.2f}")
    
    print("\n4. Workflow completed!")
    print(f"   Total clusters: {len(clusters)}")
    print(f"   Average cluster size: {sum(len(c['triplets']) for c in clusters) / len(clusters):.1f}")
    
    return clusters


if __name__ == "__main__":
    main()
    demonstrate_clustering_workflow()
