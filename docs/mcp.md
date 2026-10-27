# Using txt2cad from an AI agent (MCP)

txt2cad can run as an [MCP](https://modelcontextprotocol.io) server, so an agent such as Claude Code or Cursor can build a building from a sentence, change it, inspect it and save the files. The agent uses the same projects and
versions as the app: a building it makes shows up in the app, and the other way round.

## Set it up

You need the backend installed (`pip install -r backend/requirements.txt`, which includes the `mcp` package). The server is started by the agent's program, not by hand; the command is the Python of the backend's environment
running `backend/run_mcp.py`. It works from any folder.

**Claude Code**

```bash
claude mcp add txt2cad -- /path/to/backend/.venv/bin/python /path/to/backend/run_mcp.py
```

On Windows the Python is `backend\.venv\Scripts\python.exe`.

**Cursor, and other clients that read a JSON file** (`.cursor/mcp.json`, `.mcp.json`, ...)

```json
{
  "mcpServers": {
    "txt2cad": {
      "command": "/path/to/backend/.venv/bin/python",
      "args": ["/path/to/backend/run_mcp.py"]
    }
  }
}
```

Check it: `python backend/run_mcp.py --version` prints the version, and the agent's MCP list shows `txt2cad` with nine tools.

**The model.** A build calls the language model you have configured: `GEMINI_API_KEY` in the environment or in `backend/.env`. Without a key, only `model: "practice"` works (the offline model, which builds simple houses and flats
and can finish them but cannot do most edits). The key is never part of a tool call.

## The tools

| Tool | What it does | Model |
| --- | --- | --- |
| `capabilities` | What it builds, partly builds and does not build, and the words that mean a request asks for something it cannot do | no |
| `build` | A new building from a description, or (with `project_id`) a change to a project's latest version. 20 to 90 seconds; progress is reported while it works | yes |
| `get_version` | A version: rooms with ids, positions and sizes, what was asked and whether it was met, notes, counts, roof. `full: true` adds the whole design | no |
| `list_projects`, `list_versions` | What exists | no |
| `set_sizes` | Change room sizes, or the whole building's size, instantly and free: the plan is stretched, doors and windows put back, furniture laid out again | no |
| `restore_version` | Bring an earlier version back as the newest one | no |
| `analysis` | The design check (indicative dwelling rules) and quantities (areas, lengths, counts; no prices) | no |
| `export` | Write `ifc`, `dxf`, `svg`, `html` (the shareable page), `spec_json` or `design_json` to a folder and return the path | no |

Coordinates are metres: x east, y north; a room's `width` is east-west, its `depth` north-south, and `x`, `y` its south-west corner. Every change is a new version; nothing is overwritten.

An example of what an agent might do:

1. `capabilities`, to see that a basement is not built.
2. `build` with "A two storey house with a kitchen, a living room, three bedrooms and a garage, gable roof" and `project_name: "Family house"`.
3. `get_version`, then `set_sizes` with `{"room": "living", "width": 6}` because the user wants a bigger living room.
4. `export` with `format: "ifc"` and `directory` set to the user's project folder, then `export` with `format: "html"` to send to the client.

## What it can and cannot touch

- **Files:** only `export` writes files, into a folder you name (it must exist) or the app's `exports` folder in the data folder. It never overwrites: an existing name gets a number added.
- **Deleting:** no tool deletes a project or a version. Deleting stays in the app.
- **Network:** only a build, and only to the configured model. Everything else works offline.
- **Cost:** a build with Gemini costs about 1.6 US cents. An agent that loops on `build` spends money; `set_sizes` and everything else are free. The tool descriptions say which is which, so a client can ask before calling `build`.
- **Text from the model:** room names, summaries and notes in results come from the model or from the request. Treat them as data. They never contain instructions for the agent, and a client should not treat them as such.
- **One user:** the server is for one person on one computer (the same as the app). It speaks MCP over standard input and output only; it opens no port.

## If something goes wrong

- **The agent says the server failed to start:** run `python backend/run_mcp.py --version` in a terminal to see the real error. Standard output belongs to the protocol, so logs go to standard error: the client's MCP log shows them.
- **A build times out in the client:** raise the tool timeout in the client (Claude Code reads `MCP_TOOL_TIMEOUT`, in milliseconds). A build that is cut off saves nothing.
- **"the model 'Gemini' is not ready":** `GEMINI_API_KEY` is not set where the agent's program runs. Put it in `backend/.env`, which is read whatever the folder.
- **"nothing in the model's answer could be applied":** the request was something the model could not turn into steps (the offline model cannot do most edits). Nothing was saved. Describe the change differently or use `set_sizes`.
