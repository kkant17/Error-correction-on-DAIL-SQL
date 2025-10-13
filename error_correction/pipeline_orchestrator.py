"""
Pipeline Orchestrator for Error Correction Pipeline

This module coordinates the entire error correction pipeline, managing the flow between
different components and providing a unified interface for error correction operations.
"""

import os
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

from .config import ErrorCorrectionConfig
from .vector_db_manager import VectorDBManager, QueryRecord, ErrorInfo
from .rule_engine import RuleEngine, Rule, RuleTester
from .llm_explainer import LLMExplainer, Explanation
from .rule_generator import RuleGenerator, GeneratedRule
from .clustering_manager import ClusteringManager, QueryTriplet, Cluster, TripletManager, TripletData


@dataclass
class PipelineResult:
    """Data class for pipeline execution results"""
    success: bool
    corrected_query: Optional[str] = None
    applied_rules: List[Rule] = None
    confidence: float = 0.0
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PipelineOrchestrator:
    """Main orchestrator for the error correction pipeline"""
    
    def __init__(self, config: ErrorCorrectionConfig = None, api_key: Optional[str] = None):
        """
        Initialize the PipelineOrchestrator
        
        Args:
            config: Configuration object (uses default if None)
            api_key: OpenAI API key (if None, will use environment variable)
        """
        self.config = config or ErrorCorrectionConfig()
        self.api_key = api_key
        
        # Initialize components
        self.vector_db_manager = VectorDBManager(self.config)
        self.rule_engine = RuleEngine(self.config)
        self.llm_explainer = LLMExplainer(self.config, self.api_key)
        self.rule_generator = RuleGenerator(self.config, self.api_key)
        self.clustering_manager = ClusteringManager(self.config)
        
        # Setup logging
        self._setup_logging()
        
        # Pipeline state
        self.pipeline_state = {
            'initialized': True,
            'last_run': None,
            'total_queries_processed': 0,
            'successful_corrections': 0,
            'failed_corrections': 0
        }
    
    def _setup_logging(self):
        """Setup logging for the pipeline"""
        logging.basicConfig(
            level=getattr(logging, self.config.LOG_LEVEL),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.config.LOG_FILE),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def add_correct_query(self, query_text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Add a correct query to the database
        
        Args:
            query_text: The SQL query text
            metadata: Optional metadata about the query
            
        Returns:
            Query ID
        """
        query_id = self.vector_db_manager.add_correct_query(query_text, metadata)
        self.logger.info(f"Added correct query: {query_id}")
        return query_id
    
    def add_wrong_query(self, query_text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Add a wrong query to the database
        
        Args:
            query_text: The SQL query text
            metadata: Optional metadata about the query
            
        Returns:
            Query ID
        """
        query_id = self.vector_db_manager.add_wrong_query(query_text, metadata)
        self.logger.info(f"Added wrong query: {query_id}")
        return query_id
    
    def correct_query(self, query_text: str, context: Optional[str] = None) -> PipelineResult:
        """
        Correct a query using the pipeline
        
        Args:
            query_text: SQL query to correct
            context: Optional context about the query
            
        Returns:
            PipelineResult object containing correction results
        """
        try:
            self.logger.info(f"Starting correction for query: {query_text[:100]}...")
            
            # Step 1: Try to apply existing rules first
            rule_corrections = self.rule_engine.apply_rules(query_text)
            
            if rule_corrections:
                best_rule, corrected_query, confidence = rule_corrections[0]
                if confidence >= self.config.CONFIDENCE_THRESHOLD:
                    self.logger.info(f"Applied rule {best_rule.rule_id} with confidence {confidence}")
                    return PipelineResult(
                        success=True,
                        corrected_query=corrected_query,
                        applied_rules=[best_rule],
                        confidence=confidence,
                        metadata={'correction_method': 'existing_rule'}
                    )
            
            # Step 2: If no suitable rule found, generate explanation and rule
            self.logger.info("No suitable existing rule found, generating new explanation...")
            
            # Add query as wrong query for analysis
            query_id = self.add_wrong_query(query_text, {'context': context})
            
            # Generate explanation
            explanation = self.llm_explainer.explain_query_error(query_text, query_id, context)
            
            if explanation.confidence < self.config.CONFIDENCE_THRESHOLD:
                self.logger.warning(f"Low confidence explanation: {explanation.confidence}")
                return PipelineResult(
                    success=False,
                    error_message=f"Low confidence explanation: {explanation.confidence}",
                    metadata={'explanation_confidence': explanation.confidence}
                )
            
            # Generate rule from explanation
            generated_rule = self.rule_generator.generate_rule_from_explanation(explanation)
            
            if not generated_rule:
                self.logger.error("Failed to generate rule from explanation")
                return PipelineResult(
                    success=False,
                    error_message="Failed to generate rule from explanation"
                )
            
            # Validate generated rule
            is_valid, issues = self.rule_generator.validate_generated_rule(generated_rule)
            if not is_valid:
                self.logger.error(f"Generated rule is invalid: {issues}")
                return PipelineResult(
                    success=False,
                    error_message=f"Generated rule is invalid: {issues}"
                )
            
            # Convert to rule engine rule and add it
            rule = self.rule_generator.convert_to_rule_engine_rule(generated_rule)
            if not self.rule_engine.add_rule(rule):
                self.logger.error("Failed to add generated rule to rule engine")
                return PipelineResult(
                    success=False,
                    error_message="Failed to add generated rule to rule engine"
                )
            
            # Apply the new rule
            rule_corrections = self.rule_engine.apply_rules(query_text)
            if rule_corrections:
                best_rule, corrected_query, confidence = rule_corrections[0]
                self.logger.info(f"Applied newly generated rule {best_rule.rule_id}")
                return PipelineResult(
                    success=True,
                    corrected_query=corrected_query,
                    applied_rules=[best_rule],
                    confidence=confidence,
                    metadata={'correction_method': 'generated_rule'}
                )
            
            return PipelineResult(
                success=False,
                error_message="No applicable rules found after generation"
            )
            
        except Exception as e:
            self.logger.error(f"Error in correction pipeline: {e}")
            return PipelineResult(
                success=False,
                error_message=str(e)
            )
        finally:
            self.pipeline_state['total_queries_processed'] += 1
            self.pipeline_state['last_run'] = self._get_timestamp()
    
    def batch_correct_queries(self, queries: List[str], contexts: Optional[List[str]] = None) -> List[PipelineResult]:
        """
        Correct multiple queries in batch
        
        Args:
            queries: List of SQL queries to correct
            contexts: Optional list of contexts for each query
            
        Returns:
            List of PipelineResult objects
        """
        results = []
        
        for i, query in enumerate(queries):
            context = contexts[i] if contexts and i < len(contexts) else None
            result = self.correct_query(query, context)
            results.append(result)
            
            if result.success:
                self.pipeline_state['successful_corrections'] += 1
            else:
                self.pipeline_state['failed_corrections'] += 1
        
        return results
    
    def run_full_pipeline(self, wrong_queries: List[str], correct_queries: List[str] = None) -> Dict[str, Any]:
        """
        Run the full error correction pipeline
        
        Args:
            wrong_queries: List of wrong SQL queries to process
            correct_queries: Optional list of correct SQL queries for reference
            
        Returns:
            Dictionary containing pipeline results and statistics
        """
        self.logger.info("Starting full pipeline execution")
        
        # Step 1: Add queries to vector database
        wrong_query_ids = []
        for query in wrong_queries:
            query_id = self.add_wrong_query(query)
            wrong_query_ids.append(query_id)
        
        if correct_queries:
            for query in correct_queries:
                self.add_correct_query(query)
        
        # Step 2: Generate explanations for wrong queries
        self.logger.info("Generating explanations...")
        explanations = []
        for i, query in enumerate(wrong_queries):
            explanation = self.llm_explainer.explain_query_error(query, wrong_query_ids[i])
            explanations.append(explanation)
        
        # Step 3: Generate rules from explanations
        self.logger.info("Generating rules...")
        generated_rules = self.rule_generator.batch_generate_rules(explanations)
        
        # Step 4: Add valid rules to rule engine
        added_rules = 0
        for rule in generated_rules:
            rule_engine_rule = self.rule_generator.convert_to_rule_engine_rule(rule)
            if self.rule_engine.add_rule(rule_engine_rule):
                added_rules += 1
        
        # Step 5: Create triplets and perform clustering
        self.logger.info("Creating triplets and clustering...")
        triplets = []
        for i, (query, explanation) in enumerate(zip(wrong_queries, explanations)):
            query_record = self.vector_db_manager.get_query_by_id(wrong_query_ids[i])
            rule = generated_rules[i] if i < len(generated_rules) else None
            triplet = self.clustering_manager.create_triplet(query_record, explanation, rule)
            triplets.append(triplet)
        
        # Perform clustering
        clusters = self.clustering_manager.perform_clustering()
        
        # Step 6: Test corrections
        self.logger.info("Testing corrections...")
        correction_results = []
        for query in wrong_queries:
            result = self.correct_query(query)
            correction_results.append(result)
        
        # Calculate statistics
        successful_corrections = sum(1 for r in correction_results if r.success)
        average_confidence = sum(r.confidence for r in correction_results if r.success) / max(successful_corrections, 1)
        
        pipeline_results = {
            'total_queries': len(wrong_queries),
            'successful_corrections': successful_corrections,
            'failed_corrections': len(wrong_queries) - successful_corrections,
            'success_rate': successful_corrections / len(wrong_queries),
            'average_confidence': average_confidence,
            'total_explanations': len(explanations),
            'total_generated_rules': len(generated_rules),
            'added_rules': added_rules,
            'total_clusters': len(clusters),
            'correction_results': correction_results
        }
        
        self.logger.info(f"Pipeline completed. Success rate: {pipeline_results['success_rate']:.2%}")
        
        return pipeline_results
    
    def get_pipeline_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics about the pipeline"""
        return {
            'pipeline_state': self.pipeline_state,
            'vector_db_stats': self.vector_db_manager.get_statistics(),
            'rule_engine_stats': self.rule_engine.get_rule_statistics(),
            'explainer_stats': self.llm_explainer.get_explanation_statistics(),
            'rule_generator_stats': self.rule_generator.get_rule_statistics(),
            'clustering_stats': self.clustering_manager.get_clustering_statistics()
        }
    
    def export_pipeline_data(self, export_dir: str):
        """Export all pipeline data to a directory"""
        os.makedirs(export_dir, exist_ok=True)
        
        # Export vector database data
        self.vector_db_manager.export_rules(os.path.join(export_dir, "vector_db_rules.json"))
        
        # Export rule engine data
        self.rule_engine.export_rules(os.path.join(export_dir, "rule_engine_rules.json"))
        
        # Export explanations
        self.llm_explainer.export_explanations(os.path.join(export_dir, "explanations.json"))
        
        # Export generated rules
        self.rule_generator.export_generated_rules(os.path.join(export_dir, "generated_rules.json"))
        
        # Export pipeline statistics
        with open(os.path.join(export_dir, "pipeline_statistics.json"), 'w') as f:
            json.dump(self.get_pipeline_statistics(), f, indent=2)
        
        self.logger.info(f"Pipeline data exported to {export_dir}")
    
    def reset_pipeline(self):
        """Reset the pipeline to initial state"""
        self.logger.info("Resetting pipeline...")
        
        # Clear all data
        self.vector_db_manager.clear_all_data()
        self.llm_explainer.clear_explanations()
        self.rule_generator.clear_generated_rules()
        self.clustering_manager.clear_all_data()
        
        # Reset pipeline state
        self.pipeline_state = {
            'initialized': True,
            'last_run': None,
            'total_queries_processed': 0,
            'successful_corrections': 0,
            'failed_corrections': 0
        }
        
        self.logger.info("Pipeline reset completed")
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        return datetime.now().isoformat()
    
    def health_check(self) -> Dict[str, Any]:
        """Perform a health check on all pipeline components"""
        health_status = {
            'overall_health': True,
            'components': {},
            'issues': []
        }
        
        # Check vector database
        try:
            stats = self.vector_db_manager.get_statistics()
            health_status['components']['vector_db'] = {'status': 'healthy', 'stats': stats}
        except Exception as e:
            health_status['components']['vector_db'] = {'status': 'unhealthy', 'error': str(e)}
            health_status['issues'].append(f"Vector DB: {e}")
            health_status['overall_health'] = False
        
        # Check rule engine
        try:
            stats = self.rule_engine.get_rule_statistics()
            health_status['components']['rule_engine'] = {'status': 'healthy', 'stats': stats}
        except Exception as e:
            health_status['components']['rule_engine'] = {'status': 'unhealthy', 'error': str(e)}
            health_status['issues'].append(f"Rule Engine: {e}")
            health_status['overall_health'] = False
        
        # Check LLM explainer
        try:
            stats = self.llm_explainer.get_explanation_statistics()
            health_status['components']['llm_explainer'] = {'status': 'healthy', 'stats': stats}
        except Exception as e:
            health_status['components']['llm_explainer'] = {'status': 'unhealthy', 'error': str(e)}
            health_status['issues'].append(f"LLM Explainer: {e}")
            health_status['overall_health'] = False
        
        # Check rule generator
        try:
            stats = self.rule_generator.get_rule_statistics()
            health_status['components']['rule_generator'] = {'status': 'healthy', 'stats': stats}
        except Exception as e:
            health_status['components']['rule_generator'] = {'status': 'unhealthy', 'error': str(e)}
            health_status['issues'].append(f"Rule Generator: {e}")
            health_status['overall_health'] = False
        
        # Check clustering manager
        try:
            stats = self.clustering_manager.get_clustering_statistics()
            health_status['components']['clustering_manager'] = {'status': 'healthy', 'stats': stats}
        except Exception as e:
            health_status['components']['clustering_manager'] = {'status': 'unhealthy', 'error': str(e)}
            health_status['issues'].append(f"Clustering Manager: {e}")
            health_status['overall_health'] = False
        
        return health_status


class ErrorCorrectionPipeline:
    """Main pipeline class that coordinates the entire error correction workflow"""
    
    def __init__(self, config: ErrorCorrectionConfig):
        """
        Initialize the ErrorCorrectionPipeline
        
        Args:
            config: Configuration object containing parameters
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.vector_db_manager = VectorDBManager(config)
        self.rule_engine = RuleEngine(config)
        self.rule_tester = RuleTester(config, self.vector_db_manager)
        self.llm_explainer = LLMExplainer(config)
        self.rule_generator = RuleGenerator(config)
        self.clustering_manager = ClusteringManager(config)
        self.triplet_manager = TripletManager(config)
        
        self.logger.info("ErrorCorrectionPipeline initialized with all components")
    
    def run_pipeline(self, nl_query: str, ground_truth_sql: Optional[str] = None) -> Tuple[str, bool]:
        """
        Run the complete error correction pipeline
        
        Args:
            nl_query: Natural language query
            ground_truth_sql: Optional ground truth SQL for validation
            
        Returns:
            Tuple of (final_sql, is_correct)
        """
        self.logger.info(f"Starting pipeline for query: {nl_query[:50]}...")
        
        try:
            # Step 1: Get SQL from DAIL SQL
            self.logger.info("Step 1: Getting SQL from DAIL SQL")
            generated_sql = self._call_dail_sql(nl_query)
            self.logger.info(f"Generated SQL: {generated_sql}")
            
            # Step 2: Apply existing rules
            self.logger.info("Step 2: Applying existing rules")
            rule_result = self.rule_engine.apply_rules(generated_sql)
            is_valid = rule_result.is_valid
            applied_rules = rule_result.applied_rules
            corrected_sql = rule_result.corrected_sql if rule_result.corrected_sql else generated_sql
            
            self.logger.info(f"Rule application result: is_valid={is_valid}, applied_rules={len(applied_rules)}")
            if corrected_sql != generated_sql:
                self.logger.info(f"SQL corrected: {generated_sql} -> {corrected_sql}")
            
            final_sql = corrected_sql if corrected_sql else generated_sql
            
            # Step 3-4: Check correctness and store
            self.logger.info("Step 3-4: Validating SQL correctness and storing")
            is_correct = self._validate_sql(final_sql, ground_truth_sql)
            
            if is_correct:
                self.logger.info("SQL is correct - storing in correct queries")
                self.vector_db_manager.store_correct_query(
                    nl_query=nl_query,
                    sql_query=final_sql,
                    metadata={
                        'processed_by': 'error_correction_pipeline',
                        'applied_rules': [rule.rule_id for rule in applied_rules],
                        'timestamp': datetime.now().isoformat()
                    }
                )
            else:
                self.logger.info("SQL is incorrect - storing in wrong queries")
                error_info = self._create_error_info(final_sql, ground_truth_sql)
                
                self.vector_db_manager.store_wrong_query(
                    nl_query=nl_query,
                    sql_query=final_sql,
                    error_info=error_info,
                    metadata={
                        'processed_by': 'error_correction_pipeline',
                        'applied_rules': [rule.rule_id for rule in applied_rules],
                        'timestamp': datetime.now().isoformat()
                    }
                )
                
                # Step 5: Get LLM explanation
                self.logger.info("Step 5: Generating LLM explanation")
                explanation = self.llm_explainer.generate_explanation(
                    nl_query=nl_query,
                    sql_query=final_sql,
                    error_info=error_info
                )
                
                if explanation:
                    self.logger.info(f"Generated explanation: {explanation.explanation_id}")
                    
                    # Step 6: Generate and validate rule
                    self.logger.info("Step 6: Generating and validating rule")
                    rule_result = self.rule_generator.generate_rule_from_explanation(
                        explanation=explanation,
                        wrong_query=final_sql,
                        nl_query=nl_query
                    )
                    
                    if rule_result and rule_result.get('generated_rule'):
                        generated_rule = rule_result['generated_rule']
                        self.logger.info(f"Generated rule: {generated_rule['rule_id']}")
                        
                        # Validate rule on the original wrong query
                        validation_result = self.rule_generator.validate_rule_on_query(
                            rule_result['executable_rule'], final_sql
                        )
                        
                        if validation_result.catches_error:
                            self.logger.info("Rule validation passed - rule catches the error")
                            
                            # Step 7: Add to triplet collection
                            self.logger.info("Step 7: Adding to triplet collection")
                            triplet_id = self.triplet_manager.add_triplet(
                                nl_query=nl_query,
                                sql_query=final_sql,
                                explanation=explanation,
                                rule=generated_rule,
                                database_schema=self._extract_database_schema(final_sql),
                                metadata={
                                    'pipeline_step': 'error_correction',
                                    'validation_passed': True
                                }
                            )
                            
                            self.logger.info(f"Added triplet: {triplet_id}")
                            
                            # Step 8-9: Check if we have enough triplets for clustering
                            triplet_count = self.triplet_manager.get_triplet_count()
                            self.logger.info(f"Current triplet count: {triplet_count}")
                            
                            if triplet_count >= self.config.MIN_TRIPLET_COUNT:
                                self.logger.info("Step 8-9: Running clustering and rule consolidation")
                                self._run_clustering_and_rule_consolidation()
                            else:
                                self.logger.info(f"Not enough triplets for clustering: {triplet_count} < {self.config.MIN_TRIPLET_COUNT}")
                        else:
                            self.logger.warning("Rule validation failed - rule does not catch the error")
                    else:
                        self.logger.warning("Failed to generate rule from explanation")
                else:
                    self.logger.warning("Failed to generate explanation")
            
            self.logger.info(f"Pipeline completed: final_sql={final_sql}, is_correct={is_correct}")
            return final_sql, is_correct
            
        except Exception as e:
            self.logger.error(f"Error in pipeline execution: {e}")
            # Return original query if pipeline fails
            return generated_sql if 'generated_sql' in locals() else nl_query, False
    
    def _call_dail_sql(self, nl_query: str) -> str:
        """
        Call DAIL SQL to generate SQL from natural language query
        
        Args:
            nl_query: Natural language query
            
        Returns:
            Generated SQL query
        """
        try:
            # This is a placeholder for the actual DAIL SQL integration
            # In practice, you would call the DAIL SQL inference code here
            self.logger.info(f"Calling DAIL SQL for query: {nl_query}")
            
            # For demonstration, return a simple SELECT query
            # In real implementation, this would call the actual DAIL SQL model
            return f"SELECT * FROM table WHERE condition = '{nl_query}'"
            
        except Exception as e:
            self.logger.error(f"Error calling DAIL SQL: {e}")
            # Return a fallback query
            return f"SELECT * FROM table WHERE id = 1"
    
    def _validate_sql(self, sql_query: str, ground_truth_sql: Optional[str] = None) -> bool:
        """
        Validate SQL correctness
        
        Args:
            sql_query: SQL query to validate
            ground_truth_sql: Optional ground truth SQL for comparison
            
        Returns:
            True if SQL is correct, False otherwise
        """
        try:
            if ground_truth_sql:
                # Compare with ground truth
                is_correct = sql_query.strip().lower() == ground_truth_sql.strip().lower()
                self.logger.info(f"Ground truth comparison: {is_correct}")
                return is_correct
            
            # Basic syntax validation
            import sqlparse
            parsed = sqlparse.parse(sql_query)
            is_valid = len(parsed) > 0 and parsed[0] is not None
            
            # Additional validation could be added here
            # e.g., checking against database schema, executing query, etc.
            
            self.logger.info(f"Syntax validation: {is_valid}")
            return is_valid
            
        except Exception as e:
            self.logger.error(f"Error validating SQL: {e}")
            return False
    
    def _create_error_info(self, sql_query: str, ground_truth_sql: Optional[str] = None) -> ErrorInfo:
        """
        Create error information for wrong queries
        
        Args:
            sql_query: The wrong SQL query
            ground_truth_sql: Optional ground truth SQL
            
        Returns:
            ErrorInfo object
        """
        if ground_truth_sql:
            return ErrorInfo(
                error_message=f"Generated SQL does not match ground truth",
                error_type="semantic_error",
                error_code="SQL_MISMATCH",
                severity="high"
            )
        else:
            return ErrorInfo(
                error_message="SQL validation failed",
                error_type="validation_error",
                error_code="SQL_VALIDATION_FAILED",
                severity="medium"
            )
    
    def _extract_database_schema(self, sql_query: str) -> Optional[str]:
        """
        Extract database schema from SQL query
        
        Args:
            sql_query: SQL query to analyze
            
        Returns:
            Database schema name or None
        """
        try:
            # Simple schema extraction - in practice, this would be more sophisticated
            import re
            match = re.search(r'FROM\s+(\w+)', sql_query, re.IGNORECASE)
            if match:
                return match.group(1)
            return None
        except Exception:
            return None
    
    def _run_clustering_and_rule_consolidation(self):
        """
        Run clustering and rule consolidation when enough triplets are available
        """
        try:
            # Step 8: Hierarchical clustering
            triplets = self.triplet_manager.get_all_triplets()
            valid_clusters = self.clustering_manager.iterative_cluster_merging(
                triplets, 
                a_percent_threshold=self.config.A_PERCENT_THRESHOLD
            )
            
            if not valid_clusters:
                self.logger.info("Clustering failed: less than A% queries combined. Discarding triplets.")
                self.triplet_manager.clear_triplets()
                return
            
            # Generate combined rules from valid clusters
            combined_rules = []
            for cluster in valid_clusters:
                combined_rule = self.clustering_manager.combine_rules_in_cluster(cluster)
                combined_rules.append(combined_rule)
            
            # Step 9: Test each combined rule on correct queries
            for rule in combined_rules:
                pass_rate, failed_queries = self.rule_tester.test_rule_on_correct_queries(
                    rule, 
                    sample_size=self.config.X_SAMPLE_SIZE
                )
                
                if self.rule_tester.is_rule_safe(rule):
                    self.logger.info(f"Rule {rule['rule_id']} passed validation. Adding to rule engine.")
                    self.rule_engine.add_rule(rule)
                else:
                    self.logger.warning(f"Rule {rule['rule_id']} failed validation. Discarding rule and related queries.")
                    # Optionally remove the incorrect queries from wrong_queries DB
            
            # Clear processed triplets
            self.triplet_manager.clear_triplets()
            
        except Exception as e:
            self.logger.error(f"Error in clustering and rule consolidation: {e}")
            raise e
    
    def get_pipeline_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics about the pipeline"""
        return {
            'vector_db_stats': self.vector_db_manager.get_statistics(),
            'rule_engine_stats': self.rule_engine.get_rule_statistics(),
            'rule_tester_stats': self.rule_tester.get_safety_statistics(),
            'llm_explainer_stats': self.llm_explainer.get_explanation_statistics(),
            'rule_generator_stats': self.rule_generator.get_rule_statistics(),
            'clustering_stats': self.clustering_manager.get_clustering_statistics(),
            'triplet_stats': self.triplet_manager.get_triplet_statistics()
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of all pipeline components"""
        health_status = {
            'overall_health': True,
            'components': {},
            'issues': []
        }
        
        # Check all components
        components = {
            'vector_db_manager': self.vector_db_manager,
            'rule_engine': self.rule_engine,
            'rule_tester': self.rule_tester,
            'llm_explainer': self.llm_explainer,
            'rule_generator': self.rule_generator,
            'clustering_manager': self.clustering_manager,
            'triplet_manager': self.triplet_manager
        }
        
        for name, component in components.items():
            try:
                if hasattr(component, 'get_statistics'):
                    stats = component.get_statistics()
                    health_status['components'][name] = {'status': 'healthy', 'stats': stats}
                elif hasattr(component, 'get_safety_statistics'):
                    stats = component.get_safety_statistics()
                    health_status['components'][name] = {'status': 'healthy', 'stats': stats}
                else:
                    health_status['components'][name] = {'status': 'healthy', 'stats': {}}
            except Exception as e:
                health_status['components'][name] = {'status': 'unhealthy', 'error': str(e)}
                health_status['issues'].append(f"{name}: {e}")
                health_status['overall_health'] = False
        
        return health_status
    
    def export_pipeline_data(self, export_dir: str):
        """Export all pipeline data"""
        os.makedirs(export_dir, exist_ok=True)
        
        try:
            # Export vector DB data
            self.vector_db_manager.export_collection('correct_queries', os.path.join(export_dir, 'correct_queries.json'))
            self.vector_db_manager.export_collection('wrong_queries', os.path.join(export_dir, 'wrong_queries.json'))
            
            # Export rules
            self.rule_engine.export_rules(os.path.join(export_dir, 'rules.json'))
            
            # Export explanations
            self.llm_explainer.export_explanations(os.path.join(export_dir, 'explanations.json'))
            
            # Export generated rules
            self.rule_generator.export_generated_rules(os.path.join(export_dir, 'generated_rules.json'))
            
            # Export clustering data
            self.clustering_manager.export_generated_rules(os.path.join(export_dir, 'clusters.json'))
            
            # Export triplets
            self.triplet_manager.export_triplets(os.path.join(export_dir, 'triplets.json'))
            
            self.logger.info(f"Pipeline data exported to {export_dir}")
            
        except Exception as e:
            self.logger.error(f"Error exporting pipeline data: {e}")
    
    def clear_pipeline_data(self):
        """Clear all pipeline data"""
        try:
            self.vector_db_manager.clear_all_data()
            self.rule_engine.clear_all_rules()
            self.llm_explainer.clear_explanations()
            self.rule_generator.clear_generated_rules()
            self.clustering_manager.clear_all_data()
            self.triplet_manager.clear_triplets()
            
            self.logger.info("All pipeline data cleared")
            
        except Exception as e:
            self.logger.error(f"Error clearing pipeline data: {e}")
