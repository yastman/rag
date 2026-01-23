import sys
from unittest.mock import MagicMock, patch

import pytest


***REMOVED*** Mock mlflow to prevent import-time hangs/warnings
***REMOVED*** This must happen BEFORE importing src.governance.model_registry
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
    ***REMOVED*** Setup
    run_id = "test-run-id"
    config_version = "1.0.0"
    metrics = {"faithfulness": 0.9}

    mock_version = MagicMock()
    mock_version.version = "1"
    mock_mlflow.register_model.return_value = mock_version

    ***REMOVED*** Execute
    version = registry.register_config(run_id, config_version, metrics)

    ***REMOVED*** Assert
    assert version == "1"
    mock_mlflow.register_model.assert_called_once()
    mock_mlflow_client.update_model_version.assert_called_once()

    ***REMOVED*** Check that description contains metrics
    call_args = mock_mlflow_client.update_model_version.call_args
    assert "Faithfulness: 0.9" in call_args.kwargs["description"]


def test_promote_to_staging(registry, mock_mlflow_client):
    ***REMOVED*** Execute
    registry.promote_to_staging("1")

    ***REMOVED*** Assert
    mock_mlflow_client.transition_model_version_stage.assert_called_with(
        name="contextual-rag-pipeline", version="1", stage="Staging"
    )
    mock_mlflow_client.set_registered_model_alias.assert_called_with(
        name="contextual-rag-pipeline", alias="challenger", version="1"
    )


def test_promote_to_production_with_archive(registry, mock_mlflow_client):
    ***REMOVED*** Setup: Mock existing production version
    mock_current_prod = MagicMock()
    mock_current_prod.version = "1"
    mock_mlflow_client.get_model_version_by_alias.return_value = mock_current_prod

    ***REMOVED*** Execute
    registry.promote_to_production("2")

    ***REMOVED*** Assert
    ***REMOVED*** 1. Check archiving of old version
    mock_mlflow_client.transition_model_version_stage.assert_any_call(
        name="contextual-rag-pipeline", version="1", stage="Archived"
    )
    ***REMOVED*** 2. Check promotion of new version
    mock_mlflow_client.transition_model_version_stage.assert_any_call(
        name="contextual-rag-pipeline", version="2", stage="Production"
    )
    ***REMOVED*** 3. Check alias update
    mock_mlflow_client.set_registered_model_alias.assert_called_with(
        name="contextual-rag-pipeline", alias="champion", version="2"
    )


def test_promote_to_production_first_time(registry, mock_mlflow_client):
    ***REMOVED*** Setup: No existing production version (raises exception)
    mock_mlflow_client.get_model_version_by_alias.side_effect = Exception("Not found")

    ***REMOVED*** Execute
    registry.promote_to_production("1")

    ***REMOVED*** Assert
    ***REMOVED*** Should try to get alias but fail gracefully, then promote new one
    mock_mlflow_client.transition_model_version_stage.assert_called_with(
        name="contextual-rag-pipeline", version="1", stage="Production"
    )


def test_rollback_production(registry, mock_mlflow_client):
    ***REMOVED*** Execute
    registry.rollback_production("1")

    ***REMOVED*** Assert
    ***REMOVED*** Should call promote logic but without archiving (since we are rolling back)
    ***REMOVED*** Note: promote_to_production implementation calls get_model_version_by_alias inside
    ***REMOVED*** but based on logic, rollback calls promote with archive_previous=False

    mock_mlflow_client.transition_model_version_stage.assert_called_with(
        name="contextual-rag-pipeline", version="1", stage="Production"
    )


def test_get_production_config(registry, mock_mlflow_client, mock_mlflow):
    ***REMOVED*** Setup
    mock_prod_version = MagicMock()
    mock_prod_version.version = "1"
    mock_prod_version.tags = {"config_version": "1.0.0"}
    mock_mlflow_client.get_model_version_by_alias.return_value = mock_prod_version

    mock_mlflow.artifacts.load_dict.return_value = {"chunk_size": 100}

    ***REMOVED*** Execute
    config = registry.get_production_config()

    ***REMOVED*** Assert
    assert config["version"] == "1"
    assert config["config_version"] == "1.0.0"
    assert config["config"]["chunk_size"] == 100
