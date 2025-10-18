"""
Vector Database Manager for Error Correction Pipeline

This module manages the storage and retrieval of correct and wrong queries using a pluggable
vector backend. Default backend is FAISS with JSON persistence; ChromaDB can be optionally
enabled via configuration.
"""

import os
import json
import logging
import uuid
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss
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
    """Manages vector database operations for query storage and retrieval (FAISS/Chroma)"""
    
    def __init__(self, config: ErrorCorrectionConfig):
        """
        Initialize the VectorDBManager
        
        Args:
            config: Configuration object containing parameters
        """
        self.config = config
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.logger = logging.getLogger(__name__)
        self.backend = self.config.VECTOR_BACKEND.lower()
        self.logger.info(f"Initializing VectorDBManager with backend: {self.backend}")

        if self.backend == 'chroma':
            # Lazy import to avoid dependency if not used
            try:
                import chromadb
                from chromadb.config import Settings
                self._initialize_chromadb(chromadb, Settings)
                self._initialize_collections_chroma()
                self.mode = 'chroma'
            except Exception as e:
                self.logger.error(f"Chroma initialization failed: {e}. Falling back to FAISS.")
                self._initialize_faiss()
                self.mode = 'faiss'
        else:
            self._initialize_faiss()
            self.mode = 'faiss'
    
    def _initialize_chromadb(self, chromadb, Settings):
        """Initialize ChromaDB client (new-client style)."""
        db_path = os.path.join(self.config.DATA_DIR, "chroma_db")
        os.makedirs(db_path, exist_ok=True)
        # Newer chroma uses PersistentClient
        try:
            self.chroma_client = chromadb.PersistentClient(path=db_path, settings=Settings(anonymized_telemetry=False))
            self.logger.info("ChromaDB client initialized successfully (PersistentClient)")
        except Exception as e:
            # Fallback to legacy Client API if present (unlikely on new versions)
            self.chroma_client = chromadb.Client(Settings(chroma_db_impl="duckdb+parquet", persist_directory=db_path))
            self.logger.warning(f"Chroma PersistentClient failed, using legacy Client API: {e}")
    
    def _initialize_collections_chroma(self):
        """Initialize ChromaDB collections."""
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

    # ---------------- FAISS backend -----------------
    def _initialize_faiss(self):
        """Initialize FAISS indices and load persisted JSON data."""
        self.logger.info("Initializing FAISS backend with JSON persistence")
        dim = self.config.VECTOR_DIMENSION
        self.faiss_correct = faiss.IndexFlatIP(dim)
        self.faiss_wrong = faiss.IndexFlatIP(dim)
        self.correct_records: List[Dict[str, Any]] = []
        self.wrong_records: List[Dict[str, Any]] = []

        # Load persisted data
        self._faiss_load('correct')
        self._faiss_load('wrong')

    def _faiss_path(self, kind: str) -> str:
        if kind == 'correct':
            return os.path.join(self.config.CORRECT_QUERIES_DIR, 'queries.json')
        return os.path.join(self.config.WRONG_QUERIES_DIR, 'queries.json')

    def _faiss_save_atomic(self, path: str, data: Any):
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)

    def _normalize(self, v: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(v)
        if n == 0:
            return v
        return v / n

    def _faiss_load(self, kind: str):
        path = self._faiss_path(kind)
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if kind == 'correct':
                self.correct_records = data
                embs = []
                for r in data:
                    e = np.array(r.get('embedding') or [])
                    if e.size == self.config.VECTOR_DIMENSION:
                        embs.append(self._normalize(e).astype('float32'))
                if embs:
                    self.faiss_correct.add(np.vstack(embs))
            else:
                self.wrong_records = data
                embs = []
                for r in data:
                    e = np.array(r.get('embedding') or [])
                    if e.size == self.config.VECTOR_DIMENSION:
                        embs.append(self._normalize(e).astype('float32'))
                if embs:
                    self.faiss_wrong.add(np.vstack(embs))
        except Exception as e:
            self.logger.warning(f"Failed loading {kind} records: {e}")
    
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
            
            if self.mode == 'chroma':
                chroma_metadata = {
                    "query_id": query_id,
                    "nl_query": nl_query,
                    "sql_query": sql_query,
                    "query_type": "correct",
                    "execution_result": "success",
                    "timestamp": timestamp,
                    **(metadata or {})
                }
                self.correct_collection.add(
                    ids=[query_id],
                    embeddings=[embedding],
                    metadatas=[chroma_metadata],
                    documents=[combined_text]
                )
            else:
                emb = self._normalize(np.array(embedding, dtype='float32'))
                self.faiss_correct.add(emb.reshape(1, -1))
                record = {
                    'query_id': query_id,
                    'nl_query': nl_query,
                    'sql_query': sql_query,
                    'query_type': 'correct',
                    'execution_result': 'success',
                    'embedding': emb.tolist(),
                    'metadata': metadata or {},
                    'timestamp': timestamp
                }
                self.correct_records.append(record)
                self._faiss_save_atomic(self._faiss_path('correct'), self.correct_records)
            
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
            
            if self.mode == 'chroma':
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
                self.wrong_collection.add(
                    ids=[query_id],
                    embeddings=[embedding],
                    metadatas=[chroma_metadata],
                    documents=[combined_text]
                )
            else:
                emb = self._normalize(np.array(embedding, dtype='float32'))
                self.faiss_wrong.add(emb.reshape(1, -1))
                record = {
                    'query_id': query_id,
                    'nl_query': nl_query,
                    'sql_query': sql_query,
                    'query_type': 'wrong',
                    'execution_result': 'error',
                    'error_type': error_info.error_type,
                    'error_message': error_info.error_message,
                    'embedding': emb.tolist(),
                    'metadata': metadata or {},
                    'timestamp': timestamp
                }
                self.wrong_records.append(record)
                self._faiss_save_atomic(self._faiss_path('wrong'), self.wrong_records)
            
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
            # Generate normalized embedding
            qemb = self._normalize(np.array(self.embedding_model.encode(query), dtype='float32')).reshape(1, -1)
            similar_queries: List[Tuple[QueryRecord, float]] = []
            if collection_name == 'correct_queries':
                if self.mode == 'chroma':
                    results = self.correct_collection.query(query_embeddings=[qemb.tolist()[0]], n_results=top_k, include=['metadatas','distances'])
                    if results['ids'] and results['ids'][0]:
                        for i, (qid, metadata, distance) in enumerate(zip(results['ids'][0], results['metadatas'][0], results['distances'][0])):
                            similarity_score = 1 - distance
                            query_record = QueryRecord(
                                query_id=metadata.get('query_id', qid),
                                nl_query=metadata.get('nl_query', ''),
                                sql_query=metadata.get('sql_query', ''),
                                query_type=metadata.get('query_type', ''),
                                execution_result=metadata.get('execution_result'),
                                error_type=metadata.get('error_type'),
                                error_message=metadata.get('error_message'),
                                metadata={k: v for k, v in metadata.items() if k not in ['query_id','nl_query','sql_query','query_type','execution_result','error_type','error_message','timestamp']},
                                timestamp=metadata.get('timestamp')
                            )
                            similar_queries.append((query_record, float(similarity_score)))
                else:
                    if self.faiss_correct.ntotal == 0:
                        return []
                    D, I = self.faiss_correct.search(qemb, top_k)
                    for idx, sim in zip(I[0], D[0]):
                        if 0 <= idx < len(self.correct_records):
                            rec = self.correct_records[idx]
                            qr = QueryRecord(
                                query_id=rec['query_id'],
                                nl_query=rec['nl_query'],
                                sql_query=rec['sql_query'],
                                query_type='correct',
                                execution_result='success',
                                error_type=None,
                                error_message=None,
                                metadata=rec.get('metadata'),
                                timestamp=rec.get('timestamp')
                            )
                            similar_queries.append((qr, float(sim)))
            elif collection_name == 'wrong_queries':
                if self.mode == 'chroma':
                    results = self.wrong_collection.query(query_embeddings=[qemb.tolist()[0]], n_results=top_k, include=['metadatas','distances'])
                    if results['ids'] and results['ids'][0]:
                        for i, (qid, metadata, distance) in enumerate(zip(results['ids'][0], results['metadatas'][0], results['distances'][0])):
                            similarity_score = 1 - distance
                            query_record = QueryRecord(
                                query_id=metadata.get('query_id', qid),
                                nl_query=metadata.get('nl_query', ''),
                                sql_query=metadata.get('sql_query', ''),
                                query_type=metadata.get('query_type', ''),
                                execution_result=metadata.get('execution_result'),
                                error_type=metadata.get('error_type'),
                                error_message=metadata.get('error_message'),
                                metadata={k: v for k, v in metadata.items() if k not in ['query_id','nl_query','sql_query','query_type','execution_result','error_type','error_message','timestamp']},
                                timestamp=metadata.get('timestamp')
                            )
                            similar_queries.append((query_record, float(similarity_score)))
                else:
                    if self.faiss_wrong.ntotal == 0:
                        return []
                    D, I = self.faiss_wrong.search(qemb, top_k)
                    for idx, sim in zip(I[0], D[0]):
                        if 0 <= idx < len(self.wrong_records):
                            rec = self.wrong_records[idx]
                            qr = QueryRecord(
                                query_id=rec['query_id'],
                                nl_query=rec['nl_query'],
                                sql_query=rec['sql_query'],
                                query_type='wrong',
                                execution_result='error',
                                error_type=rec.get('error_type'),
                                error_message=rec.get('error_message'),
                                metadata=rec.get('metadata'),
                                timestamp=rec.get('timestamp')
                            )
                            similar_queries.append((qr, float(sim)))
            else:
                raise ValueError(f"Invalid collection name: {collection_name}")

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
            if collection_name == 'correct_queries':
                if self.mode == 'chroma':
                    count = self.correct_collection.count()
                else:
                    count = len(self.correct_records)
            elif collection_name == 'wrong_queries':
                if self.mode == 'chroma':
                    count = self.wrong_collection.count()
                else:
                    count = len(self.wrong_records)
            else:
                raise ValueError(f"Invalid collection name: {collection_name}")
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
            if self.mode == 'chroma':
                if collection_name == 'correct_queries':
                    results = self.correct_collection.get(ids=[query_id], include=['metadatas'])
                elif collection_name == 'wrong_queries':
                    results = self.wrong_collection.get(ids=[query_id], include=['metadatas'])
                else:
                    raise ValueError(f"Invalid collection name: {collection_name}")
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
                        metadata={k: v for k, v in metadata.items() if k not in ['query_id','nl_query','sql_query','query_type','execution_result','error_type','error_message','timestamp']},
                        timestamp=metadata.get('timestamp')
                    )
                return None
            else:
                records = self.correct_records if collection_name == 'correct_queries' else self.wrong_records
                for rec in records:
                    if rec.get('query_id') == query_id:
                        return QueryRecord(
                            query_id=rec['query_id'],
                            nl_query=rec['nl_query'],
                            sql_query=rec['sql_query'],
                            query_type=rec['query_type'],
                            execution_result=rec.get('execution_result'),
                            error_type=rec.get('error_type'),
                            error_message=rec.get('error_message'),
                            metadata=rec.get('metadata'),
                            timestamp=rec.get('timestamp')
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
            queries: List[QueryRecord] = []
            if self.mode == 'chroma':
                if collection_name == 'correct_queries':
                    results = self.correct_collection.get(include=['metadatas'], limit=limit)
                elif collection_name == 'wrong_queries':
                    results = self.wrong_collection.get(include=['metadatas'], limit=limit)
                else:
                    raise ValueError(f"Invalid collection name: {collection_name}")
                if results['ids']:
                    for i, query_id in enumerate(results['ids']):
                        metadata = results['metadatas'][i]
                        queries.append(QueryRecord(
                            query_id=metadata.get('query_id', query_id),
                            nl_query=metadata.get('nl_query', ''),
                            sql_query=metadata.get('sql_query', ''),
                            query_type=metadata.get('query_type', ''),
                            execution_result=metadata.get('execution_result'),
                            error_type=metadata.get('error_type'),
                            error_message=metadata.get('error_message'),
                            metadata={k: v for k, v in metadata.items() if k not in ['query_id','nl_query','sql_query','query_type','execution_result','error_type','error_message','timestamp']},
                            timestamp=metadata.get('timestamp')
                        ))
            else:
                records = self.correct_records if collection_name == 'correct_queries' else self.wrong_records
                for rec in records[:limit or len(records)]:
                    queries.append(QueryRecord(
                        query_id=rec['query_id'],
                        nl_query=rec['nl_query'],
                        sql_query=rec['sql_query'],
                        query_type=rec['query_type'],
                        execution_result=rec.get('execution_result'),
                        error_type=rec.get('error_type'),
                        error_message=rec.get('error_message'),
                        metadata=rec.get('metadata'),
                        timestamp=rec.get('timestamp')
                    ))
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
            if self.mode == 'chroma':
                if collection_name == 'correct_queries':
                    self.correct_collection.delete(ids=[query_id])
                elif collection_name == 'wrong_queries':
                    self.wrong_collection.delete(ids=[query_id])
                else:
                    raise ValueError(f"Invalid collection name: {collection_name}")
            else:
                if collection_name == 'correct_queries':
                    self.correct_records = [r for r in self.correct_records if r.get('query_id') != query_id]
                    self._faiss_save_atomic(self._faiss_path('correct'), self.correct_records)
                    # Note: FAISS doesn't support removing individual vectors in IndexFlat; would rebuild as needed.
                elif collection_name == 'wrong_queries':
                    self.wrong_records = [r for r in self.wrong_records if r.get('query_id') != query_id]
                    self._faiss_save_atomic(self._faiss_path('wrong'), self.wrong_records)
                else:
                    raise ValueError(f"Invalid collection name: {collection_name}")
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
            correct_count = self.get_query_count('correct_queries')
            wrong_count = self.get_query_count('wrong_queries')
            return {
                'total_correct_queries': correct_count,
                'total_wrong_queries': wrong_count,
                'total_queries': correct_count + wrong_count,
                'backend': self.mode,
                'collections': {
                    'correct_queries': correct_count,
                    'wrong_queries': wrong_count
                }
            }
        except Exception as e:
            self.logger.error(f"Failed to get statistics: {e}")
            return {'total_correct_queries': 0, 'total_wrong_queries': 0, 'total_queries': 0, 'error': str(e)}
    
    def clear_collection(self, collection_name: str) -> bool:
        """
        Clear all queries from the specified collection
        
        Args:
            collection_name: Name of the collection to clear
            
        Returns:
            True if cleared successfully, False otherwise
        """
        try:
            if self.mode == 'chroma':
                if collection_name == 'correct_queries':
                    results = self.correct_collection.get(include=[])
                    if results['ids']:
                        self.correct_collection.delete(ids=results['ids'])
                elif collection_name == 'wrong_queries':
                    results = self.wrong_collection.get(include=[])
                    if results['ids']:
                        self.wrong_collection.delete(ids=results['ids'])
                else:
                    raise ValueError(f"Invalid collection name: {collection_name}")
            else:
                if collection_name == 'correct_queries':
                    self.correct_records = []
                    self.faiss_correct.reset()
                    self._faiss_save_atomic(self._faiss_path('correct'), self.correct_records)
                elif collection_name == 'wrong_queries':
                    self.wrong_records = []
                    self.faiss_wrong.reset()
                    self._faiss_save_atomic(self._faiss_path('wrong'), self.wrong_records)
                else:
                    raise ValueError(f"Invalid collection name: {collection_name}")
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
            export_data = [asdict(q) for q in queries]
            with open(file_path, 'w', encoding='utf-8') as f:
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
