"""
Vector Database Manager using FAISS for efficient similarity search
"""
import os
import json
import pickle
import numpy as np
import faiss
from typing import List, Dict, Tuple, Optional
import logging
from datetime import datetime

from error_correction.config import (
    CORRECT_QUERIES_DB_PATH,
    INCORRECT_QUERIES_DB_PATH,
    EMBEDDING_DIMENSION,
    FAISS_INDEX_TYPE,
    SIMILARITY_METRIC
)

logger = logging.getLogger(__name__)


class VectorDatabase:
    """
    Manages storage and retrieval of SQL queries using FAISS vector database.
    Supports separate storage for correct and incorrect queries.
    """

    def __init__(
        self,
        db_path: str,
        embedding_dim: int = EMBEDDING_DIMENSION,
        index_type: str = FAISS_INDEX_TYPE
    ):
        """
        Initialize the vector database.

        Args:
            db_path: Path to store the database
            embedding_dim: Dimension of embedding vectors
            index_type: Type of FAISS index to use
        """
        self.db_path = db_path
        self.embedding_dim = embedding_dim
        self.index_type = index_type

        # Create directory if it doesn't exist
        os.makedirs(db_path, exist_ok=True)

        # Paths for storing components
        self.index_file = os.path.join(db_path, "faiss.index")
        self.metadata_file = os.path.join(db_path, "metadata.json")
        self.queries_file = os.path.join(db_path, "queries.pkl")

        # Initialize or load index
        self.index = self._create_or_load_index()
        self.queries = self._load_queries()
        self.metadata = self._load_metadata()

        logger.info(f"Vector database initialized at {db_path}")
        logger.info(f"Current size: {self.size()} queries")

    def _create_or_load_index(self) -> faiss.Index:
        """Create a new FAISS index or load existing one."""
        if os.path.exists(self.index_file):
            logger.info(f"Loading existing FAISS index from {self.index_file}")
            return faiss.read_index(self.index_file)
        else:
            logger.info(f"Creating new FAISS index of type {self.index_type}")
            if self.index_type == "Flat":
                # L2 distance by default, we'll normalize for cosine similarity
                index = faiss.IndexFlatL2(self.embedding_dim)
            elif self.index_type == "IVFFlat":
                quantizer = faiss.IndexFlatL2(self.embedding_dim)
                index = faiss.IndexIVFFlat(quantizer, self.embedding_dim, 100)
            else:
                # Default to Flat index
                index = faiss.IndexFlatL2(self.embedding_dim)
            return index

    def _load_queries(self) -> List[Dict]:
        """Load stored queries."""
        if os.path.exists(self.queries_file):
            with open(self.queries_file, 'rb') as f:
                return pickle.load(f)
        return []

    def _load_metadata(self) -> Dict:
        """Load metadata."""
        if os.path.exists(self.metadata_file):
            with open(self.metadata_file, 'r') as f:
                return json.load(f)
        return {
            "created_at": datetime.now().isoformat(),
            "total_queries": 0,
            "last_updated": datetime.now().isoformat()
        }

    def _save_index(self):
        """Save FAISS index to disk."""
        faiss.write_index(self.index, self.index_file)
        logger.debug(f"Saved FAISS index to {self.index_file}")

    def _save_queries(self):
        """Save queries to disk."""
        with open(self.queries_file, 'wb') as f:
            pickle.dump(self.queries, f)
        logger.debug(f"Saved queries to {self.queries_file}")

    def _save_metadata(self):
        """Save metadata to disk."""
        self.metadata["last_updated"] = datetime.now().isoformat()
        self.metadata["total_queries"] = len(self.queries)
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)
        logger.debug(f"Saved metadata to {self.metadata_file}")

    def normalize_vector(self, vector: np.ndarray) -> np.ndarray:
        """Normalize vector for cosine similarity."""
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm

    def add_query(
        self,
        sql: str,
        embedding: np.ndarray,
        metadata: Dict = None
    ) -> int:
        """
        Add a query to the database.

        Args:
            sql: SQL query string
            embedding: Query embedding vector
            metadata: Additional metadata (db_id, question, gold_sql, etc.)

        Returns:
            Index of added query
        """
        # Normalize embedding for cosine similarity
        normalized_embedding = self.normalize_vector(embedding.copy())

        # Add to FAISS index
        self.index.add(normalized_embedding.reshape(1, -1).astype('float32'))

        # Store query and metadata
        query_data = {
            "sql": sql,
            "metadata": metadata or {},
            "added_at": datetime.now().isoformat()
        }
        self.queries.append(query_data)

        # Save to disk
        self._save_index()
        self._save_queries()
        self._save_metadata()

        query_idx = len(self.queries) - 1
        logger.debug(f"Added query at index {query_idx}: {sql[:50]}...")
        return query_idx

    def add_batch(
        self,
        sqls: List[str],
        embeddings: np.ndarray,
        metadatas: List[Dict] = None
    ) -> List[int]:
        """
        Add multiple queries in batch.

        Args:
            sqls: List of SQL query strings
            embeddings: Matrix of embeddings (n_queries x embedding_dim)
            metadatas: List of metadata dicts

        Returns:
            List of indices for added queries
        """
        if metadatas is None:
            metadatas = [{}] * len(sqls)

        # Normalize embeddings
        normalized_embeddings = np.array([
            self.normalize_vector(emb) for emb in embeddings
        ]).astype('float32')

        # Add to FAISS index
        self.index.add(normalized_embeddings)

        # Store queries and metadata
        indices = []
        for sql, metadata in zip(sqls, metadatas):
            query_data = {
                "sql": sql,
                "metadata": metadata,
                "added_at": datetime.now().isoformat()
            }
            self.queries.append(query_data)
            indices.append(len(self.queries) - 1)

        # Save to disk
        self._save_index()
        self._save_queries()
        self._save_metadata()

        logger.info(f"Added {len(sqls)} queries in batch")
        return indices

    def search(
        self,
        query_embedding: np.ndarray,
        k: int = 5,
        return_distances: bool = True
    ) -> Tuple[List[Dict], Optional[List[float]]]:
        """
        Search for similar queries.

        Args:
            query_embedding: Query embedding vector
            k: Number of results to return
            return_distances: Whether to return similarity scores

        Returns:
            Tuple of (list of query dicts, list of distances)
        """
        if self.size() == 0:
            return [], [] if return_distances else None

        # Normalize query embedding
        normalized_query = self.normalize_vector(query_embedding.copy())

        # Search in FAISS index
        k = min(k, self.size())  # Don't search for more than available
        distances, indices = self.index.search(
            normalized_query.reshape(1, -1).astype('float32'),
            k
        )

        # Convert L2 distances to cosine similarity scores
        # For normalized vectors: cosine_sim = 1 - (L2_dist^2 / 2)
        similarities = 1 - (distances[0] ** 2 / 2)

        # Retrieve queries
        results = []
        for idx in indices[0]:
            if idx < len(self.queries):
                results.append(self.queries[idx])

        if return_distances:
            return results, similarities.tolist()
        return results, None

    def get_query(self, index: int) -> Optional[Dict]:
        """
        Get query by index.

        Args:
            index: Query index

        Returns:
            Query dict or None if index out of range
        """
        if 0 <= index < len(self.queries):
            return self.queries[index]
        return None

    def get_all_queries(self) -> List[Dict]:
        """Get all stored queries."""
        return self.queries.copy()

    def get_all_embeddings(self) -> np.ndarray:
        """
        Get all embeddings from the index.

        Returns:
            Matrix of all embeddings
        """
        if self.size() == 0:
            return np.array([]).reshape(0, self.embedding_dim)

        # Reconstruct vectors from index
        return faiss.vector_to_array(self.index.reconstruct_n(0, self.size())).reshape(-1, self.embedding_dim)

    def size(self) -> int:
        """Get number of queries in database."""
        return self.index.ntotal

    def clear(self):
        """Clear all data from the database."""
        self.index.reset()
        self.queries = []
        self.metadata = {
            "created_at": datetime.now().isoformat(),
            "total_queries": 0,
            "last_updated": datetime.now().isoformat()
        }
        self._save_index()
        self._save_queries()
        self._save_metadata()
        logger.info("Database cleared")


class CorrectQueriesDB(VectorDatabase):
    """Vector database for correct queries."""

    def __init__(self):
        super().__init__(CORRECT_QUERIES_DB_PATH)


class IncorrectQueriesDB(VectorDatabase):
    """Vector database for incorrect queries."""

    def __init__(self):
        super().__init__(INCORRECT_QUERIES_DB_PATH)
