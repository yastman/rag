"""MLflow Model Registry for RAG pipeline governance."""

import logging
from datetime import datetime

import mlflow
from mlflow.tracking import MlflowClient


logger = logging.getLogger(__name__)


class RAGModelRegistry:
    """
    Manage RAG pipeline configs as "models" in MLflow Model Registry.

    Workflow:
    1. Experiment → Test new config (chunking, embedding, search)
    2. Staging → Deploy to staging environment for validation
    3. Production → Promote to production after acceptance criteria met
    """

    def __init__(self) -> None:
        """Initialize Model Registry client."""
        self.client = MlflowClient()
        self.model_name = "contextual-rag-pipeline"

    def register_config(
        self, run_id: str, config_version: str, metrics: dict, description: str = ""
    ) -> str:
        """
        Register RAG config as model version.

        Args:
            run_id: MLflow run ID with the config
            config_version: Semantic version (e.g., "1.2.0")
            metrics: Evaluation metrics (recall, ndcg, latency)
            description: Human-readable description of changes

        Returns:
            Model version number
        """

        # Register model from run
        model_uri = f"runs:/{run_id}/config"

        model_version = mlflow.register_model(
            model_uri=model_uri,
            name=self.model_name,
            tags={
                "config_version": config_version,
                "registered_at": datetime.now().isoformat(),
            },
        )

        # Add detailed description
        self.client.update_model_version(
            name=self.model_name,
            version=model_version.version,
            description=f"""
{description}

**Metrics:**
- Faithfulness: {metrics.get("faithfulness", "N/A")}
- Context Precision: {metrics.get("context_precision", "N/A")}
- Context Recall: {metrics.get("context_recall", "N/A")}
- Latency P95: {metrics.get("latency_p95_ms", "N/A")}ms

**Config Version:** {config_version}
**Registered:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
""",
        )

        print(f"✅ Registered model version: {model_version.version}")
        print(f"   Config version: {config_version}")

        return str(model_version.version)

    def promote_to_staging(self, version: str) -> None:
        """Promote config to Staging via alias."""
        self.client.set_registered_model_alias(
            name=self.model_name, alias="challenger", version=version
        )

        print(f"✅ Promoted version {version} to Staging (alias: challenger)")

    def promote_to_production(self, version: str, archive_previous: bool = True) -> None:
        """
        Promote config to Production.

        Args:
            version: Version to promote
            archive_previous: Archive previous production version
        """

        # Archive current production version by removing its alias
        if archive_previous:
            try:
                current_prod = self.client.get_model_version_by_alias(
                    name=self.model_name, alias="champion"
                )

                self.client.set_registered_model_alias(
                    name=self.model_name,
                    alias=f"archived-v{current_prod.version}",
                    version=current_prod.version,
                )

                print(f"📦 Archived previous production version: {current_prod.version}")

            except Exception:
                logger.warning("No current production version to archive", exc_info=True)

        # Promote new version via alias
        self.client.set_registered_model_alias(
            name=self.model_name, alias="champion", version=version
        )

        print(f"🚀 Promoted version {version} to Production (alias: champion)")

    def rollback_production(self, to_version: str) -> None:
        """Rollback production to specific version."""
        print(f"⚠️  Rolling back production to version {to_version}")

        self.promote_to_production(to_version, archive_previous=False)

        print("✅ Rollback complete")

    def get_production_config(self) -> dict[str, object] | None:
        """Get current production config."""
        try:
            prod_version = self.client.get_model_version_by_alias(
                name=self.model_name, alias="champion"
            )

            # Load config from artifact
            config_uri = f"models:/{self.model_name}@champion/config"
            config = mlflow.artifacts.load_dict(config_uri)

            return {
                "version": prod_version.version,
                "config": config,
                "config_version": prod_version.tags.get("config_version"),
            }

        except Exception as e:
            print(f"❌ Failed to load production config: {e}")
            return None


# Example usage
if __name__ == "__main__":
    registry = RAGModelRegistry()

    # After successful evaluation
    run_id = "abc123"  # From MLflow run
    metrics = {
        "faithfulness": 0.87,
        "context_precision": 0.82,
        "context_recall": 0.91,
        "latency_p95_ms": 450,
    }

    # Register new config
    version = registry.register_config(
        run_id=run_id,
        config_version="1.2.0",
        metrics=metrics,
        description="Improved chunking with 600 tokens + contextual embeddings",
    )

    # Test in staging
    registry.promote_to_staging(version)

    # After staging validation → promote to production
    registry.promote_to_production(version)

    # If issues detected → rollback
    registry.rollback_production(to_version="5")  # Previous stable version
