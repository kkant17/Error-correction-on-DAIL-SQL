"""
Data structures for rules and rule triplets
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import json


@dataclass
class Rule:
    """
    Represents a SQL error correction rule.

    Attributes:
        pattern: Regular expression pattern matching error signatures
        correction: Description of transformation to fix the error
        error_type: Classification of the error type
        rule_id: Unique identifier for the rule
    """
    pattern: str
    correction: str
    error_type: str
    rule_id: Optional[str] = None

    def __post_init__(self):
        """Generate rule ID if not provided."""
        if self.rule_id is None:
            # Generate ID from pattern hash and timestamp
            import hashlib
            pattern_hash = hashlib.md5(self.pattern.encode()).hexdigest()[:8]
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            self.rule_id = f"rule_{pattern_hash}_{timestamp}"

    def to_dict(self) -> Dict:
        """Convert rule to dictionary."""
        return {
            'rule_id': self.rule_id,
            'pattern': self.pattern,
            'correction': self.correction,
            'error_type': self.error_type
        }

    def to_json(self) -> str:
        """Convert rule to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Rule':
        """Create rule from dictionary."""
        return cls(
            pattern=data['pattern'],
            correction=data['correction'],
            error_type=data['error_type'],
            rule_id=data.get('rule_id')
        )

    @classmethod
    def from_json(cls, json_str: str) -> 'Rule':
        """Create rule from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass
class RuleTriplet:
    """
    Represents a triplet of <query, explanation, rules>.

    Attributes:
        incorrect_query: The incorrect SQL query
        correct_query: The correct SQL query
        explanation: LLM-generated explanation of the error
        rules: List of correction rules (can be multiple rules for one query)
        db_id: Database identifier
        question: Natural language question
        triplet_id: Unique identifier
    """
    incorrect_query: str
    correct_query: str
    explanation: str
    rules: List[Rule]
    db_id: str = ""
    question: str = ""
    triplet_id: Optional[str] = None

    def __post_init__(self):
        """Generate triplet ID if not provided."""
        if self.triplet_id is None:
            import hashlib
            # Generate ID from incorrect query hash
            query_hash = hashlib.md5(self.incorrect_query.encode()).hexdigest()[:8]
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            self.triplet_id = f"triplet_{query_hash}_{timestamp}"

    def add_rule(self, rule: Rule):
        """Add a rule to this triplet."""
        self.rules.append(rule)

    def to_dict(self) -> Dict:
        """Convert triplet to dictionary."""
        return {
            'triplet_id': self.triplet_id,
            'incorrect_query': self.incorrect_query,
            'correct_query': self.correct_query,
            'explanation': self.explanation,
            'rules': [rule.to_dict() for rule in self.rules],
            'db_id': self.db_id,
            'question': self.question
        }

    def to_json(self) -> str:
        """Convert triplet to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict) -> 'RuleTriplet':
        """Create triplet from dictionary."""
        return cls(
            incorrect_query=data['incorrect_query'],
            correct_query=data['correct_query'],
            explanation=data['explanation'],
            rules=[Rule.from_dict(r) for r in data['rules']],
            db_id=data.get('db_id', ''),
            question=data.get('question', ''),
            triplet_id=data.get('triplet_id')
        )

    @classmethod
    def from_json(cls, json_str: str) -> 'RuleTriplet':
        """Create triplet from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass
class RuleCluster:
    """
    Represents a cluster of similar rules.

    Attributes:
        rules: List of rules in the cluster
        representative_triplet: Representative triplet for the cluster
        combined_rule: Combined rule from clustering
        cluster_id: Unique identifier
    """
    rules: List[Rule] = field(default_factory=list)
    representative_triplet: Optional[RuleTriplet] = None
    combined_rule: Optional[Rule] = None
    cluster_id: Optional[str] = None

    def __post_init__(self):
        """Generate cluster ID if not provided."""
        if self.cluster_id is None:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            self.cluster_id = f"cluster_{timestamp}_{len(self.rules)}"

    def add_rule(self, rule: Rule):
        """Add a rule to the cluster."""
        self.rules.append(rule)

    def size(self) -> int:
        """Get number of rules in cluster."""
        return len(self.rules)

    def to_dict(self) -> Dict:
        """Convert cluster to dictionary."""
        return {
            'cluster_id': self.cluster_id,
            'rules': [rule.to_dict() for rule in self.rules],
            'representative_triplet': self.representative_triplet.to_dict() if self.representative_triplet else None,
            'combined_rule': self.combined_rule.to_dict() if self.combined_rule else None,
            'size': self.size()
        }

    def to_json(self) -> str:
        """Convert cluster to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
