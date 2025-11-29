"""
Apply learned error correction rules to SQL predictions.
Generate corrected predictions and evaluate them against gold queries.
"""
import json
import argparse
import logging
import sys
import os
from typing import List, Dict
import re

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from error_correction.rule_engine.rule_applicator import RuleApplicator
from error_correction.rule_engine.rule_schema import Rule
from llm.chatgpt import init_chatgpt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CorrectionApplier:
    """
    Apply learned error correction rules to SQL predictions.
    """
    
    def __init__(self, model: str = "mistral:7b", openai_api_key: str = "", openai_api_base: str = ""):
        """
        Initialize the correction applier.
        
        Args:
            model: LLM model to use for fallback transformations
            openai_api_key: OpenAI API key (optional for local models)
            openai_api_base: API base URL (defaults to local Ollama)
        """
        self.model = model
        self.rule_applicator = RuleApplicator()
        
        # Initialize LLM if needed
        if openai_api_key or openai_api_base:
            init_chatgpt(openai_api_key or "", "", model, openai_api_base or "")
        
        # Load rules
        self.rules = self._load_rules()
        logger.info(f"Loaded {len(self.rules)} rules for correction")
    
    def _load_rules(self) -> List[Rule]:
        """Load rules from rules.json file."""
        rules_file = "error_correction/rules/rules.json"
        
        if not os.path.exists(rules_file):
            logger.warning(f"Rules file not found: {rules_file}")
            return []
        
        try:
            with open(rules_file, 'r') as f:
                rules_data = json.load(f)
            
            rules = []
            for rule_dict in rules_data:
                rule = Rule(
                    pattern=rule_dict.get('pattern', ''),
                    correction=rule_dict.get('correction', ''),
                    error_type=rule_dict.get('error_type', 'OTHER'),
                    rule_id=rule_dict.get('rule_id', '')
                )
                rules.append(rule)
            
            logger.info(f"Loaded {len(rules)} rules from {rules_file}")
            return rules
            
        except Exception as e:
            logger.error(f"Error loading rules: {e}")
            return []
    
    def correct_query(self, query: str) -> str:
        """
        Apply rules to correct a single query.
        
        Args:
            query: SQL query to correct
            
        Returns:
            Corrected query or original if no rules matched
        """
        if not query or not isinstance(query, str):
            return query
        
        # Try to find matching rules
        for rule in self.rules:
            if self.rule_applicator.matches_pattern(query, rule.pattern):
                logger.debug(f"Rule {rule.rule_id} matched, applying transformation")
                
                # Apply transformation with LLM fallback
                corrected = self.rule_applicator.apply_rule(
                    query,
                    rule,
                    use_llm=True,
                    llm_model=self.model
                )
                
                if corrected != query:
                    return corrected
        
        # No matching rules found, return original
        return query
    
    def correct_predictions(self, predictions: List[str]) -> List[str]:
        """
        Apply corrections to a list of predictions.
        
        Args:
            predictions: List of SQL query predictions
            
        Returns:
            List of corrected predictions
        """
        corrected = []
        
        for i, pred in enumerate(predictions):
            if (i + 1) % 100 == 0:
                logger.info(f"Correcting prediction {i+1}/{len(predictions)}")
            
            corrected_pred = self.correct_query(pred)
            corrected.append(corrected_pred)
        
        return corrected


def main():
    parser = argparse.ArgumentParser(
        description="Apply learned error correction rules to SQL predictions"
    )
    parser.add_argument(
        "--predictions_file", 
        type=str, 
        required=True,
        help="Path to original predictions file (one SQL query per line)"
    )
    parser.add_argument(
        "--output_file",
        type=str,
        required=True,
        help="Output file for corrected predictions"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="mistral:7b",
        help="LLM model to use for transformations"
    )
    parser.add_argument(
        "--openai_api_key",
        type=str,
        default="",
        help="OpenAI API key (optional for local models)"
    )
    parser.add_argument(
        "--openai_api_base",
        type=str,
        default="http://localhost:11434",
        help="OpenAI API base URL"
    )
    
    args = parser.parse_args()
    
    logger.info("="*60)
    logger.info("SQL Error Correction Rule Applier")
    logger.info("="*60)
    
    # Load predictions
    logger.info(f"\nLoading predictions from {args.predictions_file}...")
    try:
        with open(args.predictions_file, 'r') as f:
            predictions = [line.strip() for line in f.readlines()]
        logger.info(f"Loaded {len(predictions)} predictions")
    except Exception as e:
        logger.error(f"Error loading predictions: {e}")
        return 1
    
    # Initialize applier
    logger.info(f"\nInitializing correction applier with model={args.model}...")
    applier = CorrectionApplier(
        model=args.model,
        openai_api_key=args.openai_api_key,
        openai_api_base=args.openai_api_base
    )
    
    if not applier.rules:
        logger.warning("No rules loaded, copying predictions as-is")
        corrected_predictions = predictions
    else:
        # Apply corrections
        logger.info(f"\nApplying corrections to {len(predictions)} predictions...")
        corrected_predictions = applier.correct_predictions(predictions)
    
    # Save corrected predictions
    logger.info(f"\nSaving corrected predictions to {args.output_file}...")
    try:
        os.makedirs(os.path.dirname(args.output_file) or '.', exist_ok=True)
        with open(args.output_file, 'w') as f:
            for pred in corrected_predictions:
                f.write(pred + '\n')
        logger.info(f"✓ Saved {len(corrected_predictions)} corrected predictions")
    except Exception as e:
        logger.error(f"Error saving predictions: {e}")
        return 1
    
    # Statistics
    changed = sum(1 for i, pred in enumerate(predictions) if pred != corrected_predictions[i])
    logger.info(f"\nStatistics:")
    logger.info(f"  Total predictions: {len(predictions)}")
    logger.info(f"  Predictions changed: {changed} ({changed/len(predictions)*100:.1f}%)")
    logger.info(f"  Predictions unchanged: {len(predictions)-changed} ({(len(predictions)-changed)/len(predictions)*100:.1f}%)")
    
    logger.info("\n" + "="*60)
    logger.info("Correction complete!")
    logger.info("Next: Run evaluation script to measure accuracy improvement")
    logger.info("="*60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
