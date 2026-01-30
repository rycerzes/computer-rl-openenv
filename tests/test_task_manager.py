import pytest
from server.evaluators.base import TaskConfig, TaskManager


class TestTaskManager:
    def test_task_config_validation(self):
        config = TaskConfig(
            id="test_task_1",
            instruction="Open Calculator",
            setup=[{"type": "launch", "app": "gnome-calculator"}],
            evaluator={"type": "app_launched", "params": {"app_name": "gnome-calculator"}},
            max_steps=50,
            timeout=60,
        )
        assert config.id == "test_task_1"
        assert config.instruction == "Open Calculator"
        assert len(config.setup) == 1
        assert config.max_steps == 50

    def test_task_manager_init(self):
        manager = TaskManager()
        assert manager.active_task is None
        assert manager.observers == []

    def test_task_manager_setup_empty(self):
        manager = TaskManager()
        config = TaskConfig(
            id="test_task_2",
            instruction="Empty task",
            setup=[],
            evaluator={"type": "text_present", "params": {"text": "test"}},
        )
        result = manager.setup(config)
        assert result is True
        assert manager.active_task == config

    def test_task_manager_teardown(self):
        manager = TaskManager()
        config = TaskConfig(
            id="test_task_3",
            instruction="Teardown test",
            setup=[],
            evaluator={"type": "text_present", "params": {"text": "test"}},
        )
        manager.setup(config)
        manager.teardown()
        assert manager.active_task is None
        assert manager.observers == []

    def test_task_evaluate_failure(self):
        manager = TaskManager()
        config = TaskConfig(
            id="test_task_4",
            instruction="Nonexistent app",
            setup=[],
            evaluator={"type": "app_launched", "params": {"app_name": "nonexistent_app_12345"}},
            max_steps=10,
        )
        success, reward = manager.evaluate(config, elapsed_steps=5)
        assert success is False
        assert reward < 0
