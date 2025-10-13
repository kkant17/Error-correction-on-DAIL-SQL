"""
Configuration Usage Example for Error Correction Pipeline

This script demonstrates different ways to load and use the configuration.
"""

import os
from error_correction import ErrorCorrectionConfig


def main():
    """Demonstrate different configuration loading methods"""
    
    print("=== Error Correction Configuration Examples ===\n")
    
    # Example 1: Default configuration
    print("1. Using default configuration:")
    config = ErrorCorrectionConfig()
    print(f"   LLM Model: {config.LLM_MODEL}")
    print(f"   A Percent Threshold: {config.A_PERCENT_THRESHOLD}")
    print(f"   X Sample Size: {config.X_SAMPLE_SIZE}")
    print(f"   Min Triplet Count: {config.MIN_TRIPLET_COUNT}")
    print(f"   Clustering Threshold: {config.CLUSTERING_THRESHOLD}")
    print(f"   Max Clustering Iterations: {config.MAX_CLUSTERING_ITERATIONS}")
    print(f"   Rule Validation Retries: {config.RULE_VALIDATION_RETRIES}")
    
    # Example 2: Load from environment variables
    print("\n2. Loading from environment variables:")
    # Set some environment variables for demonstration
    os.environ['LLM_MODEL'] = 'gpt-3.5-turbo'
    os.environ['A_PERCENT_THRESHOLD'] = '0.8'
    os.environ['X_SAMPLE_SIZE'] = '50'
    os.environ['MIN_TRIPLET_COUNT'] = '15'
    
    env_config = ErrorCorrectionConfig.from_env()
    print(f"   LLM Model: {env_config.LLM_MODEL}")
    print(f"   A Percent Threshold: {env_config.A_PERCENT_THRESHOLD}")
    print(f"   X Sample Size: {env_config.X_SAMPLE_SIZE}")
    print(f"   Min Triplet Count: {env_config.MIN_TRIPLET_COUNT}")
    
    # Example 3: Load from configuration file
    print("\n3. Loading from configuration file:")
    config_file = "error_correction/config_example.json"
    if os.path.exists(config_file):
        file_config = ErrorCorrectionConfig.from_file(config_file)
        print(f"   LLM Model: {file_config.LLM_MODEL}")
        print(f"   A Percent Threshold: {file_config.A_PERCENT_THRESHOLD}")
        print(f"   X Sample Size: {file_config.X_SAMPLE_SIZE}")
        print(f"   Min Triplet Count: {file_config.MIN_TRIPLET_COUNT}")
    else:
        print(f"   Config file not found: {config_file}")
    
    # Example 4: Update configuration
    print("\n4. Updating configuration:")
    config.update(
        LLM_MODEL="llama-3-70b",
        A_PERCENT_THRESHOLD=0.8,
        X_SAMPLE_SIZE=200,
        MIN_TRIPLET_COUNT=20
    )
    print(f"   Updated LLM Model: {config.LLM_MODEL}")
    print(f"   Updated A Percent Threshold: {config.A_PERCENT_THRESHOLD}")
    print(f"   Updated X Sample Size: {config.X_SAMPLE_SIZE}")
    print(f"   Updated Min Triplet Count: {config.MIN_TRIPLET_COUNT}")
    
    # Example 5: Save configuration to file
    print("\n5. Saving configuration to file:")
    if config.save_to_file("error_correction/my_config.json"):
        print("   Configuration saved successfully!")
    else:
        print("   Failed to save configuration")
    
    # Example 6: Get specific configuration sections
    print("\n6. Getting specific configuration sections:")
    
    llm_config = config.get_llm_config()
    print(f"   LLM Config: {llm_config}")
    
    clustering_config = config.get_clustering_config()
    print(f"   Clustering Config: {clustering_config}")
    
    rule_config = config.get_rule_config()
    print(f"   Rule Config: {rule_config}")
    
    # Example 7: Configuration validation
    print("\n7. Configuration validation:")
    try:
        # This should work fine
        valid_config = ErrorCorrectionConfig(
            A_PERCENT_THRESHOLD=0.5,
            CLUSTERING_THRESHOLD=0.6,
            X_SAMPLE_SIZE=50,
            MIN_TRIPLET_COUNT=5
        )
        print("   Valid configuration created successfully")
    except ValueError as e:
        print(f"   Configuration validation error: {e}")
    
    try:
        # This should fail validation
        invalid_config = ErrorCorrectionConfig(
            A_PERCENT_THRESHOLD=1.5,  # Invalid: > 1
            CLUSTERING_THRESHOLD=0.6,
            X_SAMPLE_SIZE=50,
            MIN_TRIPLET_COUNT=5
        )
        print("   Invalid configuration was accepted (unexpected)")
    except ValueError as e:
        print(f"   Configuration validation caught error: {e}")
    
    # Example 8: Configuration dictionary
    print("\n8. Configuration as dictionary:")
    config_dict = config.to_dict()
    print(f"   Total configuration parameters: {len(config_dict)}")
    print(f"   Key parameters:")
    for key in ['LLM_MODEL', 'A_PERCENT_THRESHOLD', 'X_SAMPLE_SIZE', 'MIN_TRIPLET_COUNT']:
        if key in config_dict:
            print(f"     {key}: {config_dict[key]}")
    
    print("\n=== Configuration examples completed! ===")


if __name__ == "__main__":
    main()
