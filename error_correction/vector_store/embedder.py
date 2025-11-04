"""
SQL Query Embedder using CodeBERT or similar SQL-specific models
"""
import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel
from typing import List, Union
import logging

from error_correction.config import (
    SQL_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    MAX_SEQUENCE_LENGTH
)

logger = logging.getLogger(__name__)


class SQLEmbedder:
    """
    Generates embeddings for SQL queries using pre-trained code models.
    Supports models like CodeBERT, GraphCodeBERT, CodeT5, etc.
    """

    def __init__(self, model_name: str = None, device: str = None):
        """
        Initialize the SQL embedder.

        Args:
            model_name: HuggingFace model name (default: from config)
            device: Device to run model on (default: auto-detect)
                   Can be: 'cuda', 'cpu', 'xpu' (Intel Arc), or 'auto'
        """
        self.model_name = model_name or SQL_EMBEDDING_MODEL
        self.max_length = MAX_SEQUENCE_LENGTH

        # Auto-detect device if not specified
        if device is None or device == 'auto':
            self.device = self._auto_detect_device()
        else:
            self.device = device

        logger.info(f"Loading SQL embedding model: {self.model_name}")
        logger.info(f"Using device: {self.device}")

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModel.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()
            logger.info("Model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def _auto_detect_device(self) -> str:
        """
        Auto-detect the best available device.
        Supports: CUDA (NVIDIA), XPU (Intel Arc), CPU

        Returns:
            Device string
        """
        # Try Intel Extension for PyTorch (Intel Arc GPU)
        try:
            import intel_extension_for_pytorch as ipex
            if hasattr(torch, 'xpu') and torch.xpu.is_available():
                logger.info("Intel Arc GPU (XPU) detected via ipex")
                return 'xpu'
        except ImportError:
            pass

        # Try CUDA (NVIDIA GPU)
        if torch.cuda.is_available():
            logger.info("CUDA GPU detected")
            return 'cuda'

        # Fallback to CPU
        logger.info("No GPU detected, using CPU")
        return 'cpu'

    def normalize_sql(self, sql: str) -> str:
        """
        Normalize SQL query for consistent embedding.

        Args:
            sql: Raw SQL query string

        Returns:
            Normalized SQL query
        """
        # Remove extra whitespace
        sql = ' '.join(sql.split())
        # Convert to uppercase for consistency (optional)
        # sql = sql.upper()
        return sql

    def embed_query(self, sql: str) -> np.ndarray:
        """
        Generate embedding for a single SQL query.

        Args:
            sql: SQL query string

        Returns:
            Embedding vector as numpy array
        """
        sql = self.normalize_sql(sql)

        try:
            # Tokenize
            inputs = self.tokenizer(
                sql,
                max_length=self.max_length,
                padding='max_length',
                truncation=True,
                return_tensors='pt'
            )

            # Move to device
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Generate embedding
            with torch.no_grad():
                outputs = self.model(**inputs)
                # Use [CLS] token embedding (first token)
                embedding = outputs.last_hidden_state[:, 0, :].cpu().numpy()

            return embedding.flatten()

        except Exception as e:
            logger.error(f"Error embedding query '{sql[:50]}...': {e}")
            # Return zero vector on error
            return np.zeros(EMBEDDING_DIMENSION)

    def embed_batch(self, sqls: List[str], batch_size: int = 32) -> np.ndarray:
        """
        Generate embeddings for a batch of SQL queries.

        Args:
            sqls: List of SQL query strings
            batch_size: Batch size for processing

        Returns:
            Matrix of embeddings (n_queries x embedding_dim)
        """
        embeddings = []

        # Normalize all queries
        sqls = [self.normalize_sql(sql) for sql in sqls]

        # Process in batches
        for i in range(0, len(sqls), batch_size):
            batch = sqls[i:i + batch_size]

            try:
                # Tokenize batch
                inputs = self.tokenizer(
                    batch,
                    max_length=self.max_length,
                    padding='max_length',
                    truncation=True,
                    return_tensors='pt'
                )

                # Move to device
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

                # Generate embeddings
                with torch.no_grad():
                    outputs = self.model(**inputs)
                    # Use [CLS] token embeddings
                    batch_embeddings = outputs.last_hidden_state[:, 0, :].cpu().numpy()

                embeddings.append(batch_embeddings)

            except Exception as e:
                logger.error(f"Error embedding batch starting at index {i}: {e}")
                # Add zero vectors for failed batch
                batch_embeddings = np.zeros((len(batch), EMBEDDING_DIMENSION))
                embeddings.append(batch_embeddings)

        return np.vstack(embeddings)

    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0 to 1)
        """
        # Normalize vectors
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        # Compute cosine similarity
        similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)
        return float(similarity)

    def find_most_similar(
        self,
        query_embedding: np.ndarray,
        candidate_embeddings: np.ndarray,
        top_k: int = 5
    ) -> List[int]:
        """
        Find most similar queries from a set of candidates.

        Args:
            query_embedding: Query embedding vector
            candidate_embeddings: Matrix of candidate embeddings
            top_k: Number of top similar queries to return

        Returns:
            Indices of top-k most similar queries
        """
        # Compute cosine similarities
        similarities = []
        for candidate in candidate_embeddings:
            sim = self.compute_similarity(query_embedding, candidate)
            similarities.append(sim)

        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]
        return top_indices.tolist()
