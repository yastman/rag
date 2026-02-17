"""Tests for SummarizationNode integration (langmem SDK)."""

from __future__ import annotations


class TestSummarizationNodeIntegration:
    def test_summarize_node_is_runnable(self):
        """SummarizationNode has invoke/ainvoke (LangChain Runnable protocol)."""
        from langmem.short_term import SummarizationNode

        node = SummarizationNode(
            model="gpt-4o-mini",
            max_tokens=512,
            input_messages_key="messages",
            output_messages_key="messages",
        )
        assert hasattr(node, "invoke")
        assert hasattr(node, "ainvoke")

    def test_summarize_node_accepts_token_counter(self):
        """SummarizationNode accepts count_tokens_approximately."""
        from langchain_core.messages.utils import count_tokens_approximately
        from langmem.short_term import SummarizationNode

        node = SummarizationNode(
            model="gpt-4o-mini",
            max_tokens=512,
            max_tokens_before_summary=1024,
            max_summary_tokens=256,
            token_counter=count_tokens_approximately,
            input_messages_key="messages",
            output_messages_key="messages",
        )
        assert hasattr(node, "ainvoke")
        assert node.max_tokens == 512
        assert node.max_tokens_before_summary == 1024

    def test_summarize_node_output_messages_key(self):
        """SummarizationNode output_messages_key must be 'messages' for state compat."""
        from langmem.short_term import SummarizationNode

        node = SummarizationNode(
            model="gpt-4o-mini",
            max_tokens=512,
            input_messages_key="messages",
            output_messages_key="messages",
        )
        assert node.output_messages_key == "messages"
