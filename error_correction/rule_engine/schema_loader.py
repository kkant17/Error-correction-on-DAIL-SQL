"""
Database Schema Loader for LLM Context

Loads database schema from Spider tables.json or SQLite databases
and formats it for inclusion in LLM prompts.
"""
import json
import os
import sqlite3
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


def load_schema_from_tables_json(db_id: str, tables_json_path: str = "dataset/spider/tables.json") -> Optional[Dict]:
    """
    Load database schema from Spider tables.json file.
    
    Args:
        db_id: Database identifier (e.g., "concert_singer")
        tables_json_path: Path to tables.json file
        
    Returns:
        Dictionary with schema information or None if not found
    """
    if not os.path.exists(tables_json_path):
        logger.debug(f"tables.json not found at {tables_json_path}")
        return None
    
    try:
        with open(tables_json_path, 'r', encoding='utf-8') as f:
            tables_data = json.load(f)
        
        # Find schema for this db_id
        for entry in tables_data:
            if entry.get('db_id') == db_id:
                logger.debug(f"Found schema for db_id: {db_id}")
                return entry
        
        logger.debug(f"Schema not found for db_id: {db_id}")
        return None
    except Exception as e:
        logger.warning(f"Error loading schema from tables.json for {db_id}: {e}")
        return None


def format_schema_for_llm(schema: Dict) -> str:
    """
    Format database schema in a readable format for LLM.
    
    Args:
        schema: Schema dictionary from tables.json
        
    Returns:
        Formatted schema string
    """
    if not schema:
        return ""
    
    lines = []
    lines.append("Database Schema:")
    
    table_names = schema.get('table_names', [])
    column_names = schema.get('column_names', [])
    column_names_original = schema.get('column_names_original', [])
    column_types = schema.get('column_types', [])
    primary_keys = schema.get('primary_keys', [])
    foreign_keys = schema.get('foreign_keys', [])
    
    # Build table structure
    current_table_idx = -1
    for i, (table_idx, col_name) in enumerate(column_names):
        if table_idx == -1:  # Skip "*" column
            continue
        
        # New table
        if table_idx != current_table_idx:
            if current_table_idx >= 0:
                lines.append("")  # Blank line between tables
            table_name = table_names[table_idx]
            lines.append(f"Table: {table_name}")
            current_table_idx = table_idx
        
        # Add column
        col_name_orig = column_names_original[i][1] if i < len(column_names_original) else col_name
        col_type = column_types[i] if i < len(column_types) else "text"
        
        # Mark primary key
        pk_marker = " (PRIMARY KEY)" if i in primary_keys else ""
        lines.append(f"  - {col_name_orig} ({col_type}){pk_marker}")
    
    # Add foreign key relationships
    if foreign_keys:
        lines.append("")
        lines.append("Foreign Key Relationships:")
        for fk in foreign_keys:
            if len(fk) >= 2:
                col_idx, ref_col_idx = fk[0], fk[1]
                if col_idx < len(column_names) and ref_col_idx < len(column_names):
                    col_table_idx = column_names[col_idx][0]
                    ref_table_idx = column_names[ref_col_idx][0]
                    if col_table_idx >= 0 and ref_table_idx >= 0:
                        col_table = table_names[col_table_idx]
                        ref_table = table_names[ref_table_idx]
                        col_name = column_names[col_idx][1]
                        ref_col_name = column_names[ref_col_idx][1]
                        lines.append(f"  - {col_table}.{col_name} -> {ref_table}.{ref_col_name}")
    
    return "\n".join(lines)


def load_schema_from_sqlite(db_path: str) -> str:
    """
    Load schema from SQLite database file and format for LLM.
    
    Args:
        db_path: Path to SQLite database file
        
    Returns:
        Formatted schema string
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        lines = []
        lines.append("Database Schema:")
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = cursor.fetchall()
        
        for (table_name,) in tables:
            lines.append(f"\nTable: {table_name}")
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            for col in columns:
                col_id, col_name, col_type, not_null, default_val, pk = col
                pk_marker = " (PRIMARY KEY)" if pk else ""
                not_null_marker = " (NOT NULL)" if not_null else ""
                lines.append(f"  - {col_name} ({col_type}){pk_marker}{not_null_marker}")
        
        conn.close()
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Error loading schema from SQLite {db_path}: {e}")
        return ""


def find_database_path_by_id(db_id: str) -> Optional[str]:
    """
    Find SQLite database file path by db_id.
    
    Args:
        db_id: Database identifier
        
    Returns:
        Path to database file or None if not found
    """
    possible_db_dirs = [
        "dataset/spider/database",
        "dataset/spider/test_database",
        "dataset/spider",
        "dataset"
    ]
    
    for db_dir in possible_db_dirs:
        if not os.path.exists(db_dir):
            continue
        
        # Look for directory matching db_id
        db_path = os.path.join(db_dir, db_id, f"{db_id}.sqlite")
        if os.path.exists(db_path):
            return db_path
        
        # Also check if db_id.sqlite exists directly
        db_path = os.path.join(db_dir, f"{db_id}.sqlite")
        if os.path.exists(db_path):
            return db_path
    
    return None


def get_database_schema(db_id: str, tables_json_path: str = "dataset/spider/tables.json") -> str:
    """
    Get database schema for LLM context.
    Priority: tables.json > SQLite > None
    
    Args:
        db_id: Database identifier
        tables_json_path: Path to Spider tables.json
        
    Returns:
        Formatted schema string or empty string if not available
    """
    # Skip synthetic IDs (e.g., eval_q6)
    if db_id.startswith("eval_q") or not db_id:
        logger.debug(f"Skipping schema for synthetic db_id: {db_id}")
        return ""
    
    # Option 1: Try tables.json (best - includes FKs, PKs, types)
    schema_dict = load_schema_from_tables_json(db_id, tables_json_path)
    if schema_dict:
        formatted = format_schema_for_llm(schema_dict)
        if formatted:
            logger.debug(f"Loaded schema from tables.json for {db_id}")
            return formatted
    
    # Option 2: Fallback to SQLite if database file exists
    db_path = find_database_path_by_id(db_id)
    if db_path and os.path.exists(db_path):
        formatted = load_schema_from_sqlite(db_path)
        if formatted:
            logger.debug(f"Loaded schema from SQLite for {db_id}")
            return formatted
    
    logger.debug(f"No schema available for db_id: {db_id}")
    return ""

