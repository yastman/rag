Placeholder ONNX model context for Docker Compose static render gates.

These files are intentionally tiny and invalid as model artifacts (41 bytes
each). They exist only so `tests/fixtures/compose.ci.env` can RENDER the
`bge-m3` service without relying on a host-specific `/tmp` path.

They must never satisfy a real build or runtime: the Dockerfile verifies the
artifact against `services/bge-m3-api/artifact_manifest.json` (byte sizes +
SHA-256) before baking, so building with these placeholders fails loudly.

Local runtime builds must set `BGE_M3_ONNX_MODEL_HOST_DIR` to a real,
verified artifact directory produced by
`services/bge-m3-api/fetch_artifact.py` (containing `model.onnx`,
`model.onnx_data`, `tokenizer/`, and `artifact_manifest.json`).
