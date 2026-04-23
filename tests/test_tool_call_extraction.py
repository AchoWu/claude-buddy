"""
Test suite for tool call extraction with nested braces fix.
Tests the _extract_tool_calls_and_text() method that was fixed to handle
regex patterns with nested braces (e.g., grep patterns like \{.*?\}).
"""

import pytest
import re
import json
from pathlib import Path
import sys

# Add the parent directory to the path so we can import UI modules
ui_path = Path(__file__).parent.parent / "ui"
sys.path.insert(0, str(ui_path.parent))

from ui.chat_dialog import ChatDialog


class TestToolCallExtraction:
    """Tests for the _extract_tool_calls_and_text() helper method"""
    
    @pytest.fixture
    def chat_dialog(self):
        """Create a ChatDialog instance for testing"""
        # Create a minimal PyQt6 application context if needed
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        dialog = ChatDialog()
        yield dialog
        # Cleanup if needed
    
    def test_simple_tool_call(self, chat_dialog):
        """Test extraction of a simple tool call"""
        text = 'Here is the result: <tool_call>{"name": "echo", "arguments": {"command": "hello"}}</tool_call>'
        parts = chat_dialog._extract_tool_calls_and_text(text)
        
        # Should have text before and tool call
        assert len(parts) == 2
        assert parts[0] == ("text", "Here is the result:")
        assert parts[1][0] == "tool"
        assert parts[1][1][0] == "echo"
        assert parts[1][1][1] == "hello"
    
    def test_grep_with_nested_braces(self, chat_dialog):
        """Test extraction of grep tool with regex pattern containing nested braces"""
        # This is the main bug case: regex pattern with \{ and \}
        text = '<tool_call>{"name": "Grep", "arguments": {"pattern": "\\\\{.*?\\\\}", "path": "/tmp"}}</tool_call>'
        parts = chat_dialog._extract_tool_calls_and_text(text)
        
        # Should extract the tool call successfully
        assert any(p[0] == "tool" and p[1][0] == "Grep" for p in parts), \
            f"Grep tool not extracted. Parts: {parts}"
    
    def test_multiple_tool_calls(self, chat_dialog):
        """Test extraction of multiple tool calls in one message"""
        text = 'Text before <tool_call>{"name": "Tool1", "arguments": {"command": "cmd1"}}</tool_call> middle text <tool_call>{"name": "Tool2", "arguments": {"command": "cmd2"}}</tool_call> text after'
        parts = chat_dialog._extract_tool_calls_and_text(text)
        
        # Should have multiple text and tool parts
        text_parts = [p for p in parts if p[0] == "text"]
        tool_parts = [p for p in parts if p[0] == "tool"]
        
        assert len(tool_parts) == 2
        assert len(text_parts) == 3
        assert tool_parts[0][1][0] == "Tool1"
        assert tool_parts[1][1][0] == "Tool2"
    
    def test_complex_grep_pattern(self, chat_dialog):
        """Test grep pattern with multiple regex metacharacters"""
        text = '<tool_call>{"name": "Grep", "arguments": {"pattern": "def\\\\s+\\\\w+\\\\s*\\\\{.*?\\\\}", "glob": "*.py"}}</tool_call>'
        parts = chat_dialog._extract_tool_calls_and_text(text)
        
        # Should successfully extract despite complex regex
        assert any(p[0] == "tool" and p[1][0] == "Grep" for p in parts)
    
    def test_deeply_nested_json(self, chat_dialog):
        """Test tool call with deeply nested JSON structures"""
        text = '<tool_call>{"name": "ComplexTool", "arguments": {"nested": {"key": "value", "count": 123, "inner": {"deep": "data"}}}}</tool_call>'
        parts = chat_dialog._extract_tool_calls_and_text(text)
        
        # Should handle nested objects
        assert any(p[0] == "tool" and p[1][0] == "ComplexTool" for p in parts)
    
    def test_tool_call_with_whitespace(self, chat_dialog):
        """Test tool call extraction with extra whitespace"""
        text = '<tool_call>  \n  {"name": "Tool", "arguments": {"command": "test"}}  \n  </tool_call>'
        parts = chat_dialog._extract_tool_calls_and_text(text)
        
        # Should handle whitespace correctly
        assert any(p[0] == "tool" and p[1][0] == "Tool" for p in parts)
    
    def test_empty_message(self, chat_dialog):
        """Test extraction from empty message"""
        parts = chat_dialog._extract_tool_calls_and_text("")
        assert parts == []
    
    def test_message_without_tool_calls(self, chat_dialog):
        """Test extraction from message without tool calls"""
        text = "This is just a regular message with no tool calls"
        parts = chat_dialog._extract_tool_calls_and_text(text)
        
        assert len(parts) == 1
        assert parts[0][0] == "text"
        assert parts[0][1] == text
    
    def test_tool_call_only(self, chat_dialog):
        """Test message containing only a tool call"""
        text = '<tool_call>{"name": "SingleTool", "arguments": {"arg": "value"}}</tool_call>'
        parts = chat_dialog._extract_tool_calls_and_text(text)
        
        assert len(parts) == 1
        assert parts[0][0] == "tool"
        assert parts[0][1][0] == "SingleTool"
    
    def test_escaped_quotes_in_json(self, chat_dialog):
        """Test tool call with escaped quotes in arguments"""
        # JSON with escaped quotes in a string value
        text = '<tool_call>{"name": "Tool", "arguments": {"message": "Say \\"hello\\" world"}}</tool_call>'
        parts = chat_dialog._extract_tool_calls_and_text(text)
        
        # Should handle escaped quotes
        assert any(p[0] == "tool" and p[1][0] == "Tool" for p in parts)


class TestToolCallExtractionIntegration:
    """Integration tests with actual conversation history"""
    
    @pytest.fixture
    def chat_dialog(self):
        """Create a ChatDialog instance for testing"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        dialog = ChatDialog()
        yield dialog
    
    def test_load_history_with_grep_tool(self, chat_dialog):
        """Test loading conversation history with grep tool calls"""
        # Simulate a conversation with grep tool
        messages = [
            {
                "role": "user",
                "content": "Search for error patterns",
                "timestamp": 1234567890
            },
            {
                "role": "assistant",
                "content": 'Let me search for that: <tool_call>{"name": "Grep", "arguments": {"pattern": "\\\\{.*?\\\\}", "path": "/tmp"}}</tool_call>',
                "timestamp": 1234567891
            }
        ]
        
        # This should not raise an exception
        chat_dialog.load_history(messages)
        
        # The dialog should have loaded successfully
        # (In a real test, we'd verify the UI contains the tool bubble)
        assert chat_dialog is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
