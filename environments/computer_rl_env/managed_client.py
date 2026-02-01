from __future__ import annotations

import logging
from typing import Any

from openenv.core.client_types import StepResult

from .client import ComputerEnvClient
from .models import ComputerAction, ComputerObservation
from .server.vm_provider.docker_provider import DockerProvider

logger = logging.getLogger(__name__)


class ManagedComputerEnvClient:
    """Client that manages Docker container lifecycle for clean resets.
    
    This client wraps ComputerEnvClient and handles:
    -  Starting a Docker container on initialization
    -  connecting the client to the container
    -  Destroying/recreating the container on reset (if used)
    -  cleaning up on exit
    """
    
    def __init__(self, image_name: str = "computer-rl-env:latest"):
        self.provider = DockerProvider(image_name)
        self._client: ComputerEnvClient | None = None
        self._is_env_used = False
        self._connected = False
        
    def connect(self):
        """Start container and connect client."""
        if self._connected:
            return

        base_url = self.provider.start()
        self._client = ComputerEnvClient(base_url=base_url)
        # Note: ComputerEnvClient typically doesn't need explicit connect() 
        # unless it uses persistent websockets immediately
        self._connected = True
        logger.info(f"Connected to managed env at {base_url}")

    def reset(self, **kwargs) -> StepResult[ComputerObservation]:
        """Reset environment, restarting container if needed."""
        if not self._connected:
            self.connect()
            
        if self._is_env_used:
            logger.info("Environment was used, restarting container...")
            self.provider.revert_to_snapshot()  # Stops container
            self._connected = False
            self.connect()             # Starts new container & client
            self._is_env_used = False
        
        # Now call server's reset (which just resets counters/tasks)
        result = self._client.reset(**kwargs)
        return result
    
    def step(self, action: ComputerAction) -> StepResult[ComputerObservation]:
        """Execute action, marks env as used."""
        if not self._connected:
            raise RuntimeError("Client not connected")
            
        self._is_env_used = True
        return self._client.step(action)
        
    def close(self):
        """Clean up container."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self.provider.stop()
        self._connected = False
        
    def __enter__(self):
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
