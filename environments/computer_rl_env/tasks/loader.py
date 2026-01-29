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
            if path.suffix == ".json":
                data = json.load(f)
            elif path.suffix in [".yaml", ".yml"]:
                # Keep legacy YAML support for now, but OSWorld uses JSON
                data = yaml.safe_load(f)
            else:
                raise ValueError(f"Unsupported file extension: {path.suffix}")

        # Handle simplified task definitions or migrate old ones if needed
        # For now, we assume strict adherence to the new Task model
        return Task(**data)

    def load_from_registry(self, registry_path: str) -> List[Task]:
        """
        Load tasks defined in a registry JSON file (OSWorld style).
        
        The registry file is a JSON dict mapping category names to lists of task IDs.
        Tasks are expected to be in an 'examples' subdirectory relative to the registry file.
        
        Args:
            registry_path: Path to the registry JSON file (e.g., test_small.json)
            
        Returns:
            List of loaded Task objects
        """
        registry_path = Path(registry_path)
        if not registry_path.exists():
            raise FileNotFoundError(f"Registry file not found: {registry_path}")
            
        base_dir = registry_path.parent / "examples"
        if not base_dir.exists():
             # Fallback: try relative to the loader itself or project root if needed
             # For now, strictly follow the structure seen in evaluation_examples
             pass

        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
            
        tasks = []
        for category, task_ids in registry.items():
            category_dir = base_dir / category
            if not category_dir.exists():
                print(f"Warning: Category directory not found: {category_dir}")
                continue
                
            for task_id in task_ids:
                task_file = category_dir / f"{task_id}.json"
                try:
                    task = self.load_file(str(task_file))
                    # Inject category if missing
                    if not task.category:
                        task.category = category
                    tasks.append(task)
                except Exception as e:
                    print(f"Error loading task {task_id} from {task_file}: {e}")
                    
        return tasks
