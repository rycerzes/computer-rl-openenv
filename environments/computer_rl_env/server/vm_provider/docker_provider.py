import logging
import os
import socket
import time

import docker
import requests
from docker.errors import APIError, NotFound

logger = logging.getLogger(__name__)


class DockerProvider:
    def __init__(
        self, image_name: str = "computer-rl-env:latest", container_name: str | None = None
    ):
        self.image_name = image_name
        self.container_name = container_name
        try:
            self.client = docker.from_env()
            self.client.ping()  # Verify connection
        except (docker.errors.DockerException, PermissionError):
            # Fallback for Podman on Linux (common on Fedora/RHEL)
            # Podman often uses a rootless socket in XDG_RUNTIME_DIR
            uid = os.getuid()
            podman_sock = (
                os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{uid}") + "/podman/podman.sock"
            )
            if os.path.exists(podman_sock):
                logger.info(f"Default docker socket failed, using Podman socket at {podman_sock}")
                self.client = docker.DockerClient(base_url=f"unix://{podman_sock}")
            else:
                raise

        self.container = None
        self.port = None
        self.cdp_port = None  # Chrome DevTools Protocol port

    def _get_free_port(self) -> int:
        """Find a free port on localhost."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def start(self, port: int | None = None, cdp_port: int | None = None) -> str:
        """Start container and return base URL (http://localhost:port).

        Args:
            port: Port for the environment server (8000 inside container)
            cdp_port: Port for Chrome DevTools Protocol (1337 inside container)
        """
        if self.container:
            logger.warning("Container already running, stopping it first")
            self.stop()

        self.port = port or self._get_free_port()
        self.cdp_port = cdp_port or self._get_free_port()

        try:
            logger.info(
                f"Starting container from image {self.image_name} on port {self.port}, CDP port {self.cdp_port}"
            )
            self.container = self.client.containers.run(
                self.image_name,
                name=self.container_name,  # Pass name if provided
                detach=True,
                ports={
                    "8000/tcp": self.port,
                    "1337/tcp": self.cdp_port,  # Chrome DevTools Protocol
                },
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
                self.cdp_port = None

    def revert_to_snapshot(self, port: int | None = None) -> str:
        """Reset by stopping and starting fresh container (OSWorld style).

        Returns:
            Base URL of the newly started container.
        """
        logger.info("Reverting to snapshot (restarting container)")
        saved_port = port or self.port
        saved_cdp_port = self.cdp_port
        self.stop()
        return self.start(port=saved_port, cdp_port=saved_cdp_port)

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

    def execute(
        self,
        cmd: str,
        shell: bool = False,
        background: bool = False,
        timeout: int | None = None,
    ) -> str:
        if self.container:
            try:
                if shell:
                    cmd = ["/bin/bash", "-c", cmd]

                result = self.container.exec_run(cmd, detach=background)

                if background:
                    return "Background process started"

                return result.output.decode("utf-8")
            except Exception as e:
                logger.error(f"Command execution failed: {e}")
                return ""
        logger.warning("No container running to execute command")
        return ""

    def get_display(self) -> str:
        return ":99"
