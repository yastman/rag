import sys
from unittest.mock import MagicMock, patch

import pytest


# Mock mlflow to prevent import-time hangs/warnings
# This must happen BEFORE importing src.governance.model_registry
mock_mlflow = MagicMock()
sys.modules["mlflow"] = mock_mlflow
sys.modules["mlflow.tracking"] = MagicMock()
sys.modules["mlflow.artifacts"] = MagicMock()

from src.governance.model_registry import RAGModelRegistry


@pytest.fixture
def mock_mlflow_client():
    with patch("src.governance.model_registry.MlflowClient") as mock_client_cls:
        client_instance = MagicMock()
        mock_client_cls.return_value = client_instance
        yield client_instance


@pytest.fixture
def mock_mlflow():
    with patch("src.governance.model_registry.mlflow") as mock_mlflow_module:
        yield mock_mlflow_module


@pytest.fixture
def registry(mock_mlflow_client):
    return RAGModelRegistry()


def test_register_config(registry, mock_mlflow, mock_mlflow_client):
    # Setup
    run_id = "test-run-id"
    config_version = "1.0.0"
    metrics = {"faithfulness": 0.9}

    mock_version = MagicMock()
    mock_version.version = "1"
    mock_mlflow.register_model.return_value = mock_version

    # Execute
    version = registry.register_config(run_id, config_version, metrics)

    # Assert
    assert version == "1"
    mock_mlflow.register_model.assert_called_once()
    mock_mlflow_client.update_model_version.assert_called_once()

    # Check that description contains metrics
    call_args = mock_mlflow_client.update_model_version.call_args
    assert "Faithfulness: 0.9" in call_args.kwargs["description"]


def test_promote_to_staging(registry, mock_mlflow_client):
    # Execute
    registry.promote_to_staging("1")

    # Assert
    mock_mlflow_client.transition_model_version_stage.assert_called_with(
        name="contextual-rag-pipeline", version="1", stage="Staging"
    )
    mock_mlflow_client.set_registered_model_alias.assert_called_with(
        name="contextual-rag-pipeline", alias="challenger", version="1"
    )


def test_promote_to_production_with_archive(registry, mock_mlflow_client):
    # Setup: Mock existing production version
    mock_current_prod = MagicMock()
    mock_current_prod.version = "1"
    mock_mlflow_client.get_model_version_by_alias.return_value = mock_current_prod

    # Execute
    registry.promote_to_production("2")

    # Assert
    # 1. Check archiving of old version
    mock_mlflow_client.transition_model_version_stage.assert_any_call(
        name="contextual-rag-pipeline", version="1", stage="Archived"
    )
    # 2. Check promotion of new version
    mock_mlflow_client.transition_model_version_stage.assert_any_call(
        name="contextual-rag-pipeline", version="2", stage="Production"
    )
    # 3. Check alias update
    mock_mlflow_client.set_registered_model_alias.assert_called_with(
        name="contextual-rag-pipeline", alias="champion", version="2"
    )


def test_promote_to_production_first_time(registry, mock_mlflow_client):
    # Setup: No existing production version (raises exception)
    mock_mlflow_client.get_model_version_by_alias.side_effect = Exception("Not found")

    # Execute
    registry.promote_to_production("1")

    # Assert
    # Should try to get alias but fail gracefully, then promote new one
    mock_mlflow_client.transition_model_version_stage.assert_called_with(
        name="contextual-rag-pipeline", version="1", stage="Production"
    )


def test_rollback_production(registry, mock_mlflow_client):
    # Execute
    registry.rollback_production("1")

    # Assert
    # Should call promote logic but without archiving (since we are rolling back)
    # Note: promote_to_production implementation calls get_model_version_by_alias inside
    # but based on logic, rollback calls promote with archive_previous=False

    mock_mlflow_client.transition_model_version_stage.assert_called_with(
        name="contextual-rag-pipeline", version="1", stage="Production"
    )


def test_get_production_config(registry, mock_mlflow_client, mock_mlflow):
    # Setup
    mock_prod_version = MagicMock()
    mock_prod_version.version = "1"
    mock_prod_version.tags = {"config_version": "1.0.0"}
    mock_mlflow_client.get_model_version_by_alias.return_value = mock_prod_version

    mock_mlflow.artifacts.load_dict.return_value = {"chunk_size": 100}

    # Execute
    config = registry.get_production_config()

    # Assert
    assert config["version"] == "1"
    assert config["config_version"] == "1.0.0"
    assert config["config"]["chunk_size"] == 100
