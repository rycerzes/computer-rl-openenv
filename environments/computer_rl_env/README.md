# Computer RL Environment

A computer control RL environment for OpenEnv, implementing Gymnasium-style API for desktop GUI automation.

## Installation

```bash
# From project root
cd environments/computer_rl_env
uv sync
```

## Build Docker Image

```bash
docker build -f server/Dockerfile -t computer-rl-env:latest .
```

## Run Environment Locally

```bash
# Start the server
uv run server

# Or with Docker
docker run -p 8000:8000 computer-rl-env:latest
```

## Usage

```python
from computer_rl_env import ComputerEnvClient, ComputerAction

# Connect to running environment
client = ComputerEnvClient("http://localhost:8000")

# Reset environment
obs = client.reset()

# Take action
action = ComputerAction(action_type="click", x=500, y=500)
result = client.step(action)

# Close connection
client.close()
```