"""Tests for AI prompts — verify they contain expected placeholders."""

from conductor.ai.prompts import SUMMARIZE_PROMPT, SUGGEST_PROMPT, NLP_PARSE_PROMPT


class TestPrompts:
    def test_summarize_prompt_has_placeholder(self):
        assert "{terminal_output}" in SUMMARIZE_PROMPT

    def test_summarize_prompt_format(self):
        result = SUMMARIZE_PROMPT.format(terminal_output="test output")
        assert "test output" in result

    def test_suggest_prompt_has_placeholders(self):
        assert "{terminal_output}" in SUGGEST_PROMPT
        assert "{project_alias}" in SUGGEST_PROMPT
        assert "{session_type}" in SUGGEST_PROMPT
        assert "{working_dir}" in SUGGEST_PROMPT

    def test_suggest_prompt_format(self):
        result = SUGGEST_PROMPT.format(
            terminal_output="output",
            project_alias="MyApp",
            session_type="claude-code",
            working_dir="/tmp",
        )
        assert "MyApp" in result

    def test_nlp_prompt_has_placeholders(self):
        assert "{user_message}" in NLP_PARSE_PROMPT
        assert "{session_list_json}" in NLP_PARSE_PROMPT
        assert "{last_prompt_context}" in NLP_PARSE_PROMPT

    def test_nlp_prompt_format(self):
        result = NLP_PARSE_PROMPT.format(
            user_message="show status",
            session_list_json="[]",
            last_prompt_context="None",
        )
        assert "show status" in result
