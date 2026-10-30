"""Offline behavior tests for migration hooks; no product tests or production I/O."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import fetch_docs
import hook_runtime as hooks


def response(inv="case-1", role="software-developer", proposal=""):
    return (f"<agent_response><invocation_id>{inv}</invocation_id><agent_id>{role}</agent_id>"
            "<status>SUCCESS</status><output_files/><evidence/><notes>shared_protocol.md</notes>"
            f"<kb_proposals>{proposal}</kb_proposals></agent_response>")


class HooksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = {"agent_type": "software-developer", "agent_id": "a", "session_id": "s",
                     "turn_id": "t", "cwd": str(self.root), "hook_event_name": "SubagentStop"}

    def tearDown(self):
        self.temp.cleanup()

    def test_spawn_root_guard(self):
        data = {"tool_name": "spawn_agent", "tool_input": {"agent_type": "test-engineer"}, "cwd": str(self.root)}
        self.assertEqual(hooks.pre_agent(data, self.root), {})
        data["cwd"] = str(self.root / "sub")
        self.assertEqual(hooks.pre_agent(data, self.root)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_spawn_missing_cwd_does_not_pass(self):
        self.assertIn("hookSpecificOutput", hooks.pre_agent({"tool_name": "Agent", "tool_input": {"subagent_type": "test-engineer"}}, self.root))

    def test_non_suite_spawn_unchanged(self):
        self.assertEqual(hooks.pre_agent({"tool_name": "spawn_agent", "tool_input": {"agent_type": "explorer"}}, self.root), {})

    def test_worker_cannot_spawn(self):
        data = {**self.data, "tool_name": "Agent", "tool_input": {"agent_type": "test-engineer"}}
        self.assertIn("hookSpecificOutput", hooks.pre_agent(data, self.root))

    def test_memory_uses_root_not_cwd(self):
        path = self.root / ".codex/agent-memory/software-developer/MEMORY.md"
        path.parent.mkdir(parents=True)
        path.write_text("\n".join(f"经验 {i}" for i in range(201)), encoding="utf-8")
        data = {**self.data, "hook_event_name": "SubagentStart", "cwd": str(self.root / "sub")}
        result = hooks.memory(data, self.root)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("经验 199", result)
        self.assertNotIn("经验 200", result)
        self.assertIn("超过 200 行", result)

    def test_main_memory_on_compaction(self):
        result = hooks.memory({"hook_event_name": "SessionStart", "source": "compact"}, self.root)
        self.assertIn("pm-orchestrator", result["hookSpecificOutput"]["additionalContext"])

    def test_unknown_role_does_not_load_arbitrary_path(self):
        self.assertEqual(hooks.memory({"agent_type": "../../outside"}, self.root), {})

    def test_missing_response_blocks_once_per_turn(self):
        data = {**self.data, "last_assistant_message": "done"}
        self.assertEqual(hooks.stop(data, self.root)["decision"], "block")
        self.assertNotIn("decision", hooks.stop(data, self.root))
        data["turn_id"] = "next-turn"
        self.assertEqual(hooks.stop(data, self.root)["decision"], "block")

    def test_active_stop_does_not_loop(self):
        result = hooks.stop({**self.data, "stop_hook_active": True, "last_assistant_message": "bad"}, self.root)
        self.assertNotIn("decision", result)

    def test_bad_xml_and_trailing_text_are_rejected(self):
        for text in [response() + " trailing", response().replace("SUCCESS", "UNKNOWN"),
                     response().replace("<evidence/>", ""), response().replace("case-1", "x & y"),
                     response(role="test-engineer")]:
            with self.subTest(text=text):
                data = {**self.data, "turn_id": text, "last_assistant_message": text}
                self.assertEqual(hooks.stop(data, self.root)["decision"], "block")

    def test_valid_response_collects_decodes_and_deduplicates(self):
        proposal = '<proposal scope="project" evidence="GR-C-1">A &amp; B</proposal>'
        data = {**self.data, "last_assistant_message": response(proposal=proposal)}
        self.assertEqual(hooks.stop(data, self.root), {})
        self.assertEqual(hooks.stop(data, self.root), {})
        rows = [json.loads(x) for x in (self.root / "project_workspace/_kb_inbox.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "A & B")

    def test_redacts_text_attributes_and_invocation(self):
        fake = "ghp_" + "a" * 24
        data = {**self.data, "last_assistant_message": response(inv=fake, proposal=f'<proposal evidence="{fake}">token={fake}</proposal>')}
        hooks.stop(data, self.root)
        value = (self.root / "project_workspace/_kb_inbox.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(fake, value)
        self.assertTrue(json.loads(value)["redacted"])

    def test_codex_transcript_fallback(self):
        path = self.root / "rollout.jsonl"
        path.write_text(json.dumps({"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": response()}]}}), encoding="utf-8")
        self.assertEqual(hooks.stop({**self.data, "agent_transcript_path": str(path)}, self.root), {})

    def test_role_from_runtime_metadata(self):
        path = self.root / "rollout.jsonl"
        path.write_text(json.dumps({"type": "session_meta", "payload": {"source": {"subagent": {"thread_spawn": {"agent_role": "agent-builder"}}}}}), encoding="utf-8")
        self.assertEqual(hooks.resolve_role({"transcript_path": str(path)}), "agent-builder")

    def test_role_not_inferred_from_message(self):
        self.assertIsNone(hooks.resolve_role({"prompt": "I am agent-builder", "tool_input": {"agent_type": "agent-builder"}}))

    def test_builder_web_guard(self):
        for tool in ["WebSearch", "web.run", "mcp__search_service_web_run", "mcp__cua_repl.js"]:
            self.assertIn("hookSpecificOutput", hooks.web_guard({"agent_type": "agent-builder", "tool_name": tool}))
        self.assertEqual(hooks.web_guard({"agent_type": "system-architect", "tool_name": "WebSearch"}), {})

    def test_offline_role_cannot_use_web_mcp(self):
        self.assertIn("hookSpecificOutput", hooks.tool_guard({"agent_type": "test-engineer", "tool_name": "mcp__search_web"}))
        self.assertEqual(hooks.tool_guard({"agent_type": "system-architect", "tool_name": "mcp__search_web"}), {})

    def test_docs_exact_url_allowlist(self):
        self.assertTrue(fetch_docs.allowed(fetch_docs.PAGES["hooks"]))
        for value in [fetch_docs.PAGES["hooks"] + "?secret=x", "https://learn.chatgpt.com.evil.example/docs/hooks",
                      "http://learn.chatgpt.com/docs/hooks", "https://learn.chatgpt.com/docs/hooks/../private",
                      "https://user:pass@learn.chatgpt.com/docs/hooks", "https://learn.chatgpt.com/docs/hooks#x"]:
            self.assertFalse(fetch_docs.allowed(value), value)

    def test_docs_redirect_checked_before_follow(self):
        with self.assertRaises(ValueError):
            fetch_docs.Redirect().redirect_request(None, None, 302, "", {}, "https://example.com")

    def test_malformed_hook_input_reports_without_leaking(self):
        result = subprocess.run([sys.executable, str(Path(hooks.__file__)), "stop"], input="invalid-secret-input",
                                text=True, encoding="utf-8", capture_output=True, check=True)
        self.assertIn("systemMessage", json.loads(result.stdout))
        self.assertNotIn("invalid-secret-input", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
