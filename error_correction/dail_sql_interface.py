"""
DAIL SQL Interface for Error Correction Pipeline

This module provides a clean interface to the DAIL SQL model for text-to-SQL generation.
It wraps the existing DAIL SQL inference code and provides additional validation utilities.
"""

import os
import logging
import json
from typing import Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass
import sqlite3

import sqlparse
import sqlvalidator
from llm.chatgpt import init_chatgpt, ask_llm
from utils.enums import LLM
from utils.post_process import process_duplication, get_sqls
from error_correction.config import ErrorCorrectionConfig


@dataclass
class SqlExecutionResult:
    """Data class for SQL execution results"""
    success: bool
    rows: Optional[list] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    execution_time: Optional[float] = None


@dataclass
class ErrorInfo:
    """Data class for error information"""
    error_type: str
    error_message: str
    error_code: Optional[str] = None
    stack_trace: Optional[str] = None


class DAILSQLInterface:
    """Interface class for DAIL SQL model integration"""
    
    def __init__(self, config: ErrorCorrectionConfig):
        """
        Initialize the DAIL SQL interface
        
        Args:
            config: Configuration object containing necessary parameters
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize OpenAI client
        init_chatgpt(
            OPENAI_API_KEY=config.LLM_API_KEY,
            OPENAI_GROUP_ID=config.OPENAI_GROUP_ID,
            model=config.LLM_MODEL,
            OPENAI_API_BASE=config.OPENAI_API_BASE
        )
        
        # Set up logging
        self._setup_logging()
    
    def _setup_logging(self):
        """Setup logging for the interface"""
        logging.basicConfig(
            level=getattr(logging, self.config.LOG_LEVEL),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.config.LOG_FILE),
                logging.StreamHandler()
            ]
        )
    
    def call_dail_sql(self, nl_query: str, database_schema: Optional[str] = None) -> str:
        """
        Call DAIL SQL to convert natural language to SQL
        
        Args:
            nl_query: Natural language query
            database_schema: Optional database schema information
            
        Returns:
            Generated SQL query string
        
        Raises:
            Exception: If DAIL SQL generation fails
        """
        try:
            self.logger.info(f"Generating SQL for query: {nl_query[:100]}...")
            
            # Prepare prompt with schema if provided
            if database_schema:
                prompt = f"Database Schema:\n{database_schema}\n\nQuery: {nl_query}"
            else:
                prompt = nl_query
            
            # Call DAIL SQL model
            result = ask_llm(
                model=self.config.LLM_MODEL,
                batch=[prompt],
                temperature=self.config.TEMPERATURE,
                n=1
            )
            
            # Process the result
            sql = result["response"][0]
            sql = process_duplication(sql)
            
            # Ensure query starts with SELECT
            if not sql.strip().upper().startswith("SELECT"):
                sql = "SELECT " + sql.strip()
            
            self.logger.info(f"Generated SQL: {sql}")
            return sql
            
        except Exception as e:
            self.logger.error(f"Error generating SQL: {e}")
            raise
    
    def execute_sql(self, sql_query: str, database: str) -> Tuple[Optional[list], Optional[ErrorInfo]]:
        """
        Execute a SQL query against a database
        
        Args:
            sql_query: SQL query to execute
            database: Path to SQLite database file
            
        Returns:
            Tuple of (results, error_info). If execution succeeds, error_info will be None.
            If execution fails, results will be None and error_info will contain error details.
        """
        try:
            self.logger.info(f"Executing SQL query: {sql_query[:100]}...")
            
            # Validate database path
            if not os.path.exists(database):
                raise FileNotFoundError(f"Database file not found: {database}")
            
            # Connect to database
            with sqlite3.connect(database) as conn:
                cursor = conn.cursor()
                
                try:
                    # Execute query
                    cursor.execute(sql_query)
                    results = cursor.fetchall()
                    
                    # Get column names
                    column_names = [description[0] for description in cursor.description]
                    
                    # Format results as list of dictionaries
                    formatted_results = []
                    for row in results:
                        formatted_results.append(dict(zip(column_names, row)))
                    
                    self.logger.info(f"Query executed successfully. {len(formatted_results)} rows returned.")
                    return formatted_results, None
                    
                except sqlite3.Error as e:
                    error_info = ErrorInfo(
                        error_type="sql_execution_error",
                        error_message=str(e),
                        error_code=str(e.args[0]) if e.args else None
                    )
                    self.logger.error(f"SQL execution error: {e}")
                    return None, error_info
                
        except Exception as e:
            self.logger.error(f"Error executing SQL: {e}")
            error_info = ErrorInfo(
                error_type="execution_error",
                error_message=str(e)
            )
            return None, error_info
    
    def validate_sql_correctness(self, generated_sql: str, ground_truth_sql: str, database: str) -> bool:
        """
        Validate if generated SQL is correct by comparing with ground truth
        
        Args:
            generated_sql: Generated SQL query to validate
            ground_truth_sql: Ground truth SQL query to compare against
            database: Path to SQLite database
            
        Returns:
            True if the generated SQL is semantically equivalent to ground truth
        """
        try:
            self.logger.info("Validating SQL correctness...")
            
            # Step 1: Basic syntax validation
            if not self._validate_syntax(generated_sql):
                self.logger.warning("Generated SQL failed syntax validation")
                return False
            
            # Step 2: Execute both queries and compare results
            generated_results, gen_error = self.execute_sql(generated_sql, database)
            if gen_error:
                self.logger.warning("Generated SQL execution failed")
                return False
            
            ground_truth_results, gt_error = self.execute_sql(ground_truth_sql, database)
            if gt_error:
                self.logger.error("Ground truth SQL execution failed")
                return False
            
            # Compare results
            return self._compare_query_results(generated_results, ground_truth_results)
            
        except Exception as e:
            self.logger.error(f"Error validating SQL correctness: {e}")
            return False
    
    def _validate_syntax(self, sql_query: str) -> bool:
        """
        Validate SQL syntax
        
        Args:
            sql_query: SQL query to validate
            
        Returns:
            True if syntax is valid
        """
        try:
            # Parse with sqlparse
            parsed = sqlparse.parse(sql_query)
            if not parsed or not parsed[0]:
                return False
            
            # Additional validation with sqlvalidator
            validation = sqlvalidator.parse(sql_query)
            return validation.is_valid()
            
        except Exception as e:
            self.logger.error(f"Error in syntax validation: {e}")
            return False
    
    def _compare_query_results(self, results1: list, results2: list) -> bool:
        """
        Compare two query results for semantic equivalence
        
        Args:
            results1: First query results
            results2: Second query results
            
        Returns:
            True if results are semantically equivalent
        """
        if results1 is None or results2 is None:
            return False
        
        try:
            # Convert results to sets of tuples for comparison
            set1 = {tuple(sorted(d.items())) for d in results1}
            set2 = {tuple(sorted(d.items())) for d in results2}
            
            # Compare result sets
            return set1 == set2
            
        except Exception as e:
            self.logger.error(f"Error comparing query results: {e}")
            return False