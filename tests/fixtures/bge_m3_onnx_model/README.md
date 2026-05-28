Placeholder ONNX INT8 model context for Docker Compose static build gates.

These files are intentionally tiny and invalid as model artifacts. They exist
only so `tests/fixtures/compose.ci.env` can render and build the `bge-m3`
image without relying on a host-specific `/tmp` path.

Local runtime builds must set `BGE_M3_ONNX_MODEL_HOST_DIR` to a real directory
containing `model.int8.onnx` and `model.int8.onnx.data`.
