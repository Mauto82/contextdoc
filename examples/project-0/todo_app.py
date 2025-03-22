#!/usr/bin/env python3
"""
Simple Todo List Application
"""
import sys
from models.todo_item import TodoItem
from services.todo_service import TodoService
from services.storage_service import StorageService

class TodoApp:
    def __init__(self, storage_path="todos.json"):
        self.storage_service = StorageService(storage_path)
        self.todo_service = TodoService(self.storage_service)
        
    def run(self):
        """Main application loop"""
        print("Todo List Manager")
        print("-----------------")
        
        while True:
            self._display_todos()
            command = input("\nCommand (help for commands): ").strip().lower()
            
            if command == "exit":
                print("Goodbye!")
                sys.exit(0)
            elif command == "help":
                self._display_help()
            elif command == "add":
                self._add_todo()
            elif command.startswith("complete "):
                self._complete_todo(command[9:])
            elif command.startswith("delete "):
                self._delete_todo(command[7:])
            elif command.startswith("update "):
                self._update_todo(command[7:])
            elif command == "filter active":
                self._display_todos(status="active")
            elif command == "filter completed":
                self._display_todos(status="completed")
            elif command == "filter all":
                self._display_todos()
            else:
                print("Unknown command. Type 'help' for available commands.")
    
    def _display_todos(self, status=None):
        """Display todo items"""
        todos = self.todo_service.get_todos(status=status)
        
        if not todos:
            print("\nNo todos found!")
            return
            
        print("\nID | Status    | Title")
        print("-----------------------")
        for todo in todos:
            status_str = "✓ Complete" if todo.is_completed else "○ Active  "
            print(f"{todo.id} | {status_str} | {todo.title}")
    
    def _display_help(self):
        """Display available commands"""
        print("\nAvailable commands:")
        print("  add              - Add a new todo")
        print("  complete <id>    - Mark a todo as complete")
        print("  delete <id>      - Delete a todo")
        print("  update <id>      - Update a todo's title")
        print("  filter active    - Show only active todos")
        print("  filter completed - Show only completed todos")
        print("  filter all       - Show all todos")
        print("  help             - Display this help")
        print("  exit             - Exit the application")
    
    def _add_todo(self):
        """Add a new todo item"""
        title = input("Title: ").strip()
        if not title:
            print("Title cannot be empty.")
            return
            
        try:
            todo = self.todo_service.create_todo(title)
            print(f"Todo '{todo.title}' added with ID {todo.id}")
        except ValueError as e:
            print(f"Error: {e}")
    
    def _complete_todo(self, id_str):
        """Mark a todo as complete"""
        try:
            id = int(id_str.strip())
            self.todo_service.complete_todo(id)
            print(f"Todo {id} marked as complete")
        except ValueError:
            print("Invalid ID format")
        except KeyError:
            print(f"No todo found with ID {id}")
    
    def _delete_todo(self, id_str):
        """Delete a todo item"""
        try:
            id = int(id_str.strip())
            self.todo_service.delete_todo(id)
            print(f"Todo {id} deleted")
        except ValueError:
            print("Invalid ID format")
        except KeyError:
            print(f"No todo found with ID {id}")
    
    def _update_todo(self, id_str):
        """Update a todo item's title"""
        try:
            id = int(id_str.strip())
            todo = self.todo_service.get_todo(id)
            print(f"Current title: {todo.title}")
            new_title = input("New title: ").strip()
            
            if not new_title:
                print("Title cannot be empty.")
                return
                
            self.todo_service.update_todo(id, new_title)
            print(f"Todo {id} updated")
        except ValueError:
            print("Invalid ID format")
        except KeyError:
            print(f"No todo found with ID {id}")

if __name__ == "__main__":
    app = TodoApp()
    app.run()
