#!/usr/bin/env python3
"""
Generate evaluation file in the same format as eval_codellama_dev.txt
but using error-corrected queries from the pipeline results.
"""

import json
import argparse
import os
from datetime import datetime
from collections import defaultdict

def load_pipeline_results(json_path: str) -> dict:
    """Load pipeline test results from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_difficulty(query_data: dict) -> str:
    """
    Determine query difficulty based on query characteristics.
    Uses same criteria as Spider evaluation.
    """
    # If difficulty is stored in metadata, use it
    if 'difficulty' in query_data:
        return query_data['difficulty']
    
    gold_sql = query_data.get('gold_sql', '').lower()
    
    # Count complexity indicators
    has_join = ' join ' in gold_sql
    has_subquery = 'select' in gold_sql[gold_sql.find('from'):] if 'from' in gold_sql else False
    has_group = ' group by ' in gold_sql
    has_order = ' order by ' in gold_sql
    has_having = ' having ' in gold_sql
    has_union = ' union ' in gold_sql or ' intersect ' in gold_sql or ' except ' in gold_sql
    has_nested = gold_sql.count('select') > 1
    
    complexity_score = sum([
        has_join * 1,
        has_subquery * 2,
        has_group * 1,
        has_order * 1,
        has_having * 1,
        has_union * 2,
        has_nested * 2
    ])
    
    if complexity_score == 0:
        return 'easy'
    elif complexity_score <= 2:
        return 'medium'
    elif complexity_score <= 4:
        return 'hard'
    else:
        return 'extra'

def generate_eval_file(results: dict, output_path: str):
    """Generate eval file in the format of eval_codellama_dev.txt."""
    
    queries = results.get('queries', [])
    summary = results.get('summary', {})
    
    # Statistics by difficulty
    stats = defaultdict(lambda: {
        'count': 0,
        'exact_match': 0,
        'execution_match': 0,
        'partial_select': [],
        'partial_where': [],
        'partial_group': [],
        'partial_order': []
    })
    
    lines = []
    
    for query_data in queries:
        # Get the transformed query (use original if transformation failed)
        steps = query_data.get('steps', {})
        transformed = steps.get('transformed_query', query_data.get('incorrect_query', ''))
        gold = query_data.get('gold_query', query_data.get('gold_sql', ''))
        
        # Determine difficulty using gold query
        query_for_difficulty = {'gold_sql': gold, **query_data}
        difficulty = get_difficulty(query_for_difficulty)
        
        # Add to output
        lines.append(f"{difficulty} pred: {transformed}")
        lines.append(f"{difficulty} gold: {gold}")
        lines.append("")
        
        # Update statistics
        stats[difficulty]['count'] += 1
        stats['all']['count'] += 1
        
        validation = steps.get('validation', {})
        if validation.get('passed', False):
            if validation.get('method') == 'exact_match':
                stats[difficulty]['exact_match'] += 1
                stats[difficulty]['execution_match'] += 1
                stats['all']['exact_match'] += 1
                stats['all']['execution_match'] += 1
            elif validation.get('method') == 'execution_match':
                stats[difficulty]['execution_match'] += 1
                stats['all']['execution_match'] += 1
        
        # Collect partial match scores
        partial = validation.get('partial_match', {})
        if partial:
            for component in ['select', 'where', 'group', 'order']:
                if component in partial:
                    f1 = partial[component].get('f1', 0)
                    stats[difficulty][f'partial_{component}'].append(f1)
                    stats['all'][f'partial_{component}'].append(f1)
    
    # Add summary statistics
    lines.append("")
    lines.append("=" * 80)
    lines.append(f"ERROR CORRECTION PIPELINE RESULTS")
    lines.append(f"Generated: {datetime.now().isoformat()}")
    lines.append(f"Source: {results.get('config', {}).get('model', 'unknown')}")
    lines.append("=" * 80)
    lines.append("")
    
    # Header row
    difficulties = ['easy', 'medium', 'hard', 'extra', 'all']
    header = f"{'':20}"
    for d in difficulties:
        header += f"{d:20}"
    lines.append(header)
    
    # Count row
    count_row = f"{'count':20}"
    for d in difficulties:
        count_row += f"{stats[d]['count']:<20}"
    lines.append(count_row)
    
    lines.append("")
    lines.append("=====================   EXECUTION ACCURACY     =====================")
    
    # Execution accuracy
    exec_row = f"{'execution':20}"
    for d in difficulties:
        count = stats[d]['count']
        exec_match = stats[d]['execution_match']
        acc = exec_match / count if count > 0 else 0
        exec_row += f"{acc:<20.3f}"
    lines.append(exec_row)
    
    lines.append("")
    lines.append("====================== EXACT MATCHING ACCURACY =====================")
    
    # Exact match accuracy
    exact_row = f"{'exact match':20}"
    for d in difficulties:
        count = stats[d]['count']
        exact_match = stats[d]['exact_match']
        acc = exact_match / count if count > 0 else 0
        exact_row += f"{acc:<20.3f}"
    lines.append(exact_row)
    
    lines.append("")
    lines.append("---------------------PARTIAL MATCHING F1 (avg)----------------------")
    
    # Partial match F1 scores (averaged)
    for component in ['select', 'where', 'group', 'order']:
        row = f"{component:20}"
        for d in difficulties:
            scores = stats[d][f'partial_{component}']
            avg = sum(scores) / len(scores) if scores else 0
            row += f"{avg:<20.3f}"
        lines.append(row)
    
    # Add pipeline-specific summary
    lines.append("")
    lines.append("=" * 80)
    lines.append("PIPELINE SUMMARY")
    lines.append("=" * 80)
    lines.append(f"Total queries processed: {summary.get('total', 0)}")
    lines.append(f"Explanations generated: {summary.get('explanations_generated', 0)}")
    lines.append(f"Solutions generated: {summary.get('solutions_generated', 0)}")
    lines.append(f"Rules generated: {summary.get('rules_generated', 0)}")
    lines.append(f"Rules applied (transformed): {summary.get('rules_applied', 0)}")
    lines.append(f"Exact matches: {summary.get('exact_matches', 0)}")
    lines.append(f"Execution matches: {summary.get('execution_matches', 0)}")
    lines.append(f"Validation passed: {summary.get('validation_passed', 0)}")
    lines.append(f"Success rate: {summary.get('success_rate', 0):.2f}%")
    lines.append("")
    
    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"Generated eval file: {output_path}")
    print(f"  Total queries: {stats['all']['count']}")
    print(f"  Execution accuracy: {stats['all']['execution_match'] / stats['all']['count'] * 100:.2f}%" if stats['all']['count'] > 0 else "  No queries")
    print(f"  Exact match accuracy: {stats['all']['exact_match'] / stats['all']['count'] * 100:.2f}%" if stats['all']['count'] > 0 else "  No queries")

def main():
    parser = argparse.ArgumentParser(description='Generate eval file from pipeline results')
    parser.add_argument('--input', '-i', type=str, 
                        default='results/pipeline_test_60_queries_20251129_005435.json',
                        help='Path to pipeline results JSON file')
    parser.add_argument('--output', '-o', type=str,
                        default=None,
                        help='Output path for eval file (default: auto-generated)')
    
    args = parser.parse_args()
    
    # Load results
    print(f"Loading results from: {args.input}")
    results = load_pipeline_results(args.input)
    
    # Auto-generate output filename if not provided
    if args.output is None:
        # Extract model name from results config
        model = results.get('config', {}).get('model', 'unknown')
        # Clean model name for filename (replace : with _)
        model_clean = model.replace(':', '_').replace('/', '_')
        args.output = f"results/eval_{model_clean}_error_correction.txt"
    
    # Generate eval file
    generate_eval_file(results, args.output)

if __name__ == '__main__':
    main()

