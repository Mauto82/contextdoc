"""
Todo Item Model
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class TodoItem:
    """Represents a single todo item"""
    id: int
    title: str
    is_completed: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    def complete(self):
        """Mark the todo item as completed"""
        if not self.is_completed:
            self.is_completed = True
            self.completed_at = datetime.now()
    
    def reactivate(self):
        """Mark the todo item as active (not completed)"""
        if self.is_completed:
            self.is_completed = False
            self.completed_at = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "title": self.title,
            "is_completed": self.is_completed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TodoItem':
        """Create a TodoItem from a dictionary"""
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
        completed_at = datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
        
        return cls(
            id=data["id"],
            title=data["title"],
            is_completed=data["is_completed"],
            created_at=created_at,
            completed_at=completed_at
        )
