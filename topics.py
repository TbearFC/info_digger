"""Rule-based keyword tagging. Each topic maps to a list of lowercase keywords
that are matched against a combined title+description string."""

TOPICS: dict[str, list[str]] = {
    "LLM Reasoning": [
        "reasoning",
        "chain-of-thought",
        "chain of thought",
        "cot",
        "o1",
        "o3",
        "r1",
        "thinking",
        "step-by-step",
        "step by step",
        "inference-time",
        "test-time compute",
        "monte carlo tree",
        "mcts",
        "self-consistency",
    ],
    "RAG": [
        "rag",
        "retrieval-augmented",
        "retrieval augmented",
        "retrieval augmentation",
        "vector search",
        "vector store",
        "embedding retrieval",
        "knowledge base",
        "document qa",
        "semantic search",
    ],
    "Agents": [
        "agent",
        "agentic",
        "multi-agent",
        "multi agent",
        "tool use",
        "tool calling",
        "function calling",
        "autonomous",
        "workflow automation",
        "ai assistant",
        "computer use",
        "browser use",
    ],
    "Multimodal": [
        "multimodal",
        "vision language",
        "vlm",
        "image-text",
        "image text",
        "video-language",
        "video language",
        "text-to-image",
        "text to image",
        "speech",
        "audio language",
        "omni",
    ],
    "Fine-tuning": [
        "fine-tuning",
        "fine tuning",
        "finetuning",
        "lora",
        "qlora",
        "peft",
        "instruction tuning",
        "rlhf",
        "dpo",
        "sft",
        "alignment",
    ],
    "Inference": [
        "inference",
        "quantization",
        "pruning",
        "distillation",
        "compression",
        "speculative decoding",
        "kv cache",
        "throughput",
        "latency",
        "vllm",
        "tensorrt",
        "onnx",
    ],
}


def tag_entry(title: str, description: str) -> list[str]:
    """Return matching topic names for a given title+description (lowercase match)."""
    text = (title + " " + (description or "")).lower()
    matched = []
    for topic, keywords in TOPICS.items():
        if any(kw in text for kw in keywords):
            matched.append(topic)
    return matched
