import os
import json
import yaml
from typing import List, Optional, Dict, Any
from pathlib import Path

from .base import Task

class TaskLoader:
    """
    Load tasks from YAML/JSON files.
    """

    def load_file(self, filepath: str) -> Task:
        """
        Load single task from YAML or JSON file.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Task file not found: {filepath}")

        with open(path, "r", encoding="utf-8") as f:
            if path.suffix in [".yaml", ".yml"]:
                data = yaml.safe_load(f)
            elif path.suffix == ".json":
                data = json.load(f)
            else:
                raise ValueError(f"Unsupported file extension: {path.suffix}")

        return Task(**data)

    def load_directory(self, dirpath: str) -> List[Task]:
        """
        Load all tasks from a directory (recursive).
        """
        path = Path(dirpath)
        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {dirpath}")

        tasks = []
        for file_path in path.glob("**/*"):
            if file_path.suffix in [".yaml", ".yml", ".json"]:
                try:
                    task = self.load_file(str(file_path))
                    tasks.append(task)
                except Exception as e:
                    print(f"Error loading task from {file_path}: {e}")
        
        return tasks

    def load_catalog(self, catalog_path: str = "tasks/tasks.yaml") -> Dict[str, Any]:
        """
        Load task registry from master catalog.
        """
        # Placeholder for catalog implementation
        # In the future, this will load a mapping of task IDs to files
        return {}

    def filter_tasks(self, 
                    tasks: List[Task],
                    categories: Optional[List[str]] = None,
                    difficulty: Optional[str] = None) -> List[Task]:
        """
        Filter tasks by metadata.
        """
        filtered = tasks
        
        if categories:
            filtered = [t for t in filtered if t.category in categories]
        
        if difficulty:
            filtered = [t for t in filtered if t.difficulty == difficulty]
            
        return filtered
