#!/usr/bin/env python3
"""One-shot OpenHands worker spawn (the openhands host's "claude -p" equivalent).

The OpenHands SDK has no single-shot CLI: spawning a worker is a small Python
program. This runner is that program, parameterized by env vars so hosts/*.json
can express it as a command (HOST-ADAPTER.md spawn-with-model):

    OH_RUNNER=tools/openhands_run.py \
    OH_MODEL=openrouter/deepseek/deepseek-v4-flash-0731 \   # LiteLLM id
    OH_BASE_URL=https://openrouter.ai/api/v1 \
    OH_WORKSPACE=/path/to/project \
    OH_PROMPT="$(cat prompt.md)" \
    python ~/.venvs/openhands/bin/python   # or any python with openhands-sdk

Writes ONE JSON object to stdout shaped like the claude -p --output-format json
result, so tools/host.py usage parses both the same way:

    {"type": "result", "is_error": false, "subtype": "...",
     "result": "<final agent text>",
     "session_id": "...", "duration_ms": N,
     "usage": {"input_tokens": N, "output_tokens": N}}

Exit codes: 0 ok, 3 agent ran but errored, 4 config error.
"""
import os
import sys
import time


def main():
    prompt = os.environ.get("OH_PROMPT")
    if not prompt and os.environ.get("OH_PROMPT_FILE"):
        with open(os.environ["OH_PROMPT_FILE"], encoding="utf-8") as f:
            prompt = f.read()
    model = os.environ.get("OH_MODEL")
    api_key = os.environ.get("OH_API_KEY") or os.environ.get("LLM_API_KEY")
    base_url = os.environ.get("OH_BASE_URL") or None
    workspace = os.environ.get("OH_WORKSPACE") or os.getcwd()
    if not prompt:
        print("openhands_run: OH_PROMPT is required", file=sys.stderr)
        return 4
    if not model:
        print("openhands_run: OH_MODEL is required (LiteLLM id, e.g. "
              "openrouter/deepseek/deepseek-v4-flash-0731)", file=sys.stderr)
        return 4
    if not api_key:
        print("openhands_run: no API key (set OH_API_KEY or LLM_API_KEY)",
              file=sys.stderr)
        return 4

    try:
        from pydantic import SecretStr
        from openhands.sdk import LLM, Agent, Conversation, Tool
        from openhands.tools.terminal import TerminalTool
        from openhands.tools.file_editor import FileEditorTool
    except ImportError as err:
        print("openhands_run: openhands-sdk not installed in this python "
              "(pip install openhands-sdk openhands-tools): %s" % err,
              file=sys.stderr)
        return 4

    started = time.monotonic()
    llm = LLM(model=model, api_key=SecretStr(api_key), base_url=base_url,
              usage_id="pmos-worker")
    agent = Agent(llm=llm, tools=[Tool(name=TerminalTool.name),
                                  Tool(name=FileEditorTool.name)])
    conversation = Conversation(agent=agent, workspace=os.path.abspath(workspace))
    conversation.send_message(prompt)

    status, result_text = "ok", ""
    try:
        conversation.run()
        # final agent text: last agent MessageEvent whose role is assistant.
        # MessageEvent carries .llm_message (role/content), not .message.
        for ev in reversed(list(getattr(conversation.state, "events", []) or [])):
            if type(ev).__name__ != "MessageEvent":
                continue
            lm = getattr(ev, "llm_message", None)
            if getattr(lm, "role", "") != "assistant":
                continue
            texts = [getattr(c, "text", "") for c in
                     (getattr(lm, "content", None) or [])]
            result_text = "\n".join(t for t in texts if t).strip()
            break
        if not result_text:
            result_text = "(agent finished without a final text message)"
    except Exception as err:  # noqa: BLE001 - report, don't crash the shim
        status, result_text = "failed", str(err)
    if len(result_text) > 4000:
        print("openhands_run: final report truncated %d -> 4000 chars"
              % len(result_text), file=sys.stderr)

    metrics = llm.metrics
    usage_obj = getattr(metrics, "accumulated_token_usage", None) if metrics else None
    out = {
        "type": "result",
        "is_error": status != "ok",
        "subtype": "openhands_sdk",
        "result": result_text[:4000],
        "session_id": str(getattr(conversation, "id", "") or ""),
        "duration_ms": int((time.monotonic() - started) * 1000),
        "usage": {
            "input_tokens": getattr(usage_obj, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(usage_obj, "completion_tokens", 0) or 0,
        },
        "cost_usd": getattr(metrics, "accumulated_cost", None) if metrics else None,
    }
    import json as _json
    sys.stdout.write(_json.dumps(out))
    return 0 if status == "ok" else 3


if __name__ == "__main__":
    sys.exit(main())
