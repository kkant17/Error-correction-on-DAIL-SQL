"""
LLM Explainer for Error Correction Pipeline

This module handles generating explanations for SQL query errors using Large Language Models.
It provides functionality to analyze queries, identify errors, and generate human-readable explanations.
"""

import os
import json
import logging
import time
import requests
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import openai
from .config import ErrorCorrectionConfig


@dataclass
class ErrorInfo:
    """Data class for error information"""
    error_message: str
    error_type: str = "unknown"
    error_code: Optional[str] = None
    stack_trace: Optional[str] = None
    severity: str = "medium"  # low, medium, high, critical


@dataclass
class Explanation:
    """Data class for storing explanation information"""
    explanation_id: str
    nl_query: str
    sql_query: str
    error_info: ErrorInfo
    root_cause: str
    violated_pattern: str
    correct_pattern: str
    general_rule: str
    confidence: float
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None


class LLMExplainer:
    """LLM-based explainer for SQL query errors with support for multiple LLM backends"""
    
    def __init__(self, config: ErrorCorrectionConfig, api_key: Optional[str] = None):
        """
        Initialize the LLMExplainer
        
        Args:
            config: Configuration object containing parameters
            api_key: API key for LLM service (if None, will use environment variable)
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.api_key = api_key or os.getenv('OPENAI_API_KEY') or config.LLM_API_KEY
        
        # Initialize LLM client based on model type
        self._initialize_llm_client()
        
        # Load existing explanations
        self.explanations: List[Explanation] = []
        self._load_explanations()
    
    def _initialize_llm_client(self):
        """Initialize the appropriate LLM client based on configuration"""
        model_name = self.config.LLM_MODEL.lower()
        
        if 'gpt' in model_name or 'openai' in model_name:
            self.llm_type = "openai"
            if not self.api_key:
                raise ValueError("OpenAI API key is required for OpenAI models. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
            openai.api_key = self.api_key
            self.logger.info("Initialized OpenAI client")
            
        elif 'llama' in model_name or 'ollama' in model_name:
            self.llm_type = "ollama"
            self.ollama_base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
            self.logger.info(f"Initialized Ollama client with base URL: {self.ollama_base_url}")
            
        elif 'vllm' in model_name:
            self.llm_type = "vllm"
            self.vllm_base_url = os.getenv('VLLM_BASE_URL', 'http://localhost:8000')
            self.logger.info(f"Initialized vLLM client with base URL: {self.vllm_base_url}")
            
        else:
            # Default to OpenAI
            self.llm_type = "openai"
            if not self.api_key:
                raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
            openai.api_key = self.api_key
            self.logger.warning(f"Unknown model type: {model_name}. Defaulting to OpenAI.")
    
    def generate_explanation(self, nl_query: str, sql_query: str, error_info: ErrorInfo) -> Dict[str, Any]:
        """
        Generate an explanation for a SQL query error
        
        Args:
            nl_query: Natural language query
            sql_query: Generated SQL query that has an error
            error_info: Error information
            
        Returns:
            Dictionary containing the explanation
        """
        self.logger.info(f"Generating explanation for query: {nl_query[:50]}...")
        
        # Build the structured prompt
        prompt = self._build_structured_prompt(nl_query, sql_query, error_info)
        
        # Generate explanation with retry logic
        explanation_data = self._call_llm_with_retry(prompt)
        
        # Validate the explanation format
        if not self.validate_explanation_format(explanation_data):
            self.logger.warning("Generated explanation format is invalid, using fallback")
            explanation_data = self._create_fallback_explanation(nl_query, sql_query, error_info)
        
        # Create explanation object
        explanation = Explanation(
            explanation_id=f"exp_{len(self.explanations)}_{int(time.time())}",
            nl_query=nl_query,
            sql_query=sql_query,
            error_info=error_info,
            root_cause=explanation_data.get('root_cause', 'Unknown'),
            violated_pattern=explanation_data.get('violated_pattern', 'Unknown'),
            correct_pattern=explanation_data.get('correct_pattern', 'Unknown'),
            general_rule=explanation_data.get('general_rule', 'Unknown'),
            confidence=explanation_data.get('confidence', 0.5),
            metadata={
                'model': self.config.LLM_MODEL,
                'llm_type': self.llm_type,
                'generation_time': datetime.now().isoformat()
            },
            created_at=datetime.now().isoformat()
        )
        
        # Store explanation
        self.explanations.append(explanation)
        self._save_explanations()
        
        self.logger.info(f"Generated explanation with confidence: {explanation.confidence}")
        return explanation_data
    
    def _build_structured_prompt(self, nl_query: str, sql_query: str, error_info: ErrorInfo) -> str:
        """Build the structured prompt for explanation generation"""
        prompt = f"""Given the natural language query: '{nl_query}'
The generated SQL query: '{sql_query}'
Resulted in error: '{error_info.error_message}'

Analyze why this SQL query is incorrect. Provide:
1. Root cause of the error
2. What SQL pattern was violated
3. The correct SQL pattern that should be used
4. General rule to prevent this error in future queries

Format your response as JSON with keys: 
'root_cause', 'violated_pattern', 'correct_pattern', 'general_rule', 'confidence'

Be specific and technical in your analysis. Focus on SQL syntax, semantics, and best practices."""
        
        return prompt
    
    def _call_llm_with_retry(self, prompt: str, max_retries: int = 3) -> Dict[str, Any]:
        """Call LLM with retry logic"""
        for attempt in range(max_retries):
            try:
                if self.llm_type == "openai":
                    return self._call_openai(prompt)
                elif self.llm_type == "ollama":
                    return self._call_ollama(prompt)
                elif self.llm_type == "vllm":
                    return self._call_vllm(prompt)
                else:
                    raise ValueError(f"Unknown LLM type: {self.llm_type}")
                    
            except Exception as e:
                self.logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    self.logger.error(f"All {max_retries} attempts failed")
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff
        
        return {}
    
    def _call_openai(self, prompt: str) -> Dict[str, Any]:
        """Call OpenAI API"""
        try:
            response = openai.ChatCompletion.create(
                model=self.config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.config.MAX_TOKENS,
                temperature=self.config.TEMPERATURE
            )
            
            response_text = response.choices[0].message.content.strip()
            return self._parse_json_response(response_text)
            
        except Exception as e:
            self.logger.error(f"OpenAI API call failed: {e}")
            raise
    
    def _call_ollama(self, prompt: str) -> Dict[str, Any]:
        """Call Ollama API"""
        try:
            url = f"{self.ollama_base_url}/api/generate"
            data = {
                "model": self.config.LLM_MODEL,
                "prompt": f"{self._get_system_prompt()}\n\n{prompt}",
                "stream": False,
                "options": {
                    "temperature": self.config.TEMPERATURE,
                    "max_tokens": self.config.MAX_TOKENS
                }
            }
            
            response = requests.post(url, json=data, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            response_text = result.get('response', '').strip()
            return self._parse_json_response(response_text)
            
        except Exception as e:
            self.logger.error(f"Ollama API call failed: {e}")
            raise
    
    def _call_vllm(self, prompt: str) -> Dict[str, Any]:
        """Call vLLM API"""
        try:
            url = f"{self.vllm_base_url}/v1/chat/completions"
            data = {
                "model": self.config.LLM_MODEL,
                "messages": [
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": self.config.MAX_TOKENS,
                "temperature": self.config.TEMPERATURE
            }
            
            response = requests.post(url, json=data, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            response_text = result['choices'][0]['message']['content'].strip()
            return self._parse_json_response(response_text)
            
        except Exception as e:
            self.logger.error(f"vLLM API call failed: {e}")
            raise
    
    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON response from LLM"""
        try:
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                parsed = json.loads(json_str)
                
                # Validate required fields
                required_fields = ['root_cause', 'violated_pattern', 'correct_pattern', 'general_rule']
                if all(field in parsed for field in required_fields):
                    return parsed
            
            # If no valid JSON found, try to parse the entire response
            return json.loads(response_text)
            
        except json.JSONDecodeError as e:
            self.logger.warning(f"Failed to parse JSON response: {e}")
            return self._create_fallback_explanation_data(response_text)
        except Exception as e:
            self.logger.error(f"Error parsing response: {e}")
            return self._create_fallback_explanation_data(response_text)
    
    def _create_fallback_explanation_data(self, response_text: str) -> Dict[str, Any]:
        """Create fallback explanation data when JSON parsing fails"""
        return {
            'root_cause': 'Unable to parse LLM response',
            'violated_pattern': 'Unknown',
            'correct_pattern': 'Unknown',
            'general_rule': 'Review SQL syntax and semantics',
            'confidence': 0.1
        }
    
    def _create_fallback_explanation(self, nl_query: str, sql_query: str, error_info: ErrorInfo) -> Dict[str, Any]:
        """Create a fallback explanation when LLM fails"""
        return {
            'root_cause': f'SQL query failed with error: {error_info.error_message}',
            'violated_pattern': 'Unknown SQL pattern',
            'correct_pattern': 'Valid SQL syntax required',
            'general_rule': 'Ensure proper SQL syntax and semantics',
            'confidence': 0.1
        }
    
    def validate_explanation_format(self, explanation: Dict[str, Any]) -> bool:
        """
        Validate that the explanation has the required format
        
        Args:
            explanation: Dictionary containing the explanation
            
        Returns:
            True if format is valid, False otherwise
        """
        required_fields = ['root_cause', 'violated_pattern', 'correct_pattern', 'general_rule']
        
        # Check if all required fields are present
        if not all(field in explanation for field in required_fields):
            self.logger.warning(f"Missing required fields in explanation: {required_fields}")
            return False
        
        # Check if fields are not empty
        for field in required_fields:
            if not explanation[field] or explanation[field].strip() == '':
                self.logger.warning(f"Empty field in explanation: {field}")
                return False
        
        # Check confidence score if present
        if 'confidence' in explanation:
            confidence = explanation['confidence']
            if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                self.logger.warning(f"Invalid confidence score: {confidence}")
                return False
        
        return True
    
    def batch_generate_explanations(self, query_data: List[Tuple[str, str, ErrorInfo]]) -> List[Dict[str, Any]]:
        """
        Generate explanations for multiple queries in batch
        
        Args:
            query_data: List of tuples containing (nl_query, sql_query, error_info)
            
        Returns:
            List of explanation dictionaries
        """
        explanations = []
        
        for nl_query, sql_query, error_info in query_data:
            try:
                explanation = self.generate_explanation(nl_query, sql_query, error_info)
                explanations.append(explanation)
            except Exception as e:
                self.logger.error(f"Error generating explanation for query: {e}")
                fallback = self._create_fallback_explanation(nl_query, sql_query, error_info)
                explanations.append(fallback)
        
        return explanations
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for the LLM"""
        return """You are an expert SQL analyst and database administrator with deep knowledge of SQL syntax, semantics, and best practices. Your task is to analyze SQL query errors and provide clear, accurate explanations.

Key guidelines:
1. Be precise and technical in your analysis
2. Identify the root cause of errors, not just symptoms
3. Provide actionable insights for improvement
4. Consider both syntax and semantic correctness
5. Be concise but comprehensive in your explanations
6. Always provide a confidence score (0.0-1.0) for your analysis
7. Format your response as valid JSON

Focus on helping users understand and fix their SQL queries effectively."""
    
    def _load_explanations(self):
        """Load existing explanations from disk"""
        explanations_file = os.path.join(self.config.TRIPLETS_DIR, "explanations.json")
        if os.path.exists(explanations_file):
            try:
                with open(explanations_file, 'r') as f:
                    data = json.load(f)
                    for exp_data in data:
                        # Convert old format to new format if needed
                        if 'error_info' in exp_data:
                            error_info = ErrorInfo(**exp_data['error_info'])
                        else:
                            error_info = ErrorInfo(
                                error_message=exp_data.get('error_message', 'Unknown error'),
                                error_type=exp_data.get('error_type', 'unknown')
                            )
                        
                        explanation = Explanation(
                            explanation_id=exp_data['explanation_id'],
                            nl_query=exp_data.get('nl_query', ''),
                            sql_query=exp_data.get('sql_query', ''),
                            error_info=error_info,
                            root_cause=exp_data.get('root_cause', ''),
                            violated_pattern=exp_data.get('violated_pattern', ''),
                            correct_pattern=exp_data.get('correct_pattern', ''),
                            general_rule=exp_data.get('general_rule', ''),
                            confidence=exp_data.get('confidence', 0.5),
                            metadata=exp_data.get('metadata'),
                            created_at=exp_data.get('created_at')
                        )
                        self.explanations.append(explanation)
            except Exception as e:
                self.logger.warning(f"Could not load explanations: {e}")
    
    def _save_explanations(self):
        """Save explanations to disk"""
        data = []
        for explanation in self.explanations:
            exp_data = {
                'explanation_id': explanation.explanation_id,
                'nl_query': explanation.nl_query,
                'sql_query': explanation.sql_query,
                'error_info': {
                    'error_message': explanation.error_info.error_message,
                    'error_type': explanation.error_info.error_type,
                    'error_code': explanation.error_info.error_code,
                    'stack_trace': explanation.error_info.stack_trace,
                    'severity': explanation.error_info.severity
                },
                'root_cause': explanation.root_cause,
                'violated_pattern': explanation.violated_pattern,
                'correct_pattern': explanation.correct_pattern,
                'general_rule': explanation.general_rule,
                'confidence': explanation.confidence,
                'metadata': explanation.metadata,
                'created_at': explanation.created_at
            }
            data.append(exp_data)
        
        with open(os.path.join(self.config.TRIPLETS_DIR, "explanations.json"), 'w') as f:
            json.dump(data, f, indent=2)
    
    def get_explanation_by_id(self, explanation_id: str) -> Optional[Explanation]:
        """Get an explanation by ID"""
        for explanation in self.explanations:
            if explanation.explanation_id == explanation_id:
                return explanation
        return None
    
    def get_explanations_by_error_type(self, error_type: str) -> List[Explanation]:
        """Get all explanations of a specific error type"""
        return [exp for exp in self.explanations if exp.error_info.error_type == error_type]
    
    def get_high_confidence_explanations(self, min_confidence: float = None) -> List[Explanation]:
        """Get explanations with confidence above threshold"""
        if min_confidence is None:
            min_confidence = self.config.CONFIDENCE_THRESHOLD
        
        return [exp for exp in self.explanations if exp.confidence >= min_confidence]
    
    def get_explanation_statistics(self) -> Dict[str, Any]:
        """Get statistics about stored explanations"""
        if not self.explanations:
            return {
                'total_explanations': 0,
                'explanations_by_error_type': {},
                'average_confidence': 0.0
            }
        
        error_types = {}
        for explanation in self.explanations:
            error_type = explanation.error_info.error_type
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        return {
            'total_explanations': len(self.explanations),
            'explanations_by_error_type': error_types,
            'average_confidence': sum(exp.confidence for exp in self.explanations) / len(self.explanations),
            'high_confidence_count': len(self.get_high_confidence_explanations())
        }
    
    def export_explanations(self, file_path: str):
        """Export explanations to a file"""
        with open(file_path, 'w') as f:
            json.dump([{
                'explanation_id': exp.explanation_id,
                'nl_query': exp.nl_query,
                'sql_query': exp.sql_query,
                'error_info': {
                    'error_message': exp.error_info.error_message,
                    'error_type': exp.error_info.error_type,
                    'error_code': exp.error_info.error_code,
                    'stack_trace': exp.error_info.stack_trace,
                    'severity': exp.error_info.severity
                },
                'root_cause': exp.root_cause,
                'violated_pattern': exp.violated_pattern,
                'correct_pattern': exp.correct_pattern,
                'general_rule': exp.general_rule,
                'confidence': exp.confidence,
                'metadata': exp.metadata,
                'created_at': exp.created_at
            } for exp in self.explanations], f, indent=2)
    
    def clear_explanations(self):
        """Clear all stored explanations"""
        self.explanations = []
        explanations_file = os.path.join(self.config.TRIPLETS_DIR, "explanations.json")
        if os.path.exists(explanations_file):
            os.remove(explanations_file)
