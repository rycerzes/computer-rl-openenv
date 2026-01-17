import re
import time
from typing import List, Dict, Tuple, Any, Optional

class RuleBasedAgent:
    """
    Rule-based baseline agent.
    Uses simple heuristics to act on the environment.
    """

    def __init__(self):
        """Initialize RuleBasedAgent."""
        pass

    def predict(self, instruction: str, observation: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Apply simple rules to select actions based on instruction and observation.
        
        Args:
            instruction: The task instruction string.
            observation: The current observation dictionary.
            
        Returns:
            Tuple of (response_text, list_of_actions).
        """
        # Parse accessibility tree from observation
        acc_tree = observation.get("accessibility_tree", "")
        screenshot = observation.get("screenshot", None) # Not used in simple rules yet
        
        actions = []
        response_text = "Analyzing screen..."

        # Rule 1: Search - if instruction contains "search" or "find", look for search bar
        if "search" in instruction.lower() or "find" in instruction.lower():
            target_ids = ["search", "input", "edit"]
            coords = self._find_element(acc_tree, target_ids)
            if coords:
                actions.append({"action_type": "left_click", "coordinate": coords})
                # Extract search term if possible (very naive)
                search_term = "test query"
                words = instruction.split()
                if "for" in words:
                    idx = words.index("for")
                    if idx + 1 < len(words):
                        search_term = " ".join(words[idx+1:])
                
                actions.append({"action_type": "type", "text": search_term})
                actions.append({"action_type": "key", "key": "enter"})
                response_text = f"Searching for '{search_term}'"
                return response_text, actions

        # Rule 2: Open/Launch - click on icons
        if "open" in instruction.lower() or "launch" in instruction.lower():
            # Try to find app name in instruction
            words = instruction.lower().split()
            app_name = None
            if "open" in words:
                idx = words.index("open")
                if idx + 1 < len(words):
                    app_name = words[idx+1]
            
            if app_name:
                coords = self._find_element(acc_tree, [app_name])
                if coords:
                     actions.append({"action_type": "double_click", "coordinate": coords})
                     response_text = f"Opening {app_name}"
                     return response_text, actions

        # Rule 3: Click generic buttons if mentioned
        target_name = None
        instruction_lower = instruction.lower()
        if "click" in instruction_lower:
             # Extract what to click "click [target]"
             match = re.search(r"click (?:on )?(?:the )?([\w\s]+)", instruction_lower)
             if match:
                 target_name = match.group(1).strip()
        
        if target_name:
            coords = self._find_element(acc_tree, [target_name])
            if coords:
                actions.append({"action_type": "left_click", "coordinate": coords})
                response_text = f"Clicking on {target_name}"
                return response_text, actions

        # Fallback: Random action if no rules trigger (or maybe just wait)
        response_text = "No rule matched, waiting."
        actions.append({"action_type": "wait", "duration": 1.0})
        
        return response_text, actions

    def _find_element(self, tree: str, keywords: List[str]) -> Optional[List[int]]:
        """
        Parses the accessibility tree (text format) to find coordinates of an element.
        This is a placeholder logic as the tree format depends on AccessibilityParser implementation.
        Assuming tree format: "Role: Name [x, y, w, h]" or similar.
        """
        lines = tree.split('\n')
        for line in lines:
            line_lower = line.lower()
            for kw in keywords:
                if kw.lower() in line_lower:
                    # Try to extract coordinates [x, y, w, h] or (x, y)
                    # Regex for [x, y, w, h]
                    match = re.search(r"\[(\d+), (\d+), (\d+), (\d+)\]", line)
                    if match:
                        x, y, w, h = map(int, match.groups())
                        return [x + w // 2, y + h // 2]
                    
                    # Regex for (x, y)
                    match = re.search(r"\((\d+), (\d+)\)", line)
                    if match:
                        x, y = map(int, match.groups())
                        return [x, y]
        return None

    def reset(self, logger=None):
        pass
