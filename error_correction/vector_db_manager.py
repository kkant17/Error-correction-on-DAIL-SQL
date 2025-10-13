"""
Vector Database Manager for Error Correction Pipeline

This module manages the storage and retrieval of correct and wrong queries using ChromaDB.
It provides functionality for embedding queries, storing them, and performing similarity searches.
"""

import os
import json
import logging
import uuid
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
from .config import ErrorCorrectionConfig


@dataclass
class QueryRecord:
    """Data class for storing query records"""
    query_id: str
    nl_query: str
    sql_query: str
    query_type: str  # 'correct' or 'wrong'
    execution_result: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None


@dataclass
class ErrorInfo:
    """Data class for error information"""
    error_type: str
    error_message: str
    error_code: Optional[str] = None
    stack_trace: Optional[str] = None


class VectorDBManager:
    """Manages vector database operations for query storage and retrieval using ChromaDB"""
    
    def __init__(self, config: ErrorCorrectionConfig):
        """
        Initialize the VectorDBManager
        
        Args:
            config: Configuration object containing parameters
        """
        self.config = config
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.logger = logging.getLogger(__name__)
        
        # Initialize ChromaDB client
        self._initialize_chromadb()
        
        # Initialize collections
        self._initialize_collections()
    
    def _initialize_chromadb(self):
        """Initialize ChromaDB client"""
        try:
            # Create persistent client with custom settings
            self.chroma_client = chromadb.PersistentClient(
                path=os.path.join(self.config.DATA_DIR, "chroma_db"),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            self.logger.info("ChromaDB client initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize ChromaDB client: {e}")
            raise
    
    def _initialize_collections(self):
        """Initialize ChromaDB collections"""
        try:
            # Create or get correct queries collection
            self.correct_collection = self.chroma_client.get_or_create_collection(
                name="correct_queries",
                metadata={"description": "Collection for correct SQL queries"}
            )
            
            # Create or get wrong queries collection
            self.wrong_collection = self.chroma_client.get_or_create_collection(
                name="wrong_queries", 
                metadata={"description": "Collection for wrong SQL queries"}
            )
            
            self.logger.info("ChromaDB collections initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize collections: {e}")
            raise
    
    def store_correct_query(self, nl_query: str, sql_query: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Store a correct query in the database
        
        Args:
            nl_query: Natural language query
            sql_query: Generated SQL query
            metadata: Optional metadata about the query
            
        Returns:
            Query ID
        """
        try:
            query_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            # Create query record
            query_record = QueryRecord(
                query_id=query_id,
                nl_query=nl_query,
                sql_query=sql_query,
                query_type="correct",
                execution_result="success",
                metadata=metadata or {},
                timestamp=timestamp
            )
            
            # Generate embedding for the combined text
            combined_text = f"{nl_query} {sql_query}"
            embedding = self.embedding_model.encode(combined_text).tolist()
            
            # Prepare metadata for ChromaDB
            chroma_metadata = {
                "query_id": query_id,
                "nl_query": nl_query,
                "sql_query": sql_query,
                "query_type": "correct",
                "execution_result": "success",
                "timestamp": timestamp,
                **(metadata or {})
            }
            
            # Add to ChromaDB collection
            self.correct_collection.add(
                ids=[query_id],
                embeddings=[embedding],
                metadatas=[chroma_metadata],
                documents=[combined_text]
            )
            
            self.logger.info(f"Stored correct query: {query_id}")
            return query_id
            
        except Exception as e:
            self.logger.error(f"Failed to store correct query: {e}")
            raise
    
    def store_wrong_query(self, nl_query: str, sql_query: str, error_info: ErrorInfo, 
                         metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Store a wrong query in the database
        
        Args:
            nl_query: Natural language query
            sql_query: Generated SQL query
            error_info: Error information
            metadata: Optional metadata about the query
            
        Returns:
            Query ID
        """
        try:
            query_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            # Create query record
            query_record = QueryRecord(
                query_id=query_id,
                nl_query=nl_query,
                sql_query=sql_query,
                query_type="wrong",
                execution_result="error",
                error_type=error_info.error_type,
                error_message=error_info.error_message,
                metadata=metadata or {},
                timestamp=timestamp
            )
            
            # Generate embedding for the combined text
            combined_text = f"{nl_query} {sql_query} {error_info.error_message}"
            embedding = self.embedding_model.encode(combined_text).tolist()
            
            # Prepare metadata for ChromaDB
            chroma_metadata = {
                "query_id": query_id,
                "nl_query": nl_query,
                "sql_query": sql_query,
                "query_type": "wrong",
                "execution_result": "error",
                "error_type": error_info.error_type,
                "error_message": error_info.error_message,
                "error_code": error_info.error_code,
                "timestamp": timestamp,
                **(metadata or {})
            }
            
            # Add to ChromaDB collection
            self.wrong_collection.add(
                ids=[query_id],
                embeddings=[embedding],
                metadatas=[chroma_metadata],
                documents=[combined_text]
            )
            
            self.logger.info(f"Stored wrong query: {query_id}")
            return query_id
            
        except Exception as e:
            self.logger.error(f"Failed to store wrong query: {e}")
            raise
    
    def retrieve_similar_queries(self, query: str, collection_name: str, top_k: int = 5) -> List[Tuple[QueryRecord, float]]:
        """
        Retrieve similar queries from the specified collection
        
        Args:
            query: Query to find similarities for
            collection_name: Name of the collection ('correct_queries' or 'wrong_queries')
            top_k: Number of similar queries to return
            
        Returns:
            List of tuples containing (QueryRecord, similarity_score)
        """
        try:
            # Get the appropriate collection
            if collection_name == "correct_queries":
                collection = self.correct_collection
            elif collection_name == "wrong_queries":
                collection = self.wrong_collection
            else:
                raise ValueError(f"Invalid collection name: {collection_name}")
            
            # Generate embedding for the query
            query_embedding = self.embedding_model.encode(query).tolist()
            
            # Query the collection
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=['metadatas', 'distances']
            )
            
            # Convert results to QueryRecord objects
            similar_queries = []
            if results['ids'] and results['ids'][0]:
                for i, (query_id, metadata, distance) in enumerate(zip(
                    results['ids'][0], 
                    results['metadatas'][0], 
                    results['distances'][0]
                )):
                    # Convert distance to similarity score (ChromaDB uses cosine distance)
                    similarity_score = 1 - distance
                    
                    # Create QueryRecord from metadata
                    query_record = QueryRecord(
                        query_id=metadata.get('query_id', query_id),
                        nl_query=metadata.get('nl_query', ''),
                        sql_query=metadata.get('sql_query', ''),
                        query_type=metadata.get('query_type', ''),
                        execution_result=metadata.get('execution_result'),
                        error_type=metadata.get('error_type'),
                        error_message=metadata.get('error_message'),
                        metadata={k: v for k, v in metadata.items() 
                                if k not in ['query_id', 'nl_query', 'sql_query', 'query_type', 
                                           'execution_result', 'error_type', 'error_message', 'timestamp']},
                        timestamp=metadata.get('timestamp')
                    )
                    
                    similar_queries.append((query_record, similarity_score))
            
            self.logger.info(f"Retrieved {len(similar_queries)} similar queries from {collection_name}")
            return similar_queries
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve similar queries: {e}")
            raise
    
    def get_query_count(self, collection_name: str) -> int:
        """
        Get the count of queries in the specified collection
        
        Args:
            collection_name: Name of the collection ('correct_queries' or 'wrong_queries')
            
        Returns:
            Number of queries in the collection
        """
        try:
            if collection_name == "correct_queries":
                collection = self.correct_collection
            elif collection_name == "wrong_queries":
                collection = self.wrong_collection
            else:
                raise ValueError(f"Invalid collection name: {collection_name}")
            
            count = collection.count()
            self.logger.info(f"Collection {collection_name} has {count} queries")
            return count
            
        except Exception as e:
            self.logger.error(f"Failed to get query count: {e}")
            raise
    
    def get_query_by_id(self, query_id: str, collection_name: str) -> Optional[QueryRecord]:
        """
        Get a query record by ID from the specified collection
        
        Args:
            query_id: ID of the query to retrieve
            collection_name: Name of the collection ('correct_queries' or 'wrong_queries')
            
        Returns:
            QueryRecord if found, None otherwise
        """
        try:
            if collection_name == "correct_queries":
                collection = self.correct_collection
            elif collection_name == "wrong_queries":
                collection = self.wrong_collection
            else:
                raise ValueError(f"Invalid collection name: {collection_name}")
            
            # Get the query by ID
            results = collection.get(
                ids=[query_id],
                include=['metadatas']
            )
            
            if results['ids'] and results['ids'][0]:
                metadata = results['metadatas'][0]
                return QueryRecord(
                    query_id=metadata.get('query_id', query_id),
                    nl_query=metadata.get('nl_query', ''),
                    sql_query=metadata.get('sql_query', ''),
                    query_type=metadata.get('query_type', ''),
                    execution_result=metadata.get('execution_result'),
                    error_type=metadata.get('error_type'),
                    error_message=metadata.get('error_message'),
                    metadata={k: v for k, v in metadata.items() 
                            if k not in ['query_id', 'nl_query', 'sql_query', 'query_type', 
                                       'execution_result', 'error_type', 'error_message', 'timestamp']},
                    timestamp=metadata.get('timestamp')
                )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get query by ID: {e}")
            return None
    
    def get_all_queries(self, collection_name: str, limit: Optional[int] = None) -> List[QueryRecord]:
        """
        Get all queries from the specified collection
        
        Args:
            collection_name: Name of the collection ('correct_queries' or 'wrong_queries')
            limit: Optional limit on number of queries to return
            
        Returns:
            List of QueryRecord objects
        """
        try:
            if collection_name == "correct_queries":
                collection = self.correct_collection
            elif collection_name == "wrong_queries":
                collection = self.wrong_collection
            else:
                raise ValueError(f"Invalid collection name: {collection_name}")
            
            # Get all queries
            results = collection.get(
                include=['metadatas'],
                limit=limit
            )
            
            queries = []
            if results['ids']:
                for i, query_id in enumerate(results['ids']):
                    metadata = results['metadatas'][i]
                    query_record = QueryRecord(
                        query_id=metadata.get('query_id', query_id),
                        nl_query=metadata.get('nl_query', ''),
                        sql_query=metadata.get('sql_query', ''),
                        query_type=metadata.get('query_type', ''),
                        execution_result=metadata.get('execution_result'),
                        error_type=metadata.get('error_type'),
                        error_message=metadata.get('error_message'),
                        metadata={k: v for k, v in metadata.items() 
                                if k not in ['query_id', 'nl_query', 'sql_query', 'query_type', 
                                           'execution_result', 'error_type', 'error_message', 'timestamp']},
                        timestamp=metadata.get('timestamp')
                    )
                    queries.append(query_record)
            
            return queries
            
        except Exception as e:
            self.logger.error(f"Failed to get all queries: {e}")
            raise
    
    def delete_query(self, query_id: str, collection_name: str) -> bool:
        """
        Delete a query from the specified collection
        
        Args:
            query_id: ID of the query to delete
            collection_name: Name of the collection ('correct_queries' or 'wrong_queries')
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            if collection_name == "correct_queries":
                collection = self.correct_collection
            elif collection_name == "wrong_queries":
                collection = self.wrong_collection
            else:
                raise ValueError(f"Invalid collection name: {collection_name}")
            
            collection.delete(ids=[query_id])
            self.logger.info(f"Deleted query {query_id} from {collection_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete query: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the stored queries
        
        Returns:
            Dictionary containing statistics
        """
        try:
            correct_count = self.get_query_count("correct_queries")
            wrong_count = self.get_query_count("wrong_queries")
            
            return {
                'total_correct_queries': correct_count,
                'total_wrong_queries': wrong_count,
                'total_queries': correct_count + wrong_count,
                'collections': {
                    'correct_queries': correct_count,
                    'wrong_queries': wrong_count
                }
            }
        except Exception as e:
            self.logger.error(f"Failed to get statistics: {e}")
            return {
                'total_correct_queries': 0,
                'total_wrong_queries': 0,
                'total_queries': 0,
                'error': str(e)
            }
    
    def clear_collection(self, collection_name: str) -> bool:
        """
        Clear all queries from the specified collection
        
        Args:
            collection_name: Name of the collection to clear
            
        Returns:
            True if cleared successfully, False otherwise
        """
        try:
            if collection_name == "correct_queries":
                collection = self.correct_collection
            elif collection_name == "wrong_queries":
                collection = self.wrong_collection
            else:
                raise ValueError(f"Invalid collection name: {collection_name}")
            
            # Get all IDs and delete them
            results = collection.get(include=[])
            if results['ids']:
                collection.delete(ids=results['ids'])
            
            self.logger.info(f"Cleared collection {collection_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to clear collection: {e}")
            return False
    
    def clear_all_data(self):
        """Clear all stored data from both collections"""
        try:
            self.clear_collection("correct_queries")
            self.clear_collection("wrong_queries")
            self.logger.info("Cleared all data from vector database")
        except Exception as e:
            self.logger.error(f"Failed to clear all data: {e}")
            raise
    
    def export_collection(self, collection_name: str, file_path: str) -> bool:
        """
        Export a collection to a JSON file
        
        Args:
            collection_name: Name of the collection to export
            file_path: Path to save the exported data
            
        Returns:
            True if exported successfully, False otherwise
        """
        try:
            queries = self.get_all_queries(collection_name)
            
            # Convert QueryRecord objects to dictionaries
            export_data = []
            for query in queries:
                query_dict = asdict(query)
                export_data.append(query_dict)
            
            # Save to file
            with open(file_path, 'w') as f:
                json.dump(export_data, f, indent=2)
            
            self.logger.info(f"Exported {len(queries)} queries from {collection_name} to {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export collection: {e}")
            return False
    
    def import_collection(self, collection_name: str, file_path: str) -> int:
        """
        Import queries from a JSON file to a collection
        
        Args:
            collection_name: Name of the collection to import to
            file_path: Path to the JSON file
            
        Returns:
            Number of queries imported
        """
        try:
            with open(file_path, 'r') as f:
                import_data = json.load(f)
            
            imported_count = 0
            for query_data in import_data:
                try:
                    if collection_name == "correct_queries":
                        self.store_correct_query(
                            nl_query=query_data['nl_query'],
                            sql_query=query_data['sql_query'],
                            metadata=query_data.get('metadata', {})
                        )
                    elif collection_name == "wrong_queries":
                        error_info = ErrorInfo(
                            error_type=query_data.get('error_type', 'unknown'),
                            error_message=query_data.get('error_message', ''),
                            error_code=query_data.get('error_code'),
                            stack_trace=query_data.get('stack_trace')
                        )
                        self.store_wrong_query(
                            nl_query=query_data['nl_query'],
                            sql_query=query_data['sql_query'],
                            error_info=error_info,
                            metadata=query_data.get('metadata', {})
                        )
                    imported_count += 1
                except Exception as e:
                    self.logger.warning(f"Failed to import query: {e}")
                    continue
            
            self.logger.info(f"Imported {imported_count} queries to {collection_name}")
            return imported_count
            
        except Exception as e:
            self.logger.error(f"Failed to import collection: {e}")
            return 0
