from unittest.mock import MagicMock

import pytest


@pytest.fixture
def model_registry_deps(monkeypatch):
    import src.governance.model_registry as model_registry_module

    mock_client = MagicMock()
    mock_mlflow = MagicMock()
    monkeypatch.setattr(model_registry_module, "MlflowClient", lambda: mock_client)
    monkeypatch.setattr(model_registry_module, "mlflow", mock_mlflow)
    return {"client": mock_client, "mlflow": mock_mlflow}


@pytest.fixture
def registry(model_registry_deps):
    from src.governance.model_registry import RAGModelRegistry

    return RAGModelRegistry()


def test_register_config(registry, model_registry_deps):
    run_id = "test-run-id"
    config_version = "1.0.0"
    metrics = {"faithfulness": 0.9}
    mock_mlflow = model_registry_deps["mlflow"]
    mock_mlflow_client = model_registry_deps["client"]

    mock_version = MagicMock()
    mock_version.version = "1"
    mock_mlflow.register_model.return_value = mock_version

    version = registry.register_config(run_id, config_version, metrics)

    assert version == "1"
    mock_mlflow.register_model.assert_called_once()
    mock_mlflow_client.update_model_version.assert_called_once()
    call_args = mock_mlflow_client.update_model_version.call_args
    assert "Faithfulness: 0.9" in call_args.kwargs["description"]


def test_promote_to_staging(registry, model_registry_deps):
    mock_mlflow_client = model_registry_deps["client"]

    registry.promote_to_staging("1")

    mock_mlflow_client.set_registered_model_alias.assert_called_with(
        name="contextual-rag-pipeline", alias="challenger", version="1"
    )


def test_promote_to_production_with_archive(registry, model_registry_deps):
    mock_mlflow_client = model_registry_deps["client"]
    mock_current_prod = MagicMock()
    mock_current_prod.version = "1"
    mock_mlflow_client.get_model_version_by_alias.return_value = mock_current_prod

    registry.promote_to_production("2")

    mock_mlflow_client.set_registered_model_alias.assert_any_call(
        name="contextual-rag-pipeline", alias="archived-v1", version="1"
    )
    mock_mlflow_client.set_registered_model_alias.assert_any_call(
        name="contextual-rag-pipeline", alias="champion", version="2"
    )


def test_promote_to_production_first_time(registry, model_registry_deps):
    mock_mlflow_client = model_registry_deps["client"]
    mock_mlflow_client.get_model_version_by_alias.side_effect = Exception("Not found")

    registry.promote_to_production("1")

    mock_mlflow_client.set_registered_model_alias.assert_called_with(
        name="contextual-rag-pipeline", alias="champion", version="1"
    )


def test_rollback_production(registry, model_registry_deps):
    mock_mlflow_client = model_registry_deps["client"]

    registry.rollback_production("1")

    mock_mlflow_client.set_registered_model_alias.assert_called_with(
        name="contextual-rag-pipeline", alias="champion", version="1"
    )


def test_get_production_config(registry, model_registry_deps):
    mock_mlflow_client = model_registry_deps["client"]
    mock_mlflow = model_registry_deps["mlflow"]

    mock_prod_version = MagicMock()
    mock_prod_version.version = "1"
    mock_prod_version.tags = {"config_version": "1.0.0"}
    mock_mlflow_client.get_model_version_by_alias.return_value = mock_prod_version
    mock_mlflow.artifacts.load_dict.return_value = {"chunk_size": 100}

    config = registry.get_production_config()

    assert config["version"] == "1"
    assert config["config_version"] == "1.0.0"
    assert config["config"]["chunk_size"] == 100
