# Execution and approval settings

## Provider configuration

Set a primary provider and its model ID in the ignored `.env` file. Restart the dashboard or API after changing settings. A missing model is rejected locally. The application reports an unavailable model with the setting to update when the provider rejects it.

DeepSeek example:

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TEMPERATURE=0.2
DEEPSEEK_MAX_TOKENS=4096
DEEPSEEK_API_KEY=
```

Groq example:

```dotenv
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-20b
GROQ_TEMPERATURE=0.2
GROQ_MAX_TOKENS=4096
GROQ_API_KEY=
```

Fill in the chosen API key. To configure a fallback, set `FALLBACK_LLM_PROVIDER` and the matching key and model variables in `.env.example`.

## Patch execution

Build the local sandbox image once and run Streamlit or the webhook on the Docker host.

```sh
docker build -t incident-execution-sandbox:local sandbox
```

Docker is the default. Every attempt copies the project into a new temporary workspace. The snapshot skips symlinks, hidden files, local incident state, and benchmark artifacts. Candidate code runs as UID/GID 65532 with no network, a read-only root, dropped capabilities, and one writable bind mount for the disposable workspace. The process has a one-CPU limit, 256 MiB of memory, 64 PIDs, and a 30-second test deadline. The image needs any test dependencies installed at build time. Runtime pulls are disabled.

If Docker is unavailable, execution fails with a Docker setup error. The development fallback is selected explicitly with `SANDBOX_MODE=subprocess`. It still uses a fresh copy, a reduced environment, and a 30-second test deadline. It can access host files and the network. Use it only for trusted patches. The dashboard shows a banner while it is active.

A pre-existing `.env` can override the Docker default. Remove the override or set `SANDBOX_MODE=docker` to use Docker. The shipped Compose services omit daemon access. Run the controller on the Docker host for isolated execution. A containerized controller would need an explicitly configured daemon and a workspace path visible at the same absolute path to that daemon.

## Resume a pending review

The Streamlit approval screen shows a run ID. Keep it private and save it before leaving the screen. After a restart, paste it into **Resume a pending approval** on the input page. SQLite restores the exact patch revision, incident state, and agent progress at the approval gate. Approval and cancellation claim that revision once. A successful regeneration replaces the saved revision.

Set `HITL_DB_PATH` to a persistent local SQLite file. The default is `./hitl.db`. Compose stores it under the application data volume. The database contains incident logs, complaints, and source excerpts. Limit access to its filesystem location and to the dashboard. A run ID is a bearer reference within the dashboard.

The checkpoint covers the boundary between diagnosis and execution. A restart during an active graph interrupts that phase. The webhook runs as a single graph without a dashboard approval gate.
