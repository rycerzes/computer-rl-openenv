import docker


class DockerProvider:
    def __init__(self, image_name: str = "computer-rl-env:latest"):
        self.image_name = image_name
        self.client = docker.from_env()
        self.container = None

    def start(self, port: int = 8001):
        self.container = self.client.containers.run(
            self.image_name,
            detach=True,
            ports={"8000/tcp": port},
            environment={"DISPLAY": ":99"},
        )
        return f"ws://localhost:{port}/ws"

    def stop(self):
        if self.container:
            self.container.stop()
            self.container.remove()

    def execute(self, cmd: str) -> str:
        if self.container:
            result = self.container.exec_run(cmd)
            return result.output.decode("utf-8")
        return ""

    def get_display(self) -> str:
        return ":99"
