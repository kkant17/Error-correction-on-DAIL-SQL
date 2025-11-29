"""
Analyze and validate transformed SQL queries.
Compare transformed queries with gold queries to measure quality.
"""
import json
import re
from difflib import SequenceMatcher
from typing import List, Dict, Tuple

def normalize_sql(query: str) -> str:
    """
    Normalize SQL query for comparison (lowercase, remove extra spaces, etc).
    """
    if not query or not isinstance(query, str):
        return ""
    
    # Remove leading/trailing whitespace
    query = query.strip()
    
    # Lowercase
    query = query.lower()
    
    # Remove extra whitespace
    query = re.sub(r'\s+', ' ', query)
    
    # Remove trailing semicolon
    query = query.rstrip(';').strip()
    
    return query

def calculate_similarity(str1: str, str2: str) -> float:
    """
    Calculate string similarity using SequenceMatcher (0-1 scale).
    """
    if not str1 or not str2:
        return 0.0
    
    str1_norm = normalize_sql(str1)
    str2_norm = normalize_sql(str2)
    
    if str1_norm == str2_norm:
        return 1.0
    
    matcher = SequenceMatcher(None, str1_norm, str2_norm)
    return matcher.ratio()

def analyze_transformations(transformations_file: str) -> None:
    """
    Analyze transformations and compare with gold queries.
    """
    print("Loading transformations...")
    with open(transformations_file, 'r') as f:
        transformations = json.load(f)
    
    print(f"Total transformations: {len(transformations)}")
    print("=" * 100)
    
    # Statistics
    total = len(transformations)
    successful = sum(1 for t in transformations if t.get('success', False))
    failed = total - successful
    
    exact_matches = 0  # Normalized exact match with gold
    high_similarity = 0  # > 0.8 similarity
    medium_similarity = 0  # 0.5-0.8 similarity
    low_similarity = 0  # < 0.5 similarity
    
    similarities = []
    
    print("\nAnalyzing transformation quality...\n")
    
    for i, transform in enumerate(transformations):
        original = transform.get('original_query', '')
        transformed = transform.get('transformed_query', '')
        gold = transform.get('gold_query', '')
        success = transform.get('success', False)
        
        # Calculate similarity between transformed and gold
        similarity = calculate_similarity(transformed, gold)
        similarities.append(similarity)
        
        if similarity == 1.0:
            exact_matches += 1
        elif similarity >= 0.8:
            high_similarity += 1
        elif similarity >= 0.5:
            medium_similarity += 1
        else:
            low_similarity += 1
        
        # Print some examples for review
        if i < 10 or (i % 100 == 0 and i < 300):  # Show first 10 and every 100th
            print(f"\n--- Transformation #{i+1} ---")
            print(f"Success: {success}")
            print(f"Original: {original[:80]}..." if len(original) > 80 else f"Original: {original}")
            print(f"Transformed: {transformed[:80]}..." if len(transformed) > 80 else f"Transformed: {transformed}")
            print(f"Gold: {gold[:80]}..." if len(gold) > 80 else f"Gold: {gold}")
            print(f"Similarity with gold: {similarity:.2%}")
    
    # Summary statistics
    print("\n" + "=" * 100)
    print("TRANSFORMATION QUALITY ANALYSIS")
    print("=" * 100)
    print(f"\nTotal transformations: {total}")
    print(f"Successful (attempted): {successful}")
    print(f"Failed/Not attempted: {failed}")
    print(f"\nExact matches (normalized): {exact_matches} ({exact_matches/total*100:.1f}%)")
    print(f"High similarity (>0.8): {high_similarity} ({high_similarity/total*100:.1f}%)")
    print(f"Medium similarity (0.5-0.8): {medium_similarity} ({medium_similarity/total*100:.1f}%)")
    print(f"Low similarity (<0.5): {low_similarity} ({low_similarity/total*100:.1f}%)")
    
    if similarities:
        avg_similarity = sum(similarities) / len(similarities)
        max_similarity = max(similarities)
        min_similarity = min(similarities)
        print(f"\nAverage similarity: {avg_similarity:.2%}")
        print(f"Max similarity: {max_similarity:.2%}")
        print(f"Min similarity: {min_similarity:.2%}")
    
    # Save detailed results
    results = {
        'total': total,
        'successful': successful,
        'failed': failed,
        'exact_matches': exact_matches,
        'high_similarity_count': high_similarity,
        'medium_similarity_count': medium_similarity,
        'low_similarity_count': low_similarity,
        'average_similarity': sum(similarities) / len(similarities) if similarities else 0,
        'max_similarity': max(similarities) if similarities else 0,
        'min_similarity': min(similarities) if similarities else 0
    }
    
    with open('error_correction/rules/transformation_analysis.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Detailed analysis saved to error_correction/rules/transformation_analysis.json")

if __name__ == "__main__":
    analyze_transformations('error_correction/rules/transformations.json')
