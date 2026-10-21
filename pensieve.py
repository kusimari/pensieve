"""pensieve: an MCP memory server bound to one store directory."""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = "/memories"
# Lead + a typical about.md must stay under 2,048 chars; the first 512 must stand alone.
LEAD = (
    "pensieve: your memory across sessions, in a store the user owns. If "
    "unsure this session fits the store described below, ask the user once. "
    "Search it with memory_search first when context on the user or their "
    "work would help. Save here on your own what will help a future "
    "session:\n"
    "- user: who they are, role and preferences.\n"
    "- feedback: their corrections and guidance on how to work.\n"
    "- project: context on their work for next time; name its repo or "
    "project in the description.\n"
    "- reference: where things live.\n"
    "Do not save what the repo, git history or this conversation already "
    "records, or anything ephemeral. When the user says where to store "
    "something, do that and do not save it here."
)
NO_ABOUT = (
    "This store has no about.md, so it does not say what belongs here. "
    "Ask the user before saving anything to it."
)
STORE_ONLY = (
    " Serves this store only: save here only what this server's "
    "instructions say belongs here; if unsure which store, ask the user."
)
FORMAT = (
    " Format: one file per memory, /memories/<name>.md, starting with YAML "
    "frontmatter (name, description, and metadata with type: user, "
    "feedback, project or reference), then the body. /memories/MEMORY.md "
    "is the index, one line per memory: - [Title](<name>.md) - one-line "
    "hook. Keep MEMORY.md in step when you create, delete or rename a "
    "memory."
)
CREATE = (
    "Create a new file; fails if it exists. Save on your own what will help "
    "a future session; not what the repo, git history or conversation "
    "already records, and not what the user asked to store elsewhere. First "
    "run memory_search: if a memory on the same topic exists, update it "
    "with memory_str_replace instead of adding a duplicate. Types: user = "
    "who they are, role and preferences; feedback = their corrections and "
    "guidance on how to work; project = context on their work, naming its "
    "repo or project in the description; reference = where things live."
)
VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
PATH = {"type": "string", "description": "Starts with /memories"}
TEXT = {"type": "string"}


def tool(name, description, required, **extra):
    """extra: schemas for non-string arguments, required or optional."""
    props = {key: PATH if key.endswith("path") else TEXT for key in required}
    props.update(extra)
    return {
        "name": name,
        "description": description + STORE_ONLY,
        "inputSchema": {"type": "object", "properties": props, "required": required},
    }


TOOLS = [
    tool(
        "memory_view",
        "View a directory (lists entries two levels deep, hiding dot files) "
        "or a file (numbered lines) in this memory store.",
        ["path"],
        view_range={
            "type": "array",
            "items": {"type": "integer"},
            "description": "[start, end] lines, 1-based; end -1 means the last line",
        },
    ),
    tool("memory_create", CREATE + FORMAT, ["path", "file_text"]),
    tool(
        "memory_str_replace",
        "Replace the one exact occurrence of old_str with new_str in a file." + FORMAT,
        ["path", "old_str", "new_str"],
    ),
    tool(
        "memory_insert",
        "Insert insert_text as a line after line insert_line (0 puts it first)." + FORMAT,
        ["path", "insert_line", "insert_text"],
        insert_line={"type": "integer"},
    ),
    tool("memory_delete", "Delete a file or directory." + FORMAT, ["path"]),
    tool(
        "memory_rename",
        "Rename or move a file or directory; fails if new_path exists." + FORMAT,
        ["old_path", "new_path"],
    ),
    tool(
        "memory_search",
        "Find memories containing every word of the query, case-insensitive. "
        "Returns each file's path and the lines holding a query word.",
        ["query"],
    ),
]


class ToolError(Exception):
    pass


class Store:
    def __init__(self, store):
        self.dir = store
        memory = store / "memory"
        memory.mkdir(exist_ok=True)
        self.root = memory.resolve()

    def instructions(self):
        about = self.dir / "about.md"
        text = about.read_text(encoding="utf-8").strip() if about.is_file() else NO_ABOUT
        return f"{LEAD}\n\n{text}"

    def resolve(self, path):
        if path != ROOT and not path.startswith(ROOT + "/"):
            raise ToolError(f"Path must be {ROOT} or start with {ROOT}/, got: {path}")
        parts = [part for part in path[len(ROOT) :].split("/") if part not in ("", ".")]
        if ".." in parts:
            raise ToolError(f"Path {path} may not contain '..'")
        if not parts:
            return self.root
        # Keep the last part unresolved so delete and rename act on a link, not its target.
        full = self.root.joinpath(*parts[:-1]).resolve() / parts[-1]
        for target in (full.parent, full.resolve()):
            if target != self.root and self.root not in target.parents:
                raise ToolError(f"Path {path} would leave {ROOT}")
        return full

    def existing_file(self, path):
        full = self.resolve(path)
        if not full.is_file():
            raise ToolError(f"The path {path} is not an existing file.")
        return full

    def view(self, path, view_range=None):
        full = self.resolve(path)
        if full.is_dir():
            base = path.rstrip("/")
            rows = [f"{full.stat().st_size}\t{base}"]
            rows += [f"{item.lstat().st_size}\t{base}/{rel}" for item, rel in listing(full, "", 1)]
            return (
                f"Files and directories up to 2 levels deep in {path}, dot files hidden:\n"
                + "\n".join(rows)
            )
        if not full.is_file():
            raise ToolError(f"The path {path} does not exist.")
        lines = read(full).split("\n")
        start = 1
        if view_range and len(view_range) == 2:
            start = max(1, view_range[0])
            end = len(lines) if view_range[1] == -1 else view_range[1]
            lines = lines[start - 1 : end]
        numbered = [f"{n:6}\t{line}" for n, line in enumerate(lines, start)]
        return f"Here's the content of {path} with line numbers:\n" + "\n".join(numbered)

    def create(self, path, file_text):
        full = self.resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        try:
            with full.open("x", encoding="utf-8") as f:
                f.write(file_text)
        except FileExistsError:
            raise ToolError(f"File {path} already exists") from None
        return f"File created successfully at: {path}"

    def str_replace(self, path, old_str, new_str):
        full = self.existing_file(path)
        text = read(full)
        count = text.count(old_str)
        if count != 1:
            raise ToolError(
                f"No replacement was performed: old_str appears {count} times in {path}; it must appear exactly once."
            )
        write(full, text.replace(old_str, new_str))
        return f"The file {path} has been edited."

    def insert(self, path, insert_line, insert_text):
        full = self.existing_file(path)
        lines = read(full).split("\n")
        if lines[-1] == "":
            lines.pop()
        if not 0 <= insert_line <= len(lines):
            raise ToolError(
                f"Invalid insert_line {insert_line}: it should be within [0, {len(lines)}]."
            )
        lines.insert(insert_line, insert_text.rstrip("\n"))
        write(full, "\n".join(lines) + "\n")
        return f"The file {path} has been edited."

    def delete(self, path):
        full = self.resolve(path)
        if full == self.root:
            raise ToolError(f"Cannot delete {ROOT} itself")
        if full.is_symlink() or full.is_file():
            full.unlink()
        elif full.is_dir():
            shutil.rmtree(full)
        else:
            raise ToolError(f"The path {path} does not exist")
        return f"Successfully deleted {path}"

    def rename(self, old_path, new_path):
        old, new = self.resolve(old_path), self.resolve(new_path)
        if not old.exists():
            raise ToolError(f"The path {old_path} does not exist")
        if new.exists():
            raise ToolError(f"The destination {new_path} already exists")
        new.parent.mkdir(parents=True, exist_ok=True)
        old.rename(new)
        return f"Successfully renamed {old_path} to {new_path}"

    def search(self, query):
        words = query.lower().split()
        if not words:
            raise ToolError("The query is empty.")
        hits = []
        for f in sorted(self.root.rglob("*.md")):
            if self.root not in f.resolve().parents or not f.is_file():
                continue
            text = read(f, errors="replace")
            if all(word in text.lower() for word in words):
                lines = [
                    f"  {n}: {line}"
                    for n, line in enumerate(text.split("\n"), 1)
                    if any(word in line.lower() for word in words)
                ]
                hits.append(f"{ROOT}/{f.relative_to(self.root).as_posix()}\n" + "\n".join(lines))
                if len(hits) == 20:
                    break
        return "\n".join(hits) if hits else f"No memory contains all of: {query}"


def read(path, errors="strict"):
    with path.open(
        encoding="utf-8", errors=errors, newline=""
    ) as f:  # newline="": keep CRLF as written
        return f.read()


def write(path, text):
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(text)


def listing(directory, prefix, depth):
    for item in sorted(directory.iterdir()):
        if item.name.startswith("."):
            continue
        rel = prefix + item.name
        if item.is_dir():
            yield item, rel + "/"
            if depth < 2 and not item.is_symlink():
                yield from listing(item, rel + "/", depth + 1)
        else:
            yield item, rel


def handle(store, msg):
    method, params = msg.get("method"), msg.get("params") or {}
    if not isinstance(params, dict):
        return {"error": {"code": -32602, "message": "params must be an object"}}
    if method == "initialize":
        return {
            "result": {
                "protocolVersion": params.get("protocolVersion")
                if params.get("protocolVersion") in VERSIONS
                else VERSIONS[0],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "pensieve", "version": "0.1.0"},
                "instructions": store.instructions(),
            }
        }
    if method == "ping":
        return {"result": {}}
    if method == "tools/list":
        return {"result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name", "")
        command = name.removeprefix("memory_")
        if name not in {t["name"] for t in TOOLS}:
            return {"error": {"code": -32602, "message": f"Unknown tool: {name}"}}
        try:
            text, failed = getattr(store, command)(**params.get("arguments", {})), False
        except Exception as err:  # noqa: BLE001 - bad input must not stop the server
            text, failed = str(err), True
        return {"result": {"content": [{"type": "text", "text": text}], "isError": failed}}
    return {"error": {"code": -32601, "message": f"Method not found: {method}"}}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pensieve", description=__doc__)
    parser.add_argument("--store", required=True, type=Path, help="the store directory")
    args = parser.parse_args(argv)
    if not args.store.is_dir():
        parser.error(f"--store {args.store} is not a directory")
    store = Store(args.store)
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except (ValueError, RecursionError):  # JSONDecodeError is a ValueError
            reply = {"id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            if not isinstance(msg, dict):
                reply = {"id": None, "error": {"code": -32600, "message": "Invalid request"}}
            elif "id" not in msg:
                continue  # a notification: nothing to answer
            else:
                try:
                    reply = {"id": msg["id"], **handle(store, msg)}
                except Exception:  # noqa: BLE001 - a malformed request must not stop the server
                    reply = {
                        "id": msg["id"],
                        "error": {"code": -32603, "message": "Internal error"},
                    }
        print(json.dumps({"jsonrpc": "2.0", **reply}), flush=True)


if __name__ == "__main__":
    main()
