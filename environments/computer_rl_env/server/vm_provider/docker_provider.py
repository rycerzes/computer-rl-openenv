import logging
import socket
import time

import docker
import requests
from docker.errors import APIError, NotFound

logger = logging.getLogger(__name__)


class DockerProvider:
    def __init__(self, image_name: str = "computer-rl-env:latest"):
        self.image_name = image_name
        self.client = docker.from_env()
        self.container = None
        self.port = None

    def _get_free_port(self) -> int:
        """Find a free port on localhost."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def start(self, port: int | None = None) -> str:
        """Start container and return base URL (http://localhost:port)."""
        if self.container:
            logger.warning("Container already running, stopping it first")
            self.stop()

        self.port = port or self._get_free_port()

        try:
            logger.info(f"Starting container from image {self.image_name} on port {self.port}")
            self.container = self.client.containers.run(
                self.image_name,
                detach=True,
                ports={"8000/tcp": self.port},
                environment={"DISPLAY": ":99"},
                cap_add=["SYS_ADMIN"],  # Often needed for GUI automation
                shm_size="2g",  # Prevent browser crashes
            )

            # Wait for container to be ready
            base_url = f"http://localhost:{self.port}"
            self._wait_for_ready(base_url)
            return base_url

        except Exception as e:
            logger.error(f"Failed to start container: {e}")
            self.stop()
            raise

    def stop(self):
        """Stop and remove the container."""
        if self.container:
            try:
                logger.info(f"Stopping container {self.container.short_id}")
                self.container.stop(timeout=5)
                self.container.remove(force=True)
            except (NotFound, APIError) as e:
                logger.warning(f"Error stopping container: {e}")
            finally:
                self.container = None
                self.port = None

    def revert_to_snapshot(self):
        """Reset by stopping and starting fresh container (ComputerRL style)."""
        logger.info("Reverting to snapshot (restarting container)")
        self.stop()
        # Container will be started on next use/reset via start()
        # Ideally the caller calls start() immediately after if they need it running

    def _wait_for_ready(self, base_url: str, timeout: int = 60):
        """Wait for environment server to be healthy."""
        logger.info("Waiting for environment server to be ready...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{base_url}/health", timeout=2)
                if response.status_code == 200:
                    logger.info("Environment server is ready")
                    return
            except requests.RequestException:
                pass
            time.sleep(1)

        raise TimeoutError(f"Environment server failed to start within {timeout}s")

    def execute(self, cmd: str) -> str:
        if self.container:
            try:
                result = self.container.exec_run(cmd)
                return result.output.decode("utf-8")
            except Exception as e:
                logger.error(f"Command execution failed: {e}")
                return ""
        logger.warning("No container running to execute command")
        return ""

    def get_display(self) -> str:
        return ":99"
