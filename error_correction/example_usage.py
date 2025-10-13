"""
Example usage of the VectorDBManager for Error Correction Pipeline

This script demonstrates how to use the VectorDBManager to store and retrieve queries.
"""

import os
import sys
from error_correction import VectorDBManager, ErrorCorrectionConfig, ErrorInfo


def main():
    """Main function demonstrating VectorDBManager usage"""
    
    # Initialize configuration
    config = ErrorCorrectionConfig()
    
    # Initialize VectorDBManager
    vector_db = VectorDBManager(config)
    
    print("=== VectorDBManager Example Usage ===\n")
    
    # Example 1: Store correct queries
    print("1. Storing correct queries...")
    
    correct_queries = [
        {
            "nl_query": "Find all users with age greater than 25",
            "sql_query": "SELECT * FROM users WHERE age > 25",
            "metadata": {"table": "users", "complexity": "simple"}
        },
        {
            "nl_query": "Get the count of orders by status",
            "sql_query": "SELECT status, COUNT(*) FROM orders GROUP BY status",
            "metadata": {"table": "orders", "complexity": "medium"}
        }
    ]
    
    correct_ids = []
    for query_data in correct_queries:
        query_id = vector_db.store_correct_query(
            nl_query=query_data["nl_query"],
            sql_query=query_data["sql_query"],
            metadata=query_data["metadata"]
        )
        correct_ids.append(query_id)
        print(f"   Stored correct query: {query_id}")
    
    # Example 2: Store wrong queries
    print("\n2. Storing wrong queries...")
    
    wrong_queries = [
        {
            "nl_query": "Find all users with age greater than 25",
            "sql_query": "SELECT * FROM users WERE age > 25",  # Typo: WERE instead of WHERE
            "error_info": ErrorInfo(
                error_type="syntax_error",
                error_message="Syntax error: 'WERE' should be 'WHERE'",
                error_code="SQL_SYNTAX_ERROR"
            ),
            "metadata": {"table": "users", "complexity": "simple"}
        },
        {
            "nl_query": "Get the count of orders by status",
            "sql_query": "SELECT status, COUNT(*) FROM orders GROUP BY status HAVING COUNT(*) > 1",  # Missing GROUP BY
            "error_info": ErrorInfo(
                error_type="semantic_error",
                error_message="Column 'status' must appear in GROUP BY clause",
                error_code="SQL_GROUP_BY_ERROR"
            ),
            "metadata": {"table": "orders", "complexity": "medium"}
        }
    ]
    
    wrong_ids = []
    for query_data in wrong_queries:
        query_id = vector_db.store_wrong_query(
            nl_query=query_data["nl_query"],
            sql_query=query_data["sql_query"],
            error_info=query_data["error_info"],
            metadata=query_data["metadata"]
        )
        wrong_ids.append(query_id)
        print(f"   Stored wrong query: {query_id}")
    
    # Example 3: Get query counts
    print("\n3. Getting query counts...")
    correct_count = vector_db.get_query_count("correct_queries")
    wrong_count = vector_db.get_query_count("wrong_queries")
    print(f"   Correct queries: {correct_count}")
    print(f"   Wrong queries: {wrong_count}")
    
    # Example 4: Retrieve similar queries
    print("\n4. Retrieving similar queries...")
    
    test_query = "Find users with age greater than 30"
    similar_correct = vector_db.retrieve_similar_queries(
        query=test_query,
        collection_name="correct_queries",
        top_k=2
    )
    
    print(f"   Similar correct queries for '{test_query}':")
    for query_record, similarity in similar_correct:
        print(f"     - {query_record.nl_query} (similarity: {similarity:.3f})")
    
    similar_wrong = vector_db.retrieve_similar_queries(
        query=test_query,
        collection_name="wrong_queries",
        top_k=2
    )
    
    print(f"   Similar wrong queries for '{test_query}':")
    for query_record, similarity in similar_wrong:
        print(f"     - {query_record.nl_query} (similarity: {similarity:.3f})")
        print(f"       Error: {query_record.error_message}")
    
    # Example 5: Get statistics
    print("\n5. Getting statistics...")
    stats = vector_db.get_statistics()
    print(f"   Total queries: {stats['total_queries']}")
    print(f"   Correct queries: {stats['total_correct_queries']}")
    print(f"   Wrong queries: {stats['total_wrong_queries']}")
    
    # Example 6: Export data
    print("\n6. Exporting data...")
    export_dir = "error_correction/data/exports"
    os.makedirs(export_dir, exist_ok=True)
    
    correct_export = os.path.join(export_dir, "correct_queries.json")
    wrong_export = os.path.join(export_dir, "wrong_queries.json")
    
    vector_db.export_collection("correct_queries", correct_export)
    vector_db.export_collection("wrong_queries", wrong_export)
    
    print(f"   Exported correct queries to: {correct_export}")
    print(f"   Exported wrong queries to: {wrong_export}")
    
    print("\n=== Example completed successfully! ===")


if __name__ == "__main__":
    main()
