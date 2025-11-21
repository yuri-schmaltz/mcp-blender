

# BlenderMCP - Blender Model Context Protocol Integration

BlenderMCP connects Blender to local large language models (LLMs) through the Model Context Protocol (MCP), enabling assistants running on your own hardware to automate Blender workflows. This integration provides prompt-assisted 3D modelling, scene creation, and manipulation guided by AI without relying on cloud services.

**We have no official website. Any website you see online is unofficial and has no affiliation with this project. Use them at your own risk.**

[Quick links](#architecture--data-flow) · [Installation](#installation) · [Usage](#usage) · [Troubleshooting](#troubleshooting) · [Contributing](#contributing)

[Full tutorial](https://www.youtube.com/watch?v=lCyQ717DuzQ)

### Join the Community

Give feedback, get inspired, and build on top of the MCP: [Discord](https://discord.gg/z5apgR8TFU)

### Supporters

<div align="center" markdown="1">
   <sup>Special thanks to:</sup>
   <br>
   <br>
   <a href="https://www.warp.dev/blender-mcp">
      <img alt="Warp sponsorship" width="400" src="https://github.com/user-attachments/assets/c21102f7-bab9-4344-a731-0cf6b341cab2">
   </a>

### [Warp, the intelligent terminal for developers](https://www.warp.dev/blender-mcp)
[Available for MacOS, Linux, & Windows](https://www.warp.dev/blender-mcp)<br>

</div>
<hr>

**Other supporters:**

[CodeRabbit](https://www.coderabbit.ai/)

[Satish Goda](https://github.com/satishgoda)

**All supporters:**

[Support this project](https://github.com/sponsors/ahujasid)

## Release notes (1.2.0)
- View screenshots for Blender viewport to better understand the scene
- Search and download Sketchfab models


### Previously added features:
- Support for Poly Haven assets through their API
- Support to generate 3D models using Hyper3D Rodin
- For newcomers, you can go straight to Installation. For existing users, see the points below
- Download the latest addon.py file and replace the older one, then add it to Blender
- Delete and re-add the MCP server in your preferred MCP-compatible client and you should be good to go!

## Features

- **Two-way communication**: Connect local LLM assistants to Blender through a socket-based server
- **Object manipulation**: Create, modify, and delete 3D objects in Blender
- **Material control**: Apply and modify materials and colors
- **Scene inspection**: Get detailed information about the current Blender scene
- **Code execution**: Run arbitrary Python code in Blender from your assistant

## Components

The system consists of two main components:

1. **Blender Addon (`addon.py`)**: A Blender addon that creates a socket server within Blender to receive and execute commands
2. **MCP Server (`src/blender_mcp/server.py`)**: A Python server that implements the Model Context Protocol and connects to the Blender addon

## Architecture & Data Flow

```mermaid
flowchart LR
    subgraph MCP Client
        A[MCP-aware client<br/>(LM Studio, Cursor, Continue)]
    end
    subgraph MCP Server
        B[FastMCP server<br/>(`src/blender_mcp/server.py`)]
    end
    subgraph Blender
        C[Addon socket server<br/>(`addon.py`)]
        D[bpy / scene graph]
    end

    A -- MCP request/response --> B
    B -- JSON over TCP --> C
    C -- bpy API --> D
    D -- results / viewport changes --> A
```

**Interaction summary**

- MCP-compatible clients invoke tools exposed by the FastMCP server. The server relays tool calls as JSON commands over TCP to the Blender addon, which executes them on the main Blender thread.
- Blender scene changes (object creation, material edits, imports) are driven by the addon’s handlers and returned as structured responses to the MCP client.

**Configuration points**

- **Socket target**: `BLENDER_HOST` and `BLENDER_PORT` environment variables (defaults `localhost:9876`) configure where the MCP server sends commands. The same values must be used when starting the addon inside Blender.
- **Addon panel**: The Blender sidebar exposes toggles such as Poly Haven asset fetching and connection controls (see `addon.py` UI operators). Enabling Poly Haven changes which tools the assistant can call.
- **Client launch**: MCP clients should launch the server via `uvx blender-mcp` (see LM Studio/Continue/Cursor sections below). One server instance should be active at a time to avoid port conflicts.

For a quick mental model, start at the MCP client, follow the arrows in the diagram, and open the linked source files to see how each hop works.

## Installation


### Prerequisites

- Blender 3.0 or newer
- Python 3.10 or newer
- uv package manager: 

**If you're on Mac, please install uv as**
```bash
brew install uv
```
**On Windows**
```bash
powershell -c "irm https://astral.sh/uv/install.ps1 | iex" 
```
and then
```bash
set Path=C:\Users\nntra\.local\bin;%Path%
```

Otherwise installation instructions are on their website: [Install uv](https://docs.astral.sh/uv/getting-started/installation/)

**⚠️ Do not proceed before installing UV**

### Environment Variables

The following environment variables can be used to configure the Blender connection:

- `BLENDER_HOST`: Host address for Blender socket server (default: "localhost")
- `BLENDER_PORT`: Port number for Blender socket server (default: 9876)

### Logging configuration

Blender MCP now configures logging from its entrypoint, allowing you to control verbosity and destinations when launching the server from an MCP client:

- `BLENDER_MCP_LOG_LEVEL`: Logging level (e.g., `DEBUG`, `INFO`, `WARNING`).
- `BLENDER_MCP_LOG_FORMAT`: Standard logging format string (defaults to timestamp/name/level/message).
- `BLENDER_MCP_LOG_HANDLER`: `console` (stderr) or `file`.
- `BLENDER_MCP_LOG_FILE`: File path when using the `file` handler (default: `blender_mcp.log`).

Tool calls now return structured error payloads (`{"error": {"code": "runtime_error", "message": "...", "data": {...}}}`) while detailed diagnostics continue to be written to the configured logs.

Example:
```bash
export BLENDER_HOST='host.docker.internal'
export BLENDER_PORT=9876
```

### LM Studio integration

LM Studio (v0.3.0 or newer) ships with native MCP client support, allowing any locally hosted model to call Blender tools directly.

1. Install [LM Studio](https://lmstudio.ai/) and download the model you want to run locally.
2. Open **Settings → Developer → Model Context Protocol (MCP)**.
3. Click **Add MCP server** and configure it with:
   - **Command:** `uvx`
   - **Arguments:** `blender-mcp`
4. Save the configuration and start a chat with your model. A new **Blender MCP** tool tray will appear once the server is running.

If you prefer to edit the JSON configuration manually, create or update the LM Studio MCP config file (located at `~/Library/Application Support/LM Studio/mcpServers.json` on macOS, `%APPDATA%/LM Studio/mcpServers.json` on Windows, or `~/.config/LM Studio/mcpServers.json` on Linux) with:

```json
{
    "mcpServers": {
        "blender": {
            "command": "uvx",
            "args": ["blender-mcp"],
            "env": {}
        }
    }
}
```

Restart LM Studio after saving to load the server definition.

### Ollama integration

Ollama provides the model runtime, while an MCP-aware client such as [Continue](https://continue.dev/) or [Open WebUI](https://github.com/open-webui/open-webui) orchestrates the conversation. A typical setup looks like this:

1. Install [Ollama](https://ollama.com/) and run `ollama pull llama3` (or any other model you prefer).
2. Install the Continue extension for VS Code or the Continue desktop client and choose **Ollama** as the provider for your assistant.
3. In Continue’s settings (`continue.json`), register the Blender MCP server:

   ```jsonc
   {
     "mcpServers": {
       "blender": {
         "command": "uvx",
         "args": ["blender-mcp"]
       }
     }
   }
   ```

4. Start the Continue session, ensure Ollama is running, and request the assistant to use the Blender MCP tools. You can reuse the same configuration with any MCP-compatible client that proxies queries to Ollama.

### Cursor integration

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/install-mcp?name=blender&config=eyJjb21tYW5kIjoidXZ4IGJsZW5kZXItbWNwIn0%3D)

For Mac users, go to Settings > MCP and paste the following 

- To use as a global server, use "add new global MCP server" button and paste
- To use as a project specific server, create `.cursor/mcp.json` in the root of the project and paste


```json
{
    "mcpServers": {
        "blender": {
            "command": "uvx",
            "args": [
                "blender-mcp"
            ]
        }
    }
}
```

For Windows users, go to Settings > MCP > Add Server, add a new server with the following settings:

```json
{
    "mcpServers": {
        "blender": {
            "command": "cmd",
            "args": [
                "/c",
                "uvx",
                "blender-mcp"
            ]
        }
    }
}
```

[Cursor setup video](https://www.youtube.com/watch?v=wgWsJshecac)

**⚠️ Only run one instance of the MCP server at a time within your chosen MCP client**

### Visual Studio Code Integration

_Prerequisites_: Make sure you have [Visual Studio Code](https://code.visualstudio.com/) installed before proceeding.

[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_blender--mcp_server-0098FF?style=flat-square&logo=visualstudiocode&logoColor=ffffff)](vscode:mcp/install?%7B%22name%22%3A%22blender-mcp%22%2C%22type%22%3A%22stdio%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22blender-mcp%22%5D%7D)

### Installing the Blender Addon

1. Download the `addon.py` file from this repo
1. Open Blender
2. Go to Edit > Preferences > Add-ons
3. Click "Install..." and select the `addon.py` file
4. Enable the addon by checking the box next to "Interface: Blender MCP"


## Usage

### Starting the Connection
![BlenderMCP in the sidebar](assets/addon-instructions.png)

1. In Blender, go to the 3D View sidebar (press N if not visible)
2. Find the "BlenderMCP" tab
3. Turn on the Poly Haven checkbox if you want assets from their API (optional)
4. Click "Connect to LLM client"
5. Ensure your MCP client has started the `blender-mcp` server (you can also launch it manually with `uvx blender-mcp` if needed)

### Complete usage walkthrough

Use the steps below the first time you bring everything online or when you are troubleshooting a broken setup. The goal is to ensure Blender, the MCP server, and your chosen client are all pointing at each other correctly.

1. **Prep Blender and the addon**
   - Install and enable `addon.py` (see [Installing the Blender Addon](#installing-the-blender-addon)).
   - Open the **BlenderMCP** tab in the sidebar and keep the panel visible so you can read connection status updates.
2. **Verify host/port alignment**
   - In the Blender panel, check the host and port fields. They default to `localhost` and `9876`.
   - If you need Blender to accept connections from another machine or container, set matching values via the environment variables `BLENDER_HOST` and `BLENDER_PORT` before starting the MCP server (see [Environment Variables](#environment-variables)).
3. **Start the MCP server**
   - Let your MCP-aware client (LM Studio, Continue, Cursor, VS Code, etc.) launch the server automatically **or** start it yourself in a terminal with:
     ```bash
     uvx blender-mcp
     ```
   - Keep the terminal window open; the server logs will report connection attempts and tool calls.
4. **Connect from Blender**
   - In Blender, click **Connect to LLM client**. The status message in the panel should change to connected after a few seconds.
   - If it fails, confirm no other `blender-mcp` server instance is already running and that firewalls allow TCP on the chosen port.
5. **Test round-trip communication**
   - In your MCP client, ask the assistant to “list all objects in the scene.”
   - Blender should respond with object data in the chat, confirming the end-to-end path: MCP client → MCP server → Blender addon → back to client.
6. **Stay within one running server**
   - Only one MCP server instance should be active per machine. If you switch clients, stop the previous server first to avoid port conflicts.

### Practical tips for day-to-day use

- **Keep Blender open**: The addon processes commands on Blender’s main thread, so the Blender window must remain open while you work.
- **Save often**: Tool calls can perform destructive actions (e.g., mass delete). Save versions or enable auto-save to protect work in progress.
- **Prefer small, explicit requests**: Break complex prompts into steps like “create room layout” → “add lighting” → “apply materials” to get predictable results.
- **Inspect tool calls**: Most MCP clients show a tool-call log. Use it to understand what the assistant is sending to Blender and to copy/adjust commands.
- **Refresh Poly Haven and Hyper3D states**: Toggle the relevant checkboxes in the Blender panel if the assistant forgets to fetch assets or exceeds a quota.
- **Run from scripts**: You can invoke `uvx blender-mcp` from your own automation (shell scripts, Makefiles, CI) as long as Blender is running with the addon enabled.

### Using with local LLM clients

Once your MCP client (LM Studio, Continue, Cursor, etc.) is configured and the addon is running inside Blender, the assistant will expose a hammer icon with the Blender MCP tools.

![BlenderMCP in the sidebar](assets/hammer-icon.png)

#### Capabilities

- Get scene and object information 
- Create, delete and modify shapes
- Apply or create materials for objects
- Execute any Python code in Blender
- Download the right models, assets and HDRIs through [Poly Haven](https://polyhaven.com/)
- AI generated 3D models through [Hyper3D Rodin](https://hyper3d.ai/)


### Example Commands

Here are some examples of what you can ask your local assistant to do:

- "Create a low poly scene in a dungeon, with a dragon guarding a pot of gold" [Demo](https://www.youtube.com/watch?v=DqgKuLYUv00)
- "Create a beach vibe using HDRIs, textures, and models like rocks and vegetation from Poly Haven" [Demo](https://www.youtube.com/watch?v=I29rn92gkC4)
- Give a reference image, and create a Blender scene out of it [Demo](https://www.youtube.com/watch?v=FDRb03XPiRo)
- "Generate a 3D model of a garden gnome through Hyper3D"
- "Get information about the current scene, and make a threejs sketch from it" [Demo](https://www.youtube.com/watch?v=jxbNI5L7AH8)
- "Make this car red and metallic" 
- "Create a sphere and place it above the cube"
- "Make the lighting like a studio"
- "Point the camera at the scene, and make it isometric"

## Hyper3D integration

Hyper3D's free trial key allows you to generate a limited number of models per day. If the daily limit is reached, you can wait for the next day's reset or obtain your own key from hyper3d.ai and fal.ai.

## Troubleshooting

- **Connection issues**: Make sure the Blender addon server is running, and the MCP server is configured in your chosen client. Do **not** run the `uvx` command in a terminal if the client already manages the process. Sometimes the first command won't go through but after that it starts working.
- **Timeout errors**: Try simplifying your requests or breaking them into smaller steps
- **Poly Haven integration**: Some assistants are occasionally erratic—remind them to toggle the Poly Haven checkbox or call the status tool again.
- **Have you tried turning it off and on again?**: If you're still having connection errors, try restarting both the MCP client and the Blender server


## Technical Details

### Communication Protocol

The system uses a simple JSON-based protocol over TCP sockets:

- **Commands** are sent as JSON objects with a `type` and optional `params`
- **Responses** are JSON objects with a `status` and `result` or `message`

## Limitations & Security Considerations

- The `execute_blender_code` tool allows running arbitrary Python code in Blender, which can be powerful but potentially dangerous. Use with caution in production environments. ALWAYS save your work before using it.
- Poly Haven requires downloading models, textures, and HDRI images. If you do not want to use it, please turn it off in the checkbox in Blender. 
- Complex operations might need to be broken down into smaller steps


## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This is a third-party integration and not made by Blender. Made by [Siddharth](https://x.com/sidahuj)
