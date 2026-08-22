from app import retrieval


def test_embedding_model_keeps_cpu_execution_provider(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeTextEmbedding:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(retrieval, "TextEmbedding", FakeTextEmbedding)
    monkeypatch.setattr(retrieval, "_embedding_model", None)

    model = retrieval.get_embedding_model()

    assert isinstance(model, FakeTextEmbedding)
    assert captured == {
        "model_name": "BAAI/bge-small-zh-v1.5",
        "providers": ["CPUExecutionProvider"],
    }
