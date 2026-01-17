import random
import time
from typing import List, Dict, Tuple, Any

class RandomAgent:
    """
    Random action baseline agent.
    Dumb agent that generates random actions to test the environment.
    """

    def __init__(self, action_space: Dict[str, Any] = None):
        """
        Initialize RandomAgent.
        
        Args:
            action_space: Optional dictionary definition of allowed actions.
                          If None, uses default ranges.
        """
        self.action_space = action_space or {}
        # Default screen size for random coordinates if not provided
        self.screen_width = 1920 
        self.screen_height = 1080

    def predict(self, instruction: str, observation: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Generate random actions based on the observation.
        
        Args:
            instruction: The task instruction string.
            observation: The current observation dictionary.
            
        Returns:
            Tuple of (response_text, list_of_actions).
        """
        # Randomly choose an action type
        action_types = ["key", "type", "mouse_move", "left_click", "right_click", "double_click"]
        action_type = random.choice(action_types)
        
        actions = []
        
        if action_type == "key":
            # Random common keys
            keys = ["enter", "space", "backspace", "tab", "escape", "up", "down", "left", "right"]
            key = random.choice(keys)
            actions.append({"action_type": "key", "key": key})
            
        elif action_type == "type":
            # Random short string
            chars = "abcdefghijklmnopqrstuvwxyz "
            text = "".join(random.choice(chars) for _ in range(random.randint(1, 10)))
            actions.append({"action_type": "type", "text": text})
            
        elif action_type in ["mouse_move", "left_click", "right_click", "double_click"]:
            # Random coordinates
            x = random.randint(0, 1000) # using 0-1000 normalized range as per some env conventions
            y = random.randint(0, 1000)
            
            if action_type == "mouse_move":
                 actions.append({"action_type": "mouse_move", "coordinate": [x, y]})
            elif action_type == "left_click":
                 actions.append({"action_type": "left_click", "coordinate": [x, y]})
            elif action_type == "right_click":
                 actions.append({"action_type": "right_click", "coordinate": [x, y]})
            elif action_type == "double_click":
                 actions.append({"action_type": "double_click", "coordinate": [x, y]})
        
        # Add a wait action occasionally
        if random.random() < 0.1:
            actions.append({"action_type": "wait", "duration": 0.5})

        return "I am acting randomly.", actions

    def reset(self, logger=None):
        """Reset agent state."""
        pass
