# SDK dependency decisions

This record covers SDK choices whose indirect dependencies are easy to misread. Package manifests remain the source of truth for versions.

## Qdrant client and `grpcio`

First-party application dependencies declare `qdrant-client`, not `grpcio`. The Qdrant SDK declares `grpcio` as a required transitive dependency, so another direct declaration would duplicate resolver ownership.

The user-facing `QdrantService` defaults to REST (`prefer_grpc=False`) because local Compose exposes port 6333, not the gRPC port 6334. The preflight check intentionally tries `prefer_grpc=True` first, then REST, so operators can diagnose gRPC availability. Keeping that diagnostic does not make `grpcio` a first-party direct dependency.

Revisit this decision only if code starts importing the `grpc` package directly or a supported deployment makes gRPC the runtime default. In either case, update the manifests and dependency contract together.
