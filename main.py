"""
Main entry point for the Error Correction Pipeline.

This module provides a command-line interface for running the error correction pipeline
in different modes: single query, batch processing, and evaluation.
"""

# Disable torchvision beta warnings
import warnings
import torchvision
torchvision.disable_beta_transforms_warning()

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from tqdm import tqdm
import pandas as pd
from sklearn.metrics import precision_recall_fscore_support, accuracy_score

from error_correction.config import ErrorCorrectionConfig
from error_correction.pipeline_orchestrator import ErrorCorrectionPipeline
from error_correction.dail_sql_interface import DAILSQLInterface
from error_correction.vector_db_manager import VectorDBManager
from error_correction.rule_engine import RuleEngine
from error_correction.llm_explainer import LLMExplainer
from error_correction.rule_generator import RuleGenerator
from error_correction.clustering_manager import ClusteringManager


@dataclass
class EvaluationMetrics:
    """Data class for evaluation metrics"""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    rule_coverage: float
    correction_rate: float
    error_reduction: float
    total_queries: int
    successful_corrections: int
    failed_corrections: int
    rules_applied: int
    avg_confidence: float
    execution_time: float


@dataclass
class BatchProcessingResult:
    """Data class for batch processing results"""
    total_queries: int
    processed_queries: int
    successful_corrections: int
    failed_corrections: int
    rules_applied: Dict[str, int]
    error_types: Dict[str, int]
    avg_processing_time: float
    avg_confidence: float


class ErrorCorrectionCLI:
    """Command-line interface for the error correction pipeline"""
    
    def __init__(self):
        """Initialize the CLI interface"""
        self.config = ErrorCorrectionConfig()
        self.logger = self._setup_logging()
        
        # Initialize pipeline and components
        self.pipeline = ErrorCorrectionPipeline(self.config)
        self.dail_sql = DAILSQLInterface(self.config)
        
        self.logger.info("Error Correction CLI initialized")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logging.basicConfig(
            level=getattr(logging, self.config.LOG_LEVEL),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.config.LOG_FILE),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)
    
    def _validate_args(self, args: argparse.Namespace):
        """Validate command line arguments"""
        if args.mode == "single" and not args.query:
            raise ValueError("Query is required for single mode")
        
        if args.mode in ["batch", "evaluate"] and not args.input_file:
            raise ValueError("Input file is required for batch and evaluate modes")
        
        if args.input_file and not os.path.exists(args.input_file):
            raise FileNotFoundError(f"Input file not found: {args.input_file}")
    
    def process_single_query(self, query: str, enable_error_correction: bool) -> Dict[str, Any]:
        """Process a single query through the pipeline"""
        self.logger.info(f"Processing query: {query}")
        start_time = datetime.now()
        
        try:
            # Generate SQL with DAIL SQL
            sql = self.dail_sql.call_dail_sql(query, None)
            
            if enable_error_correction:
                # Run through error correction pipeline
                corrected_sql, is_correct = self.pipeline.run_pipeline(query, sql)
                
                return {
                    "original_query": query,
                    "dail_sql_output": sql,
                    "corrected_sql": corrected_sql,
                    "is_correct": is_correct,
                    "processing_time": (datetime.now() - start_time).total_seconds(),
                    "error_correction_applied": True
                }
            else:
                return {
                    "original_query": query,
                    "dail_sql_output": sql,
                    "corrected_sql": None,
                    "is_correct": None,
                    "processing_time": (datetime.now() - start_time).total_seconds(),
                    "error_correction_applied": False
                }
                
        except Exception as e:
            self.logger.error(f"Error processing query: {e}")
            return {
                "original_query": query,
                "error": str(e),
                "processing_time": (datetime.now() - start_time).total_seconds()
            }
    
    def process_batch(self, input_file: str, enable_error_correction: bool) -> BatchProcessingResult:
        """Process queries in batch mode"""
        self.logger.info(f"Starting batch processing from {input_file}")
        start_time = datetime.now()
        
        try:
            # Read queries from file
            with open(input_file, 'r') as f:
                queries = json.load(f)
            
            results = []
            rules_applied = {}
            error_types = {}
            
            # Process each query
            for query in tqdm(queries, desc="Processing queries"):
                result = self.process_single_query(query, enable_error_correction)
                results.append(result)
                
                if result.get("rules_applied"):
                    for rule in result["rules_applied"]:
                        rules_applied[rule] = rules_applied.get(rule, 0) + 1
                
                if result.get("error_type"):
                    error_types[result["error_type"]] = error_types.get(result["error_type"], 0) + 1
            
            # Calculate statistics
            successful = sum(1 for r in results if r.get("is_correct", False))
            failed = len(results) - successful
            avg_time = sum(r["processing_time"] for r in results) / len(results)
            avg_confidence = sum(r.get("confidence", 0) for r in results) / len(results) if any(r.get("confidence") for r in results) else 0
            
            return BatchProcessingResult(
                total_queries=len(queries),
                processed_queries=len(results),
                successful_corrections=successful,
                failed_corrections=failed,
                rules_applied=rules_applied,
                error_types=error_types,
                avg_processing_time=avg_time,
                avg_confidence=avg_confidence
            )
            
        except Exception as e:
            self.logger.error(f"Error in batch processing: {e}")
            raise
    
    def evaluate(self, input_file: str) -> Tuple[EvaluationMetrics, EvaluationMetrics]:
        """
        Evaluate pipeline performance with and without error correction
        
        Returns:
            Tuple of metrics (without_correction, with_correction)
        """
        self.logger.info(f"Starting evaluation using {input_file}")
        
        try:
            # Read test set with ground truth
            with open(input_file, 'r') as f:
                test_data = json.load(f)
            
            # Lists to store predictions and ground truth
            y_true = []
            y_pred_with_correction = []
            y_pred_without_correction = []
            
            # Process queries with and without correction
            results_with_correction = []
            results_without_correction = []
            
            for item in tqdm(test_data, desc="Evaluating queries"):
                # Process without correction
                result_without = self.process_single_query(item["query"], False)
                results_without_correction.append(result_without)
                y_pred_without_correction.append(
                    self.dail_sql.validate_sql_correctness(
                        result_without["dail_sql_output"],
                        item["ground_truth"],
                        item["database"]
                    )
                )
                
                # Process with correction
                result_with = self.process_single_query(item["query"], True)
                results_with_correction.append(result_with)
                y_pred_with_correction.append(
                    self.dail_sql.validate_sql_correctness(
                        result_with["corrected_sql"],
                        item["ground_truth"],
                        item["database"]
                    )
                )
                
                # Store ground truth
                y_true.append(True)  # Since we're comparing against ground truth
            
            # Calculate metrics without correction
            metrics_without = self._calculate_metrics(
                y_true,
                y_pred_without_correction,
                results_without_correction
            )
            
            # Calculate metrics with correction
            metrics_with = self._calculate_metrics(
                y_true,
                y_pred_with_correction,
                results_with_correction
            )
            
            return metrics_without, metrics_with
            
        except Exception as e:
            self.logger.error(f"Error in evaluation: {e}")
            raise
    
    def _calculate_metrics(self, y_true: List[bool], y_pred: List[bool], results: List[Dict]) -> EvaluationMetrics:
        """Calculate evaluation metrics"""
        # Calculate precision, recall, F1
        precision, recall, f1, _ = precision_recall_fscore_support(
            y_true, y_pred, average='binary', zero_division=0
        )
        
        # Calculate accuracy
        accuracy = accuracy_score(y_true, y_pred)
        
        # Calculate rule coverage and other metrics
        total_queries = len(results)
        successful = sum(1 for r in results if r.get("is_correct", False))
        failed = total_queries - successful
        rules_applied = sum(len(r.get("rules_applied", [])) for r in results)
        rule_coverage = rules_applied / total_queries if total_queries > 0 else 0
        
        # Calculate average confidence and execution time
        avg_confidence = sum(r.get("confidence", 0) for r in results) / total_queries if total_queries > 0 else 0
        avg_time = sum(r["processing_time"] for r in results) / total_queries if total_queries > 0 else 0
        
        # Calculate error reduction
        baseline_errors = sum(1 for x in y_true if not x)
        final_errors = sum(1 for x in y_pred if not x)
        error_reduction = (baseline_errors - final_errors) / baseline_errors if baseline_errors > 0 else 0
        
        return EvaluationMetrics(
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1_score=f1,
            rule_coverage=rule_coverage,
            correction_rate=successful / total_queries if total_queries > 0 else 0,
            error_reduction=error_reduction,
            total_queries=total_queries,
            successful_corrections=successful,
            failed_corrections=failed,
            rules_applied=rules_applied,
            avg_confidence=avg_confidence,
            execution_time=avg_time
        )
    
    def save_results(self, results: Any, output_file: str):
        """Save results to file"""
        try:
            # Create output directory if it doesn't exist
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            # Convert results to JSON-serializable format
            if hasattr(results, "__dict__"):
                results = asdict(results)
            
            # Save as JSON
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2)
            
            self.logger.info(f"Results saved to {output_file}")
            
        except Exception as e:
            self.logger.error(f"Error saving results: {e}")
            raise
    
    def generate_report(self, results: Any, output_file: str):
        """Generate detailed report of results"""
        try:
            # Create report directory
            report_dir = os.path.dirname(output_file)
            os.makedirs(report_dir, exist_ok=True)
            
            # Convert results to pandas DataFrame for analysis
            if isinstance(results, (BatchProcessingResult, EvaluationMetrics)):
                df = pd.DataFrame([asdict(results)])
            elif isinstance(results, dict):
                df = pd.DataFrame([results])
            else:
                df = pd.DataFrame(results)
            
            # Generate plots
            if not df.empty:
                # Success rate plot
                success_plot = df['successful_corrections'].plot(
                    kind='bar',
                    title='Successful vs Failed Corrections'
                )
                success_plot.figure.savefig(os.path.join(report_dir, 'success_rate.png'))
                
                # Error types distribution
                if 'error_types' in df.columns:
                    error_plot = df['error_types'].value_counts().plot(
                        kind='pie',
                        title='Error Type Distribution'
                    )
                    error_plot.figure.savefig(os.path.join(report_dir, 'error_types.png'))
            
            # Save detailed statistics
            stats_file = os.path.join(report_dir, 'statistics.txt')
            with open(stats_file, 'w') as f:
                f.write("Error Correction Pipeline Results\n")
                f.write("===============================\n\n")
                
                if isinstance(results, BatchProcessingResult):
                    f.write(f"Total Queries: {results.total_queries}\n")
                    f.write(f"Successful Corrections: {results.successful_corrections}\n")
                    f.write(f"Failed Corrections: {results.failed_corrections}\n")
                    f.write(f"Average Processing Time: {results.avg_processing_time:.2f}s\n")
                    f.write(f"Average Confidence: {results.avg_confidence:.2%}\n\n")
                    
                    f.write("Rules Applied:\n")
                    for rule, count in results.rules_applied.items():
                        f.write(f"  - {rule}: {count}\n")
                    
                    f.write("\nError Types:\n")
                    for error_type, count in results.error_types.items():
                        f.write(f"  - {error_type}: {count}\n")
                
                elif isinstance(results, EvaluationMetrics):
                    f.write(f"Accuracy: {results.accuracy:.2%}\n")
                    f.write(f"Precision: {results.precision:.2%}\n")
                    f.write(f"Recall: {results.recall:.2%}\n")
                    f.write(f"F1 Score: {results.f1_score:.2%}\n")
                    f.write(f"Rule Coverage: {results.rule_coverage:.2%}\n")
                    f.write(f"Error Reduction: {results.error_reduction:.2%}\n")
                    f.write(f"Total Queries: {results.total_queries}\n")
                    f.write(f"Successful Corrections: {results.successful_corrections}\n")
                    f.write(f"Failed Corrections: {results.failed_corrections}\n")
                    f.write(f"Rules Applied: {results.rules_applied}\n")
                    f.write(f"Average Confidence: {results.avg_confidence:.2%}\n")
                    f.write(f"Average Execution Time: {results.execution_time:.2f}s\n")
            
            self.logger.info(f"Report generated in {report_dir}")
            
        except Exception as e:
            self.logger.error(f"Error generating report: {e}")
            raise


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Error Correction Pipeline CLI")
    
    parser.add_argument(
        "--mode",
        choices=["single", "batch", "evaluate"],
        required=True,
        help="Operation mode"
    )
    parser.add_argument(
        "--query",
        help="Natural language query (for single mode)"
    )
    parser.add_argument(
        "--input_file",
        help="Path to input file (for batch and evaluate modes)"
    )
    parser.add_argument(
        "--output_file",
        help="Path to output file"
    )
    parser.add_argument(
        "--enable_error_correction",
        action="store_true",
        help="Enable error correction"
    )
    
    args = parser.parse_args()
    
    try:
        # Initialize CLI
        cli = ErrorCorrectionCLI()
        
        # Validate arguments
        cli.logger.info("Validating arguments...")
        cli._validate_args(args)
        
        # Process based on mode
        if args.mode == "single":
            cli.logger.info("Running in single query mode...")
            result = cli.process_single_query(args.query, args.enable_error_correction)
            
            if args.output_file:
                cli.save_results(result, args.output_file)
            else:
                print(json.dumps(result, indent=2))
        
        elif args.mode == "batch":
            cli.logger.info("Running in batch mode...")
            result = cli.process_batch(args.input_file, args.enable_error_correction)
            
            if args.output_file:
                cli.save_results(result, args.output_file)
                cli.generate_report(result, args.output_file + "_report")
            else:
                print(json.dumps(asdict(result), indent=2))
        
        elif args.mode == "evaluate":
            cli.logger.info("Running in evaluation mode...")
            metrics_without, metrics_with = cli.evaluate(args.input_file)
            
            if args.output_file:
                results = {
                    "without_correction": asdict(metrics_without),
                    "with_correction": asdict(metrics_with)
                }
                cli.save_results(results, args.output_file)
                cli.generate_report(results, args.output_file + "_report")
            else:
                print("\nMetrics without correction:")
                print(json.dumps(asdict(metrics_without), indent=2))
                print("\nMetrics with correction:")
                print(json.dumps(asdict(metrics_with), indent=2))
        
        cli.logger.info("Processing completed successfully")
        
    except Exception as e:
        logging.error(f"Error in main execution: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()