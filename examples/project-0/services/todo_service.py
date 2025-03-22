"""
Todo Service - Business Logic Layer
"""
from typing import List, Optional
from models.todo_item import TodoItem
from services.storage_service import StorageService

class TodoService:
    def __init__(self, storage_service: StorageService):
        self.storage_service = storage_service
        self.todos = storage_service.load()
        self._next_id = self._calculate_next_id()
    
    def _calculate_next_id(self) -> int:
        """Calculate the next available ID"""
        if not self.todos:
            return 1
        return max(todo.id for todo in self.todos) + 1
    
    def get_todos(self, status: Optional[str] = None) -> List[TodoItem]:
        """
        Get todos, optionally filtered by status
        
        Args:
            status: Optional filter - 'active', 'completed', or None (all)
        """
        if status is None:
            return sorted(self.todos, key=lambda x: x.id)
        
        if status == "active":
            return sorted([todo for todo in self.todos if not todo.is_completed], 
                         key=lambda x: x.id)
        
        if status == "completed":
            return sorted([todo for todo in self.todos if todo.is_completed], 
                         key=lambda x: x.id)
        
        raise ValueError(f"Invalid status filter: {status}")
    
    def get_todo(self, id: int) -> TodoItem:
        """Get a specific todo by ID"""
        for todo in self.todos:
            if todo.id == id:
                return todo
        raise KeyError(f"No todo found with ID {id}")
    
    def create_todo(self, title: str) -> TodoItem:
        """Create a new todo item"""
        if not title:
            raise ValueError("Todo title cannot be empty")
            
        if len(title) > 100:
            raise ValueError("Todo title cannot exceed 100 characters")
        
        todo = TodoItem(
            id=self._next_id,
            title=title
        )
        
        self.todos.append(todo)
        self._next_id += 1
        self.storage_service.save(self.todos)
        
        return todo
    
    def update_todo(self, id: int, title: str) -> TodoItem:
        """Update an existing todo's title"""
        if not title:
            raise ValueError("Todo title cannot be empty")
            
        if len(title) > 100:
            raise ValueError("Todo title cannot exceed 100 characters")
        
        todo = self.get_todo(id)
        todo.title = title
        self.storage_service.save(self.todos)
        
        return todo
    
    def complete_todo(self, id: int) -> TodoItem:
        """Mark a todo as complete"""
        todo = self.get_todo(id)
        todo.complete()
        self.storage_service.save(self.todos)
        
        return todo
    
    def reactivate_todo(self, id: int) -> TodoItem:
        """Mark a completed todo as active"""
        todo = self.get_todo(id)
        todo.reactivate()
        self.storage_service.save(self.todos)
        
        return todo
    
    def delete_todo(self, id: int) -> None:
        """Delete a todo"""
        todo = self.get_todo(id)
        self.todos.remove(todo)
        self.storage_service.save(self.todos)
