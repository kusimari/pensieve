"""Drive pensieve over stdio on temp stores, with a temp HOME and cwd."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent / "pensieve.py"


def snapshot(directory):
    return {
        p.relative_to(directory).as_posix(): p.read_bytes() if p.is_file() else None
        for p in Path(directory).rglob("*")
    }


def env(home):
    return {"PATH": os.environ.get("PATH", ""), "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}


class Server:
    def __init__(self, store, home):
        self.proc = subprocess.Popen(
            [sys.executable, "-I", str(SERVER), "--store", str(store)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            cwd=home,
            env=env(home),
            text=True,
        )
        self.next_id = 0

    def raw(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def send(self, method, params=None):
        self.next_id += 1
        msg = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}}
        reply = self.raw(json.dumps(msg))
        assert reply["id"] == self.next_id
        return reply

    def call(self, name, **arguments):
        result = self.send("tools/call", {"name": name, "arguments": arguments})["result"]
        return result["content"][0]["text"], result["isError"]

    def ok(self, name, **arguments):
        text, failed = self.call(name, **arguments)
        assert not failed, text
        return text

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=5)
        self.proc.stdout.close()


class Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.store = self.make_store("store")
        self.mem = self.store / "memory"

    def make_store(self, name, about=None):
        store = self.tmp / name
        (store / "memory").mkdir(parents=True)
        if about is not None:
            (store / "about.md").write_text(about)
        return store

    def server(self, store=None):
        server = Server(store or self.store, self.home)
        self.addCleanup(server.close)
        server.send(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        )
        return server


class TestStartup(Case):
    def test_instructions_carry_about_md(self):
        (self.store / "about.md").write_text("Belongs here: coffee.\nNot here: work.\n")
        reply = Server(self.store, self.home)
        self.addCleanup(reply.close)
        result = reply.send("initialize", {"protocolVersion": "2025-11-25"})["result"]
        self.assertEqual(result["protocolVersion"], "2025-11-25")
        self.assertIn("Belongs here: coffee.\nNot here: work.", result["instructions"])
        self.assertIn("ask the user", result["instructions"][:512])

    def test_lead_says_when_to_save_and_fits_beside_about_md(self):
        (self.store / "about.md").write_text("x" * 800)
        text = self.server().send("initialize", {})["result"]["instructions"]
        lead = text[: text.index("x" * 800)]
        self.assertIn("memory_search first when context on the user", lead)
        self.assertIn("Save here on your own", lead[:512])
        for kind in ("user", "feedback", "project", "reference"):
            self.assertIn(f"\n- {kind}: ", lead[:512])
        self.assertIn("name its repo or project in the description", lead[:512])
        self.assertIn("Do not save what the repo, git history or this conversation", lead)
        self.assertIn("When the user says where to store something, do that", lead)
        self.assertIn("ask the user once", lead[:512])
        self.assertLess(len(text), 2048)

    def test_unknown_protocol_version_gets_ours(self):
        old = self.server().send("initialize", {"protocolVersion": "2025-06-18"})["result"]
        new = self.server().send("initialize", {"protocolVersion": "1999-01-01"})["result"]
        self.assertEqual(old["protocolVersion"], "2025-06-18")
        self.assertEqual(new["protocolVersion"], "2025-11-25")

    def test_instructions_without_about_md(self):
        result = self.server().send("initialize", {})["result"]
        self.assertIn("This store has no about.md", result["instructions"])

    def test_missing_store_exits_and_writes_nothing(self):
        proc = subprocess.run(
            [sys.executable, "-I", str(SERVER), "--store", str(self.tmp / "nope")],
            capture_output=True,
            text=True,
            cwd=self.home,
            env=env(self.home),
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not a directory", proc.stderr)
        self.assertFalse((self.tmp / "nope").exists())

    def test_tools_list(self):
        tools = self.server().send("tools/list")["result"]["tools"]
        names = [t["name"] for t in tools]
        self.assertEqual(
            names,
            [
                "memory_view",
                "memory_create",
                "memory_str_replace",
                "memory_insert",
                "memory_delete",
                "memory_rename",
                "memory_search",
            ],
        )
        for t in tools:
            self.assertIn("Serves this store only", t["description"])
            self.assertLessEqual(len(t["description"]), 2048)
        create = tools[1]["description"]
        self.assertIn("metadata with type", create)
        self.assertIn("First run memory_search", create)
        self.assertIn("project = context on their work, naming its repo", create)
        self.assertIn("not what the user asked to store elsewhere", create)
        self.assertIn("MEMORY.md", create)

    def test_unknown_method(self):
        self.assertEqual(self.server().send("server/discover")["error"]["code"], -32601)

    def test_bad_messages_get_errors_and_the_server_keeps_serving(self):
        s = self.server()
        self.assertEqual(s.raw("{not json")["error"]["code"], -32700)
        for line in ["5", "null", '"id"', "[1]"]:
            self.assertEqual(s.raw(line)["error"]["code"], -32600, line)
        bad_params = '{"jsonrpc": "2.0", "id": 99, "method": "tools/call", "params": [1]}'
        self.assertEqual(s.raw(bad_params)["error"]["code"], -32602)
        self.assertEqual(s.send("tools/call", {"name": 5})["error"]["code"], -32603)
        s.proc.stdin.flush()
        s.proc.stdin.buffer.write(b"\xff\xfe\n")
        s.proc.stdin.buffer.flush()
        self.assertEqual(json.loads(s.proc.stdout.readline())["error"]["code"], -32700)
        self.assertEqual(s.raw("[" * 100000)["error"]["code"], -32700)
        unknown = s.send("tools/call", {"name": "rm_rf", "arguments": {}})
        self.assertEqual(unknown["error"]["code"], -32602)
        s.proc.stdin.write('{"jsonrpc": "2.0", "method": "notifications/initialized"}\n')
        self.assertEqual(s.send("ping")["result"], {})  # the notification got no reply


class TestCommands(Case):
    def setUp(self):
        super().setUp()
        self.s = self.server()

    def test_view_dir_lists_and_hides_dot_files(self):
        (self.mem / "a.md").write_text("x")
        (self.mem / "sub").mkdir()
        (self.mem / "sub" / "b.md").write_text("y")
        (self.mem / ".hidden").write_text("z")
        text = self.s.ok("memory_view", path="/memories")
        self.assertIn("/memories/a.md", text)
        self.assertIn("/memories/sub/b.md", text)
        self.assertNotIn(".hidden", text)

    def test_view_file_numbers_lines_and_range(self):
        (self.mem / "a.md").write_text("one\ntwo\nthree")
        self.assertIn("     2\ttwo", self.s.ok("memory_view", path="/memories/a.md"))
        part = self.s.ok("memory_view", path="/memories/a.md", view_range=[2, -1])
        self.assertIn("     3\tthree", part)
        self.assertNotIn("one", part)

    def test_view_dir_with_dangling_link(self):
        (self.mem / "a.md").write_text("x")
        (self.mem / "gone").symlink_to(self.mem / "nothing")
        self.assertIn("/memories/a.md", self.s.ok("memory_view", path="/memories"))

    def test_view_missing(self):
        self.assertTrue(self.s.call("memory_view", path="/memories/none.md")[1])

    def test_create_writes_and_refuses_existing(self):
        self.s.ok("memory_create", path="/memories/dir/new.md", file_text="hello")
        self.assertEqual((self.mem / "dir" / "new.md").read_text(), "hello")
        _, failed = self.s.call("memory_create", path="/memories/dir/new.md", file_text="other")
        self.assertTrue(failed)
        self.assertEqual((self.mem / "dir" / "new.md").read_text(), "hello")

    def test_str_replace_one_match_only(self):
        f = self.mem / "a.md"
        f.write_text("cat dog cat")
        self.assertTrue(
            self.s.call("memory_str_replace", path="/memories/a.md", old_str="cat", new_str="x")[1]
        )
        self.assertTrue(
            self.s.call("memory_str_replace", path="/memories/a.md", old_str="cow", new_str="x")[1]
        )
        self.assertEqual(f.read_text(), "cat dog cat")
        self.s.ok("memory_str_replace", path="/memories/a.md", old_str="dog", new_str="emu")
        self.assertEqual(f.read_text(), "cat emu cat")

    def test_insert(self):
        f = self.mem / "a.md"
        f.write_text("one\nthree\n")
        self.s.ok("memory_insert", path="/memories/a.md", insert_line=1, insert_text="two")
        self.s.ok("memory_insert", path="/memories/a.md", insert_line=0, insert_text="zero")
        self.assertEqual(f.read_text(), "zero\none\ntwo\nthree\n")
        self.assertTrue(
            self.s.call("memory_insert", path="/memories/a.md", insert_line=9, insert_text="x")[1]
        )

    def test_insert_and_replace_keep_line_endings(self):
        f = self.mem / "a.md"
        f.write_bytes(b"a\r\nb\x0cc\n")
        self.s.ok("memory_insert", path="/memories/a.md", insert_line=1, insert_text="x")
        self.s.ok("memory_str_replace", path="/memories/a.md", old_str="a\r\n", new_str="A\r\n")
        self.assertEqual(f.read_bytes(), b"A\r\nx\nb\x0cc\n")

    def test_delete_and_rename_act_on_a_link_not_its_target(self):
        (self.mem / "real").mkdir()
        (self.mem / "real" / "keep.md").write_text("k")
        (self.mem / "alias").symlink_to(self.mem / "real")
        (self.mem / "alias2").symlink_to(self.mem / "real")
        self.s.ok("memory_delete", path="/memories/alias")
        self.s.ok("memory_rename", old_path="/memories/alias2", new_path="/memories/moved")
        self.assertFalse((self.mem / "alias").is_symlink())
        self.assertTrue((self.mem / "moved").is_symlink())
        self.assertEqual((self.mem / "real" / "keep.md").read_text(), "k")

    def test_delete_file_dir_not_root(self):
        (self.mem / "a.md").write_text("x")
        (self.mem / "sub").mkdir()
        (self.mem / "sub" / "b.md").write_text("y")
        self.s.ok("memory_delete", path="/memories/a.md")
        self.s.ok("memory_delete", path="/memories/sub")
        self.assertEqual(list(self.mem.iterdir()), [])
        self.assertTrue(self.s.call("memory_delete", path="/memories")[1])
        self.assertTrue(self.mem.is_dir())

    def test_rename_refuses_existing_target(self):
        (self.mem / "a.md").write_text("a")
        (self.mem / "b.md").write_text("b")
        self.assertTrue(
            self.s.call("memory_rename", old_path="/memories/a.md", new_path="/memories/b.md")[1]
        )
        self.s.ok("memory_rename", old_path="/memories/a.md", new_path="/memories/old/c.md")
        self.assertEqual((self.mem / "old" / "c.md").read_text(), "a")
        self.assertFalse((self.mem / "a.md").exists())

    def test_search_line_numbers_match_view(self):
        (self.mem / "a.md").write_bytes(b"a\x0cb word\nc word\n")
        self.assertIn("2: c word", self.s.ok("memory_search", query="word"))
        self.assertIn("     2\tc word", self.s.ok("memory_view", path="/memories/a.md"))
        self.assertIn("a.md", self.s.ok("memory_view", path="/memories/."))

    def test_search_needs_every_word(self):
        (self.mem / "coffee.md").write_text(
            "---\nname: coffee\n---\nGrind 18 clicks for Pour-over.\n"
        )
        (self.mem / "tea.md").write_text("Pour-over is not for tea.\n")
        text = self.s.ok("memory_search", query="pour-over GRIND")
        self.assertIn("/memories/coffee.md", text)
        self.assertIn("4: Grind 18 clicks", text)
        self.assertNotIn("tea.md", text)
        self.assertIn("No memory", self.s.ok("memory_search", query="espresso"))

    def test_bad_arguments_are_tool_errors(self):
        self.assertTrue(self.s.call("memory_view")[1])
        self.assertTrue(self.s.call("memory_view", path=None)[1])
        self.s.ok("memory_view", path="/memories")  # still serving


class TestPathSafety(Case):
    def test_escapes_refused(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "secret.md").write_text("secret words")
        (self.store / "about.md").write_text("about")
        (self.mem / "link").symlink_to(outside)
        (self.mem / "filelink.md").symlink_to(outside / "secret.md")
        (self.mem / "real.md").write_text("real")
        (outside / "back.md").symlink_to(self.mem / "real.md")  # a link outside pointing in
        s = self.server()
        before = snapshot(self.tmp)
        for path in [
            "/etc/passwd",
            "memory/x.md",
            "/memories/../about.md",
            "/memories/sub/../a.md",
            "/memories/a/../../x.md",
            "/memoriesX/a.md",
            "/memories/link/secret.md",
            "/memories/link/new.md",
            "/memories/filelink.md",
            "/memories/link/back.md",
        ]:
            for name, args in [
                ("memory_view", {"path": path}),
                ("memory_create", {"path": path, "file_text": "x"}),
                ("memory_delete", {"path": path}),
                ("memory_str_replace", {"path": path, "old_str": "s", "new_str": "x"}),
                ("memory_insert", {"path": path, "insert_line": 0, "insert_text": "x"}),
                ("memory_rename", {"old_path": "/memories/real.md", "new_path": path}),
                ("memory_rename", {"old_path": path, "new_path": "/memories/moved.md"}),
            ]:
                text, failed = s.call(name, **args)
                self.assertTrue(failed, f"{name} {path}: {text}")
        self.assertIn("No memory", s.ok("memory_search", query="secret words"))
        self.assertEqual(snapshot(self.tmp), before)


class TestIsolation(Case):
    def test_two_stores_share_nothing(self):
        other = self.make_store("other")
        a, b = self.server(), self.server(other)
        a.ok("memory_create", path="/memories/cello.md", file_text="learning the cello")
        self.assertIn("No memory", b.ok("memory_search", query="cello"))
        self.assertTrue(b.call("memory_view", path="/memories/cello.md")[1])
        self.assertIn("cello", a.ok("memory_search", query="cello"))

    def test_nothing_written_outside_the_store(self):
        before = snapshot(self.tmp)
        s = self.server()
        s.ok("memory_create", path="/memories/a.md", file_text="one\n")
        s.ok("memory_insert", path="/memories/a.md", insert_line=1, insert_text="two")
        s.ok("memory_str_replace", path="/memories/a.md", old_str="two", new_str="2")
        s.ok("memory_rename", old_path="/memories/a.md", new_path="/memories/b.md")
        s.ok("memory_create", path="/memories/gone.md", file_text="x")
        s.ok("memory_delete", path="/memories/gone.md")
        s.close()
        after = snapshot(self.tmp)
        self.assertEqual({k: v for k, v in after.items() if k != "store/memory/b.md"}, before)
        self.assertEqual(after["store/memory/b.md"], b"one\n2\n")


if __name__ == "__main__":
    unittest.main()
