"""
Clustering Manager for Error Correction Pipeline

This module handles hierarchical clustering of query-explanation-rule triplets.
It provides functionality to group similar queries and their associated explanations and rules.
"""

import os
import json
import numpy as np
import logging
import uuid
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from .config import ErrorCorrectionConfig
from .vector_db_manager import QueryRecord
from .llm_explainer import Explanation
from .rule_generator import GeneratedRule


@dataclass
class QueryTriplet:
    """Data class for query-explanation-rule triplets"""
    triplet_id: str
    query_record: QueryRecord
    explanation: Explanation
    rule: Optional[GeneratedRule] = None
    cluster_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None


@dataclass
class Cluster:
    """Data class for clusters"""
    cluster_id: str
    triplets: List[QueryTriplet]
    centroid: Optional[np.ndarray] = None
    size: int = 0
    average_similarity: float = 0.0
    dominant_error_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None


@dataclass
class TripletData:
    """Data class for storing triplet information in JSON format"""
    triplet_id: str
    nl_query: str
    sql_query: str
    explanation: Dict[str, Any]
    rule: Optional[Dict[str, Any]] = None
    error_type: str = ""
    timestamp: str = ""
    database_schema: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TripletManager:
    """Manager for storing and managing query-explanation-rule triplets in JSON format"""
    
    def __init__(self, config: ErrorCorrectionConfig):
        """
        Initialize the TripletManager
        
        Args:
            config: Configuration object containing parameters
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.triplets: List[TripletData] = []
        self.triplet_count: int = 0
        self._load_triplets()
    
    def add_triplet(self, nl_query: str, sql_query: str, explanation: Explanation, 
                   rule: Optional[GeneratedRule] = None, database_schema: Optional[str] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Add a new triplet to the collection
        
        Args:
            nl_query: Natural language query
            sql_query: SQL query
            explanation: Explanation object
            rule: Optional GeneratedRule object
            database_schema: Optional database schema information
            metadata: Optional additional metadata
            
        Returns:
            triplet_id: Unique identifier for the triplet
        """
        triplet_id = f"triplet_{self.triplet_count}_{int(datetime.now().timestamp())}"
        
        # Convert explanation to dictionary
        explanation_dict = {
            'explanation_id': explanation.explanation_id,
            'query_id': explanation.query_id,
            'query_text': explanation.query_text,
            'error_type': explanation.error_type,
            'explanation_text': explanation.explanation_text,
            'confidence': explanation.confidence,
            'suggested_fix': explanation.suggested_fix,
            'metadata': explanation.metadata,
            'created_at': explanation.created_at
        }
        
        # Convert rule to dictionary if provided
        rule_dict = None
        if rule:
            rule_dict = {
                'rule_id': rule.rule_id,
                'request_id': rule.request_id,
                'explanation_id': rule.explanation_id,
                'rule_type': rule.rule_type,
                'pattern': rule.pattern,
                'replacement': rule.replacement,
                'description': rule.description,
                'confidence': rule.confidence,
                'conditions': rule.conditions,
                'metadata': rule.metadata,
                'created_at': rule.created_at,
                'validation_passed': rule.validation_passed,
                'test_results': rule.test_results
            }
        
        # Create triplet data
        triplet_data = TripletData(
            triplet_id=triplet_id,
            nl_query=nl_query,
            sql_query=sql_query,
            explanation=explanation_dict,
            rule=rule_dict,
            error_type=explanation.error_type,
            timestamp=datetime.now().isoformat(),
            database_schema=database_schema,
            metadata=metadata or {}
        )
        
        # Add to collection
        self.triplets.append(triplet_data)
        self.triplet_count += 1
        
        # Save to disk
        self._save_triplets()
        
        self.logger.info(f"Added triplet {triplet_id} with error type: {explanation.error_type}")
        
        return triplet_id
    
    def get_triplet_count(self) -> int:
        """
        Get the total number of triplets
        
        Returns:
            int: Number of triplets in the collection
        """
        return len(self.triplets)
    
    def get_all_triplets(self) -> List[Dict[str, Any]]:
        """
        Get all triplets as a list of dictionaries
        
        Returns:
            List of dictionaries containing triplet data
        """
        return [asdict(triplet) for triplet in self.triplets]
    
    def clear_triplets(self) -> None:
        """
        Clear all triplets (typically called after successful clustering)
        """
        self.triplets = []
        self.triplet_count = 0
        
        # Remove the triplets file
        triplets_file = os.path.join(self.config.TRIPLETS_DIR, "triplets_data.json")
        if os.path.exists(triplets_file):
            os.remove(triplets_file)
        
        self.logger.info("Cleared all triplets")
    
    def save_triplets_to_disk(self, filepath: str) -> bool:
        """
        Save triplets to a specific file path
        
        Args:
            filepath: Path to save the triplets file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Convert triplets to serializable format
            triplets_data = []
            for triplet in self.triplets:
                triplet_dict = {
                    'triplet_id': triplet.triplet_id,
                    'nl_query': triplet.nl_query,
                    'sql_query': triplet.sql_query,
                    'explanation': triplet.explanation,
                    'rule': triplet.rule,
                    'error_type': triplet.error_type,
                    'timestamp': triplet.timestamp,
                    'database_schema': triplet.database_schema,
                    'metadata': triplet.metadata
                }
                triplets_data.append(triplet_dict)
            
            # Save to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(triplets_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Saved {len(triplets_data)} triplets to {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save triplets to {filepath}: {e}")
            return False
    
    def load_triplets_from_disk(self, filepath: str) -> bool:
        """
        Load triplets from a specific file path
        
        Args:
            filepath: Path to load the triplets file from
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not os.path.exists(filepath):
                self.logger.warning(f"Triplets file not found: {filepath}")
                return False
            
            with open(filepath, 'r', encoding='utf-8') as f:
                triplets_data = json.load(f)
            
            # Clear existing triplets
            self.triplets = []
            self.triplet_count = 0
            
            # Load triplets from data
            for triplet_dict in triplets_data:
                triplet = TripletData(
                    triplet_id=triplet_dict['triplet_id'],
                    nl_query=triplet_dict['nl_query'],
                    sql_query=triplet_dict['sql_query'],
                    explanation=triplet_dict['explanation'],
                    rule=triplet_dict.get('rule'),
                    error_type=triplet_dict.get('error_type', ''),
                    timestamp=triplet_dict.get('timestamp', ''),
                    database_schema=triplet_dict.get('database_schema'),
                    metadata=triplet_dict.get('metadata', {})
                )
                self.triplets.append(triplet)
                self.triplet_count += 1
            
            self.logger.info(f"Loaded {len(self.triplets)} triplets from {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load triplets from {filepath}: {e}")
            return False
    
    def get_triplets_by_error_type(self, error_type: str) -> List[Dict[str, Any]]:
        """
        Get triplets filtered by error type
        
        Args:
            error_type: Error type to filter by
            
        Returns:
            List of triplets matching the error type
        """
        filtered_triplets = [triplet for triplet in self.triplets if triplet.error_type == error_type]
        return [asdict(triplet) for triplet in filtered_triplets]
    
    def get_triplets_by_database_schema(self, database_schema: str) -> List[Dict[str, Any]]:
        """
        Get triplets filtered by database schema
        
        Args:
            database_schema: Database schema to filter by
            
        Returns:
            List of triplets matching the database schema
        """
        filtered_triplets = [triplet for triplet in self.triplets if triplet.database_schema == database_schema]
        return [asdict(triplet) for triplet in filtered_triplets]
    
    def get_triplet_by_id(self, triplet_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific triplet by ID
        
        Args:
            triplet_id: ID of the triplet to retrieve
            
        Returns:
            Triplet data dictionary or None if not found
        """
        for triplet in self.triplets:
            if triplet.triplet_id == triplet_id:
                return asdict(triplet)
        return None
    
    def get_triplet_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the triplets
        
        Returns:
            Dictionary containing triplet statistics
        """
        if not self.triplets:
            return {
                'total_triplets': 0,
                'triplets_by_error_type': {},
                'triplets_by_database_schema': {},
                'triplets_with_rules': 0,
                'triplets_without_rules': 0
            }
        
        # Count by error type
        error_type_counts = {}
        database_schema_counts = {}
        triplets_with_rules = 0
        triplets_without_rules = 0
        
        for triplet in self.triplets:
            # Count by error type
            error_type = triplet.error_type or 'unknown'
            error_type_counts[error_type] = error_type_counts.get(error_type, 0) + 1
            
            # Count by database schema
            if triplet.database_schema:
                database_schema_counts[triplet.database_schema] = database_schema_counts.get(triplet.database_schema, 0) + 1
            
            # Count rules
            if triplet.rule:
                triplets_with_rules += 1
            else:
                triplets_without_rules += 1
        
        return {
            'total_triplets': len(self.triplets),
            'triplets_by_error_type': error_type_counts,
            'triplets_by_database_schema': database_schema_counts,
            'triplets_with_rules': triplets_with_rules,
            'triplets_without_rules': triplets_without_rules,
            'rule_coverage_percentage': (triplets_with_rules / len(self.triplets)) * 100 if self.triplets else 0
        }
    
    def export_triplets(self, filepath: str, format: str = 'json') -> bool:
        """
        Export triplets to a file in specified format
        
        Args:
            filepath: Path to export file
            format: Export format ('json' or 'csv')
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if format.lower() == 'json':
                return self.save_triplets_to_disk(filepath)
            elif format.lower() == 'csv':
                import pandas as pd
                
                # Convert to DataFrame
                data = []
                for triplet in self.triplets:
                    row = {
                        'triplet_id': triplet.triplet_id,
                        'nl_query': triplet.nl_query,
                        'sql_query': triplet.sql_query,
                        'error_type': triplet.error_type,
                        'timestamp': triplet.timestamp,
                        'database_schema': triplet.database_schema,
                        'has_rule': triplet.rule is not None,
                        'explanation_id': triplet.explanation.get('explanation_id', ''),
                        'rule_id': triplet.rule.get('rule_id', '') if triplet.rule else ''
                    }
                    data.append(row)
                
                df = pd.DataFrame(data)
                df.to_csv(filepath, index=False)
                self.logger.info(f"Exported {len(data)} triplets to CSV: {filepath}")
                return True
            else:
                self.logger.error(f"Unsupported export format: {format}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to export triplets: {e}")
            return False
    
    def _load_triplets(self):
        """Load triplets from default location"""
        triplets_file = os.path.join(self.config.TRIPLETS_DIR, "triplets_data.json")
        if os.path.exists(triplets_file):
            self.load_triplets_from_disk(triplets_file)
    
    def _save_triplets(self):
        """Save triplets to default location"""
        triplets_file = os.path.join(self.config.TRIPLETS_DIR, "triplets_data.json")
        self.save_triplets_to_disk(triplets_file)


class ClusteringManager:
    """Manager for hierarchical clustering of query-explanation-rule triplets"""
    
    def __init__(self, config: ErrorCorrectionConfig):
        """
        Initialize the ClusteringManager
        
        Args:
            config: Configuration object containing parameters
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.clusters: List[Cluster] = []
        self.triplets: List[QueryTriplet] = []
        self._load_triplets()
        self._load_clusters()
    
    def _load_triplets(self):
        """Load existing triplets from disk"""
        triplets_file = os.path.join(self.config.TRIPLETS_DIR, "triplets.json")
        if os.path.exists(triplets_file):
            try:
                with open(triplets_file, 'r') as f:
                    data = json.load(f)
                    for triplet_data in data:
                        # Reconstruct objects from data
                        query_record = QueryRecord(
                            query_id=triplet_data['query_record']['query_id'],
                            query_text=triplet_data['query_record']['query_text'],
                            query_type=triplet_data['query_record']['query_type'],
                            embedding=np.array(triplet_data['query_record']['embedding']) if triplet_data['query_record']['embedding'] else None,
                            metadata=triplet_data['query_record'].get('metadata'),
                            timestamp=triplet_data['query_record'].get('timestamp')
                        )
                        
                        explanation = Explanation(
                            explanation_id=triplet_data['explanation']['explanation_id'],
                            query_id=triplet_data['explanation']['query_id'],
                            query_text=triplet_data['explanation']['query_text'],
                            error_type=triplet_data['explanation']['error_type'],
                            explanation_text=triplet_data['explanation']['explanation_text'],
                            confidence=triplet_data['explanation']['confidence'],
                            suggested_fix=triplet_data['explanation'].get('suggested_fix'),
                            metadata=triplet_data['explanation'].get('metadata'),
                            created_at=triplet_data['explanation'].get('created_at')
                        )
                        
                        rule = None
                        if triplet_data.get('rule'):
                            from .rule_generator import GeneratedRule
                            from .rule_engine import RuleType
                            rule = GeneratedRule(
                                rule_id=triplet_data['rule']['rule_id'],
                                request_id=triplet_data['rule']['request_id'],
                                explanation_id=triplet_data['rule']['explanation_id'],
                                rule_type=RuleType(triplet_data['rule']['rule_type']),
                                pattern=triplet_data['rule']['pattern'],
                                replacement=triplet_data['rule']['replacement'],
                                description=triplet_data['rule']['description'],
                                confidence=triplet_data['rule']['confidence'],
                                conditions=triplet_data['rule'].get('conditions'),
                                metadata=triplet_data['rule'].get('metadata'),
                                created_at=triplet_data['rule'].get('created_at')
                            )
                        
                        triplet = QueryTriplet(
                            triplet_id=triplet_data['triplet_id'],
                            query_record=query_record,
                            explanation=explanation,
                            rule=rule,
                            cluster_id=triplet_data.get('cluster_id'),
                            metadata=triplet_data.get('metadata'),
                            created_at=triplet_data.get('created_at')
                        )
                        
                        self.triplets.append(triplet)
            except Exception as e:
                print(f"Warning: Could not load triplets: {e}")
    
    def _load_clusters(self):
        """Load existing clusters from disk"""
        clusters_file = os.path.join(self.config.TRIPLETS_DIR, "clusters.json")
        if os.path.exists(clusters_file):
            try:
                with open(clusters_file, 'r') as f:
                    data = json.load(f)
                    for cluster_data in data:
                        # Reconstruct cluster from data
                        cluster = Cluster(
                            cluster_id=cluster_data['cluster_id'],
                            triplets=[],  # Will be populated from triplets
                            centroid=np.array(cluster_data['centroid']) if cluster_data.get('centroid') else None,
                            size=cluster_data['size'],
                            average_similarity=cluster_data['average_similarity'],
                            dominant_error_type=cluster_data.get('dominant_error_type'),
                            metadata=cluster_data.get('metadata'),
                            created_at=cluster_data.get('created_at')
                        )
                        self.clusters.append(cluster)
            except Exception as e:
                print(f"Warning: Could not load clusters: {e}")
    
    def create_triplet(self, query_record: QueryRecord, explanation: Explanation, 
                      rule: Optional[GeneratedRule] = None) -> QueryTriplet:
        """
        Create a new triplet from query, explanation, and rule
        
        Args:
            query_record: QueryRecord object
            explanation: Explanation object
            rule: Optional GeneratedRule object
            
        Returns:
            QueryTriplet object
        """
        triplet = QueryTriplet(
            triplet_id=f"triplet_{len(self.triplets)}",
            query_record=query_record,
            explanation=explanation,
            rule=rule,
            metadata={'created_by': 'clustering_manager'},
            created_at=self._get_timestamp()
        )
        
        self.triplets.append(triplet)
        self._save_triplets()
        
        return triplet
    
    def cluster_triplets(self, triplets: List[TripletData], n_clusters: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Cluster triplets using hierarchical clustering with rule similarity validation
        
        Args:
            triplets: List of TripletData objects to cluster
            n_clusters: Number of clusters to create (if None, will use iterative merging)
            
        Returns:
            List of cluster dictionaries with combined rules and validation results
        """
        if len(triplets) < 10:
            self.logger.warning(f"Need at least 10 triplets for clustering, got {len(triplets)}")
            return []
        
        self.logger.info(f"Starting clustering of {len(triplets)} triplets")
        
        # Use the new iterative cluster merging method
        validated_clusters = self.iterative_cluster_merging(triplets, self.config.A_PERCENT_THRESHOLD)
        
        self.logger.info(f"Created {len(validated_clusters)} validated clusters")
        return validated_clusters
    
    def get_cluster_representative(self, cluster: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get the most central query in a cluster
        
        Args:
            cluster: Cluster dictionary containing triplets
            
        Returns:
            Dictionary containing the most representative triplet
        """
        triplets = cluster['triplets']
        if len(triplets) == 1:
            return triplets[0]
        
        # Calculate centroid of cluster embeddings
        embeddings = cluster['embeddings']
        centroid = np.mean(embeddings, axis=0)
        
        # Find triplet closest to centroid
        distances = [np.linalg.norm(emb - centroid) for emb in embeddings]
        closest_idx = np.argmin(distances)
        
        return triplets[closest_idx]
    
    def combine_rules_in_cluster(self, cluster: Dict[str, Any]) -> Dict[str, Any]:
        """
        Combine rules from all triplets in a cluster into a single rule
        
        Args:
            cluster: Cluster dictionary containing triplets with rules
            
        Returns:
            Combined rule dictionary
        """
        triplets = cluster['triplets']
        rules = [triplet.get('rule') for triplet in triplets if triplet.get('rule')]
        
        if not rules:
            return None
        
        if len(rules) == 1:
            return rules[0]
        
        # Combine patterns using OR logic
        combined_patterns = []
        combined_replacements = []
        combined_conditions = {}
        total_confidence = 0
        
        for rule in rules:
            if rule:
                combined_patterns.append(rule.get('pattern', ''))
                combined_replacements.append(rule.get('replacement', ''))
                
                # Merge conditions
                if rule.get('conditions'):
                    for key, value in rule['conditions'].items():
                        if key not in combined_conditions:
                            combined_conditions[key] = value
                
                total_confidence += rule.get('confidence', 0)
        
        # Create combined rule
        combined_rule = {
            'rule_id': f"combined_{len(triplets)}_{int(datetime.now().timestamp())}",
            'rule_type': rules[0].get('rule_type', 'combined'),
            'pattern': '|'.join(f"({pattern})" for pattern in combined_patterns if pattern),
            'replacement': self._create_combined_replacement(combined_replacements),
            'description': f"Combined rule from {len(rules)} individual rules",
            'confidence': total_confidence / len(rules),
            'conditions': combined_conditions,
            'source_rules': [rule.get('rule_id') for rule in rules],
            'created_at': datetime.now().isoformat()
        }
        
        return combined_rule
    
    def validate_combined_rule(self, combined_rule: Dict[str, Any], cluster_members: List[Dict[str, Any]]) -> Tuple[float, List[str]]:
        """
        Validate a combined rule against all cluster members
        
        Args:
            combined_rule: Combined rule to validate
            cluster_members: List of triplets in the cluster
            
        Returns:
            Tuple of (success_rate, failed_queries)
        """
        if not combined_rule:
            return 0.0, [triplet['triplet_id'] for triplet in cluster_members]
        
        successful_corrections = 0
        failed_queries = []
        
        for triplet in cluster_members:
            sql_query = triplet.get('sql_query', '')
            if not sql_query:
                failed_queries.append(triplet['triplet_id'])
                continue
            
            # Test if rule can correct the query
            corrected_query = self._apply_rule_to_query(combined_rule, sql_query)
            
            if corrected_query and corrected_query != sql_query:
                # Check if corrected query is valid
                is_valid, _ = self._validate_sql_syntax(corrected_query)
                if is_valid:
                    successful_corrections += 1
                else:
                    failed_queries.append(triplet['triplet_id'])
            else:
                failed_queries.append(triplet['triplet_id'])
        
        success_rate = successful_corrections / len(cluster_members) if cluster_members else 0.0
        return success_rate, failed_queries
    
    def _create_triplet_embeddings(self, triplets: List[TripletData]) -> np.ndarray:
        """Create embeddings for triplets using sentence transformers"""
        embeddings = []
        
        for triplet in triplets:
            # Combine query and explanation text for embedding
            combined_text = f"{triplet.nl_query} {triplet.sql_query} {triplet.explanation.get('explanation_text', '')}"
            embedding = self.embedding_model.encode(combined_text)
            embeddings.append(embedding)
        
        return np.array(embeddings)
    
    def iterative_cluster_merging(self, triplets: List[TripletData], a_percent_threshold: float) -> List[Dict[str, Any]]:
        """
        Iteratively merge clusters with detailed validation and logging
        
        Args:
            triplets: List of TripletData objects to cluster
            a_percent_threshold: Minimum percentage of triplets that must be successfully combined
            
        Returns:
            List of valid clusters with combined rules
        """
        if len(triplets) < 10:
            self.logger.warning(f"Need at least 10 triplets for clustering, got {len(triplets)}")
            return []
        
        self.logger.info(f"Starting iterative cluster merging with {len(triplets)} triplets")
        self.logger.info(f"A percent threshold: {a_percent_threshold}")
        
        # Create embeddings for all triplets
        embeddings = self._create_triplet_embeddings(triplets)
        
        # Start with each triplet as its own cluster
        clusters = []
        for i, triplet in enumerate(triplets):
            cluster = {
                'cluster_id': f"cluster_{i}",
                'triplets': [triplet],
                'embeddings': [embeddings[i]],
                'rules': [triplet.rule] if triplet.rule else [],
                'representative': triplet,
                'merge_history': []
            }
            clusters.append(cluster)
        
        self.logger.info(f"Initial state: {len(clusters)} clusters (each triplet is its own cluster)")
        
        # Track merge attempts and results
        merge_attempts = 0
        successful_merges = 0
        failed_merges = 0
        
        # Continue merging until no more beneficial merges possible
        while True:
            # Compute pairwise similarity between all clusters
            similarity_scores = self._compute_cluster_similarities(clusters, embeddings)
            
            if not similarity_scores:
                self.logger.info("No more clusters to merge")
                break
            
            # Find the two most similar clusters
            best_merge = max(similarity_scores, key=lambda x: x['similarity'])
            cluster1_idx, cluster2_idx = best_merge['cluster_indices']
            similarity = best_merge['similarity']
            
            self.logger.info(f"Merge attempt {merge_attempts + 1}:")
            self.logger.info(f"  - Clusters: {clusters[cluster1_idx]['cluster_id']} + {clusters[cluster2_idx]['cluster_id']}")
            self.logger.info(f"  - Similarity score: {similarity:.4f}")
            
            # Test the merge by creating a temporary merged cluster
            temp_merged_cluster = self._create_temp_merged_cluster(
                clusters[cluster1_idx], clusters[cluster2_idx]
            )
            
            # Generate combined rule for the merged cluster
            combined_rule = self.combine_rules_in_cluster(temp_merged_cluster)
            
            if not combined_rule:
                self.logger.warning(f"  - No rules to combine, skipping merge")
                # Remove this pair from consideration
                similarity_scores = [s for s in similarity_scores 
                                  if s['cluster_indices'] != (cluster1_idx, cluster2_idx)]
                if not similarity_scores:
                    break
                continue
            
            self.logger.info(f"  - Generated combined rule: {combined_rule.get('pattern', 'N/A')} -> {combined_rule.get('replacement', 'N/A')}")
            
            # Test combined rule on representative queries from previous clusters
            validation_results = []
            for prev_cluster in [clusters[cluster1_idx], clusters[cluster2_idx]]:
                if prev_cluster.get('representative'):
                    rep_query = prev_cluster['representative'].sql_query
                    corrected_query = self._apply_rule_to_query(combined_rule, rep_query)
                    
                    if corrected_query and corrected_query != rep_query:
                        is_valid, errors = self._validate_sql_syntax(corrected_query)
                        validation_results.append({
                            'cluster_id': prev_cluster['cluster_id'],
                            'original_query': rep_query,
                            'corrected_query': corrected_query,
                            'is_valid': is_valid,
                            'errors': errors
                        })
                        
                        self.logger.info(f"  - Representative from {prev_cluster['cluster_id']}:")
                        self.logger.info(f"    Original: {rep_query}")
                        self.logger.info(f"    Corrected: {corrected_query}")
                        self.logger.info(f"    Valid: {is_valid}")
                        if errors:
                            self.logger.info(f"    Errors: {errors}")
            
            # Check if all representative queries are successfully corrected
            all_valid = all(result['is_valid'] for result in validation_results)
            
            if all_valid and len(validation_results) > 0:
                # Accept the merge
                merged_cluster = self._perform_cluster_merge(
                    clusters[cluster1_idx], clusters[cluster2_idx], 
                    combined_rule, validation_results
                )
                
                # Replace the two original clusters with the merged cluster
                new_clusters = [clusters[i] for i in range(len(clusters)) 
                              if i not in [cluster1_idx, cluster2_idx]]
                new_clusters.append(merged_cluster)
                clusters = new_clusters
                
                successful_merges += 1
                self.logger.info(f"  - ✅ Merge ACCEPTED")
                self.logger.info(f"  - New cluster size: {len(merged_cluster['triplets'])}")
                self.logger.info(f"  - Combined rule confidence: {combined_rule.get('confidence', 0):.3f}")
                
            else:
                # Discard this merge, try next most similar pair
                failed_merges += 1
                self.logger.warning(f"  - ❌ Merge REJECTED")
                if not validation_results:
                    self.logger.warning(f"  - Reason: No representative queries to test")
                else:
                    failed_count = sum(1 for result in validation_results if not result['is_valid'])
                    self.logger.warning(f"  - Reason: {failed_count}/{len(validation_results)} representative queries failed validation")
                
                # Remove this pair from consideration
                similarity_scores = [s for s in similarity_scores 
                                  if s['cluster_indices'] != (cluster1_idx, cluster2_idx)]
                if not similarity_scores:
                    self.logger.info("No more valid merge candidates")
                    break
            
            merge_attempts += 1
            
            # Check iteration limit
            if merge_attempts >= self.config.MAX_CLUSTERING_ITERATIONS:
                self.logger.warning(f"Reached maximum iterations ({self.config.MAX_CLUSTERING_ITERATIONS})")
                break
        
        # Calculate percentage of triplets successfully combined
        total_triplets = len(triplets)
        combined_triplets = sum(len(cluster['triplets']) for cluster in clusters if len(cluster['triplets']) > 1)
        combination_percentage = (combined_triplets / total_triplets) * 100 if total_triplets > 0 else 0
        
        self.logger.info(f"Clustering completed:")
        self.logger.info(f"  - Total merge attempts: {merge_attempts}")
        self.logger.info(f"  - Successful merges: {successful_merges}")
        self.logger.info(f"  - Failed merges: {failed_merges}")
        self.logger.info(f"  - Final clusters: {len(clusters)}")
        self.logger.info(f"  - Combined triplets: {combined_triplets}/{total_triplets} ({combination_percentage:.1f}%)")
        
        # Check if combination percentage meets threshold
        if combination_percentage < a_percent_threshold:
            self.logger.warning(f"Combination percentage {combination_percentage:.1f}% < threshold {a_percent_threshold}%")
            self.logger.warning("Discarding entire clustering result")
            return []
        
        # Filter to only clusters with combined rules
        valid_clusters = []
        for cluster in clusters:
            if len(cluster['triplets']) > 1 and cluster.get('combined_rule'):
                # Final validation of combined rule
                success_rate, failed_queries = self.validate_combined_rule(
                    cluster['combined_rule'], cluster['triplets']
                )
                cluster['final_success_rate'] = success_rate
                cluster['final_failed_queries'] = failed_queries
                valid_clusters.append(cluster)
                
                self.logger.info(f"Valid cluster {cluster['cluster_id']}:")
                self.logger.info(f"  - Size: {len(cluster['triplets'])}")
                self.logger.info(f"  - Final success rate: {success_rate:.3f}")
                self.logger.info(f"  - Failed queries: {len(failed_queries)}")
        
        self.logger.info(f"Returning {len(valid_clusters)} valid clusters with combined rules")
        return valid_clusters
    
    def _iterative_cluster_merging(self, triplets: List[TripletData], embeddings: np.ndarray, 
                                  initial_labels: np.ndarray, target_clusters: Optional[int]) -> List[Dict[str, Any]]:
        """Legacy method - redirects to new iterative_cluster_merging"""
        return self.iterative_cluster_merging(triplets, self.config.A_PERCENT_THRESHOLD)
    
    def _compute_cluster_similarities(self, clusters: List[Dict[str, Any]], embeddings: np.ndarray) -> List[Dict[str, Any]]:
        """Compute pairwise similarity between all clusters"""
        similarity_scores = []
        
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                # Calculate rule similarity between clusters
                rule_similarity = self._calculate_rule_similarity(clusters[i], clusters[j])
                
                # Calculate query similarity
                query_similarity = self._calculate_query_similarity(clusters[i], clusters[j], embeddings)
                
                # Combined similarity score
                combined_similarity = (rule_similarity * 0.7) + (query_similarity * 0.3)
                
                if combined_similarity >= self.config.CLUSTERING_THRESHOLD:
                    similarity_scores.append({
                        'cluster_indices': (i, j),
                        'similarity': combined_similarity,
                        'rule_similarity': rule_similarity,
                        'query_similarity': query_similarity
                    })
        
        return similarity_scores
    
    def _create_temp_merged_cluster(self, cluster1: Dict[str, Any], cluster2: Dict[str, Any]) -> Dict[str, Any]:
        """Create a temporary merged cluster for testing"""
        return {
            'cluster_id': f"temp_merged_{cluster1['cluster_id']}_{cluster2['cluster_id']}",
            'triplets': cluster1['triplets'] + cluster2['triplets'],
            'embeddings': cluster1['embeddings'] + cluster2['embeddings'],
            'rules': cluster1['rules'] + cluster2['rules'],
            'representative': cluster1.get('representative'),  # Use first cluster's representative
            'merge_history': cluster1.get('merge_history', []) + cluster2.get('merge_history', [])
        }
    
    def _perform_cluster_merge(self, cluster1: Dict[str, Any], cluster2: Dict[str, Any], 
                              combined_rule: Dict[str, Any], validation_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Perform the actual cluster merge with combined rule"""
        merged_cluster = {
            'cluster_id': f"merged_{cluster1['cluster_id']}_{cluster2['cluster_id']}_{int(datetime.now().timestamp())}",
            'triplets': cluster1['triplets'] + cluster2['triplets'],
            'embeddings': cluster1['embeddings'] + cluster2['embeddings'],
            'rules': cluster1['rules'] + cluster2['rules'],
            'combined_rule': combined_rule,
            'representative': self.get_cluster_representative({
                'triplets': cluster1['triplets'] + cluster2['triplets'],
                'embeddings': cluster1['embeddings'] + cluster2['embeddings']
            }),
            'merge_history': cluster1.get('merge_history', []) + cluster2.get('merge_history', []) + [{
                'timestamp': datetime.now().isoformat(),
                'merged_clusters': [cluster1['cluster_id'], cluster2['cluster_id']],
                'combined_rule': combined_rule,
                'validation_results': validation_results
            }],
            'success_rate': 1.0,  # All representative queries passed validation
            'failed_queries': []
        }
        
        return merged_cluster
    
    def _find_best_cluster_merge(self, clusters: List[Dict[str, Any]], 
                                similarity_matrix: np.ndarray) -> Optional[Tuple[int, int]]:
        """Find the best pair of clusters to merge based on rule similarity"""
        best_similarity = -1
        best_merge = None
        
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                # Calculate rule similarity between clusters
                rule_similarity = self._calculate_rule_similarity(clusters[i], clusters[j])
                
                # Calculate query similarity
                query_similarity = self._calculate_query_similarity(clusters[i], clusters[j], similarity_matrix)
                
                # Combined similarity score
                combined_similarity = (rule_similarity * 0.7) + (query_similarity * 0.3)
                
                if combined_similarity > best_similarity and combined_similarity >= self.config.CLUSTERING_THRESHOLD:
                    best_similarity = combined_similarity
                    best_merge = (i, j)
        
        return best_merge
    
    def _calculate_rule_similarity(self, cluster1: Dict[str, Any], cluster2: Dict[str, Any]) -> float:
        """Calculate similarity between rules in two clusters"""
        rules1 = cluster1.get('rules', [])
        rules2 = cluster2.get('rules', [])
        
        if not rules1 or not rules2:
            return 0.0
        
        # Compare rule patterns
        patterns1 = [rule.get('pattern', '') for rule in rules1 if rule]
        patterns2 = [rule.get('pattern', '') for rule in rules2 if rule]
        
        if not patterns1 or not patterns2:
            return 0.0
        
        # Calculate pattern similarity using embeddings
        pattern_texts1 = ' '.join(patterns1)
        pattern_texts2 = ' '.join(patterns2)
        
        emb1 = self.embedding_model.encode(pattern_texts1)
        emb2 = self.embedding_model.encode(pattern_texts2)
        
        similarity = cosine_similarity([emb1], [emb2])[0][0]
        return similarity
    
    def _calculate_query_similarity(self, cluster1: Dict[str, Any], cluster2: Dict[str, Any], 
                                   similarity_matrix: np.ndarray) -> float:
        """Calculate average query similarity between clusters"""
        triplets1 = cluster1.get('triplets', [])
        triplets2 = cluster2.get('triplets', [])
        
        if not triplets1 or not triplets2:
            return 0.0
        
        # Get indices of triplets in the original list
        # This is a simplified approach - in practice, you'd need to track indices
        similarities = []
        for t1 in triplets1:
            for t2 in triplets2:
                # Calculate similarity between triplet embeddings
                emb1 = self.embedding_model.encode(f"{t1.nl_query} {t1.sql_query}")
                emb2 = self.embedding_model.encode(f"{t2.nl_query} {t2.sql_query}")
                sim = cosine_similarity([emb1], [emb2])[0][0]
                similarities.append(sim)
        
        return np.mean(similarities) if similarities else 0.0
    
    def _merge_clusters(self, clusters: List[Dict[str, Any]], merge_indices: Tuple[int, int]) -> List[Dict[str, Any]]:
        """Merge two clusters"""
        i, j = merge_indices
        cluster1 = clusters[i]
        cluster2 = clusters[j]
        
        # Create merged cluster
        merged_cluster = {
            'cluster_id': f"merged_{len(clusters)}_{int(datetime.now().timestamp())}",
            'triplets': cluster1['triplets'] + cluster2['triplets'],
            'embeddings': cluster1['embeddings'] + cluster2['embeddings'],
            'rules': cluster1['rules'] + cluster2['rules']
        }
        
        # Remove original clusters and add merged cluster
        new_clusters = [clusters[k] for k in range(len(clusters)) if k not in [i, j]]
        new_clusters.append(merged_cluster)
        
        return new_clusters
    
    def _create_combined_replacement(self, replacements: List[str]) -> str:
        """Create a combined replacement pattern from multiple replacements"""
        if not replacements:
            return ""
        
        if len(replacements) == 1:
            return replacements[0]
        
        # For now, return the first replacement
        # In practice, you might want more sophisticated combination logic
        return replacements[0]
    
    def _apply_rule_to_query(self, rule: Dict[str, Any], query: str) -> Optional[str]:
        """Apply a rule to a query"""
        if not rule:
            return None
        
        pattern = rule.get('pattern', '')
        replacement = rule.get('replacement', '')
        
        if not pattern or not replacement:
            return None
        
        try:
            import re
            corrected_query = re.sub(pattern, replacement, query, flags=re.IGNORECASE)
            return corrected_query
        except Exception as e:
            self.logger.error(f"Error applying rule to query: {e}")
            return None
    
    def _validate_sql_syntax(self, sql_query: str) -> Tuple[bool, List[str]]:
        """Validate SQL syntax (simplified version)"""
        errors = []
        
        try:
            # Basic syntax checks
            if not sql_query.strip():
                errors.append("Empty query")
                return False, errors
            
            # Check for balanced quotes
            single_quotes = sql_query.count("'")
            double_quotes = sql_query.count('"')
            
            if single_quotes % 2 != 0:
                errors.append("Unmatched single quotes")
            if double_quotes % 2 != 0:
                errors.append("Unmatched double quotes")
            
            # Check for balanced parentheses
            paren_count = 0
            for char in sql_query:
                if char == '(':
                    paren_count += 1
                elif char == ')':
                    paren_count -= 1
                    if paren_count < 0:
                        errors.append("Unmatched closing parenthesis")
                        break
            
            if paren_count != 0:
                errors.append("Unmatched parentheses")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            errors.append(f"Syntax validation error: {str(e)}")
            return False, errors
    
    def _get_triplet_embeddings(self) -> np.ndarray:
        """Get embeddings for all triplets"""
        embeddings = []
        
        for triplet in self.triplets:
            # Combine query, explanation, and rule text for embedding
            combined_text = f"{triplet.query_record.query_text} {triplet.explanation.explanation_text}"
            if triplet.rule:
                combined_text += f" {triplet.rule.description}"
            
            embedding = self.embedding_model.encode(combined_text)
            embeddings.append(embedding)
        
        return np.array(embeddings)
    
    def _create_cluster(self, triplets: List[QueryTriplet], label: int) -> Cluster:
        """Create a cluster from triplets"""
        cluster_id = f"cluster_{label}"
        
        # Calculate centroid
        embeddings = [self.embedding_model.encode(f"{t.query_record.query_text} {t.explanation.explanation_text}") for t in triplets]
        centroid = np.mean(embeddings, axis=0)
        
        # Calculate average similarity within cluster
        similarities = []
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                sim = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
                similarities.append(sim)
        
        average_similarity = np.mean(similarities) if similarities else 0.0
        
        # Find dominant error type
        error_types = [t.explanation.error_type for t in triplets]
        dominant_error_type = max(set(error_types), key=error_types.count) if error_types else None
        
        cluster = Cluster(
            cluster_id=cluster_id,
            triplets=triplets,
            centroid=centroid,
            size=len(triplets),
            average_similarity=average_similarity,
            dominant_error_type=dominant_error_type,
            metadata={'created_by': 'clustering_manager'},
            created_at=self._get_timestamp()
        )
        
        return cluster
    
    def find_similar_clusters(self, query_text: str, k: int = 5) -> List[Tuple[Cluster, float]]:
        """
        Find clusters similar to a query
        
        Args:
            query_text: Query to find similar clusters for
            k: Number of similar clusters to return
            
        Returns:
            List of tuples containing (Cluster, similarity_score)
        """
        if not self.clusters:
            return []
        
        query_embedding = self.embedding_model.encode(query_text)
        similarities = []
        
        for cluster in self.clusters:
            if cluster.centroid is not None:
                similarity = cosine_similarity([query_embedding], [cluster.centroid])[0][0]
                similarities.append((cluster, similarity))
        
        # Sort by similarity and return top k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:k]
    
    def get_cluster_by_id(self, cluster_id: str) -> Optional[Cluster]:
        """Get a cluster by ID"""
        for cluster in self.clusters:
            if cluster.cluster_id == cluster_id:
                return cluster
        return None
    
    def get_triplets_by_cluster(self, cluster_id: str) -> List[QueryTriplet]:
        """Get all triplets in a cluster"""
        return [t for t in self.triplets if t.cluster_id == cluster_id]
    
    def get_clusters_by_error_type(self, error_type: str) -> List[Cluster]:
        """Get clusters with a specific dominant error type"""
        return [c for c in self.clusters if c.dominant_error_type == error_type]
    
    def get_large_clusters(self, min_size: int = None) -> List[Cluster]:
        """Get clusters above a minimum size"""
        if min_size is None:
            min_size = self.config.MIN_CLUSTER_SIZE
        
        return [c for c in self.clusters if c.size >= min_size]
    
    def merge_clusters(self, cluster_ids: List[str]) -> Optional[Cluster]:
        """
        Merge multiple clusters into one
        
        Args:
            cluster_ids: List of cluster IDs to merge
            
        Returns:
            Merged cluster or None if merge fails
        """
        clusters_to_merge = [c for c in self.clusters if c.cluster_id in cluster_ids]
        
        if len(clusters_to_merge) < 2:
            return None
        
        # Combine all triplets
        all_triplets = []
        for cluster in clusters_to_merge:
            all_triplets.extend(cluster.triplets)
        
        # Create new merged cluster
        merged_cluster = self._create_cluster(all_triplets, len(self.clusters))
        merged_cluster.cluster_id = f"merged_{len(self.clusters)}"
        
        # Remove old clusters
        self.clusters = [c for c in self.clusters if c.cluster_id not in cluster_ids]
        
        # Add merged cluster
        self.clusters.append(merged_cluster)
        
        # Update triplets
        for triplet in all_triplets:
            triplet.cluster_id = merged_cluster.cluster_id
        
        self._save_clusters()
        self._save_triplets()
        
        return merged_cluster
    
    def split_cluster(self, cluster_id: str, n_subclusters: int = 2) -> List[Cluster]:
        """
        Split a cluster into subclusters
        
        Args:
            cluster_id: ID of cluster to split
            n_subclusters: Number of subclusters to create
            
        Returns:
            List of new subclusters
        """
        cluster = self.get_cluster_by_id(cluster_id)
        if not cluster or len(cluster.triplets) < n_subclusters:
            return []
        
        # Perform subclustering
        embeddings = self._get_triplet_embeddings()
        cluster_indices = [i for i, t in enumerate(self.triplets) if t.cluster_id == cluster_id]
        cluster_embeddings = embeddings[cluster_indices]
        
        subclustering = AgglomerativeClustering(n_clusters=n_subclusters, linkage='ward')
        sub_labels = subclustering.fit_predict(cluster_embeddings)
        
        # Create subclusters
        subclusters = []
        for sub_label in np.unique(sub_labels):
            sub_triplets = [cluster.triplets[i] for i in range(len(cluster.triplets)) if sub_labels[i] == sub_label]
            subcluster = self._create_cluster(sub_triplets, len(self.clusters) + len(subclusters))
            subcluster.cluster_id = f"{cluster_id}_sub_{sub_label}"
            subclusters.append(subcluster)
            
            # Update triplets
            for triplet in sub_triplets:
                triplet.cluster_id = subcluster.cluster_id
        
        # Remove original cluster and add subclusters
        self.clusters = [c for c in self.clusters if c.cluster_id != cluster_id]
        self.clusters.extend(subclusters)
        
        self._save_clusters()
        self._save_triplets()
        
        return subclusters
    
    def get_clustering_statistics(self) -> Dict[str, Any]:
        """Get statistics about clustering"""
        if not self.clusters:
            return {
                'total_clusters': 0,
                'total_triplets': 0,
                'average_cluster_size': 0.0,
                'clusters_by_error_type': {}
            }
        
        clusters_by_error_type = {}
        for cluster in self.clusters:
            error_type = cluster.dominant_error_type or 'unknown'
            clusters_by_error_type[error_type] = clusters_by_error_type.get(error_type, 0) + 1
        
        return {
            'total_clusters': len(self.clusters),
            'total_triplets': len(self.triplets),
            'average_cluster_size': sum(c.size for c in self.clusters) / len(self.clusters),
            'clusters_by_error_type': clusters_by_error_type,
            'largest_cluster_size': max(c.size for c in self.clusters) if self.clusters else 0,
            'smallest_cluster_size': min(c.size for c in self.clusters) if self.clusters else 0
        }
    
    def _save_triplets(self):
        """Save triplets to disk"""
        data = []
        for triplet in self.triplets:
            triplet_data = {
                'triplet_id': triplet.triplet_id,
                'query_record': {
                    'query_id': triplet.query_record.query_id,
                    'query_text': triplet.query_record.query_text,
                    'query_type': triplet.query_record.query_type,
                    'embedding': triplet.query_record.embedding.tolist() if triplet.query_record.embedding is not None else None,
                    'metadata': triplet.query_record.metadata,
                    'timestamp': triplet.query_record.timestamp
                },
                'explanation': {
                    'explanation_id': triplet.explanation.explanation_id,
                    'query_id': triplet.explanation.query_id,
                    'query_text': triplet.explanation.query_text,
                    'error_type': triplet.explanation.error_type,
                    'explanation_text': triplet.explanation.explanation_text,
                    'confidence': triplet.explanation.confidence,
                    'suggested_fix': triplet.explanation.suggested_fix,
                    'metadata': triplet.explanation.metadata,
                    'created_at': triplet.explanation.created_at
                },
                'rule': {
                    'rule_id': triplet.rule.rule_id,
                    'request_id': triplet.rule.request_id,
                    'explanation_id': triplet.rule.explanation_id,
                    'rule_type': triplet.rule.rule_type.value,
                    'pattern': triplet.rule.pattern,
                    'replacement': triplet.rule.replacement,
                    'description': triplet.rule.description,
                    'confidence': triplet.rule.confidence,
                    'conditions': triplet.rule.conditions,
                    'metadata': triplet.rule.metadata,
                    'created_at': triplet.rule.created_at
                } if triplet.rule else None,
                'cluster_id': triplet.cluster_id,
                'metadata': triplet.metadata,
                'created_at': triplet.created_at
            }
            data.append(triplet_data)
        
        with open(os.path.join(self.config.TRIPLETS_DIR, "triplets.json"), 'w') as f:
            json.dump(data, f, indent=2)
    
    def _save_clusters(self):
        """Save clusters to disk"""
        data = []
        for cluster in self.clusters:
            cluster_data = {
                'cluster_id': cluster.cluster_id,
                'centroid': cluster.centroid.tolist() if cluster.centroid is not None else None,
                'size': cluster.size,
                'average_similarity': cluster.average_similarity,
                'dominant_error_type': cluster.dominant_error_type,
                'metadata': cluster.metadata,
                'created_at': cluster.created_at
            }
            data.append(cluster_data)
        
        with open(os.path.join(self.config.TRIPLETS_DIR, "clusters.json"), 'w') as f:
            json.dump(data, f, indent=2)
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        return datetime.now().isoformat()
    
    def clear_all_data(self):
        """Clear all clustering data"""
        self.clusters = []
        self.triplets = []
        
        # Remove files
        for file_path in [
            os.path.join(self.config.TRIPLETS_DIR, "triplets.json"),
            os.path.join(self.config.TRIPLETS_DIR, "clusters.json")
        ]:
            if os.path.exists(file_path):
                os.remove(file_path)
