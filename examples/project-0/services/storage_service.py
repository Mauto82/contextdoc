"""
Storage Service - Persistence Layer
"""
import json
import os
from typing import List
from models.todo_item import TodoItem

class StorageService:
    def __init__(self, file_path: str):
        self.file_path = file_path
    
    def load(self) -> List[TodoItem]:
        """Load todos from storage"""
        if not os.path.exists(self.file_path):
            return []
        
        try:
            with open(self.file_path, 'r') as f:
                data = json.load(f)
                return [TodoItem.from_dict(item) for item in data]
        except (json.JSONDecodeError, KeyError) as e:
            # Handle corrupted data file
            print(f"Error loading data: {e}")
            # Backup the corrupted file if it exists
            if os.path.exists(self.file_path):
                backup_path = f"{self.file_path}.bak"
                os.rename(self.file_path, backup_path)
                print(f"Corrupted data file backed up to {backup_path}")
            return []
    
    def save(self, todos: List[TodoItem]) -> None:
        """Save todos to storage"""
        data = [todo.to_dict() for todo in todos]
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.file_path) if os.path.dirname(self.file_path) else '.', exist_ok=True)
        
        # Write to a temporary file first to prevent data loss if the program crashes
        temp_path = f"{self.file_path}.tmp"
        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Rename the temporary file to the actual file
        os.replace(temp_path, self.file_path)
