#!/usr/bin/env python3
"""inference.py — Baseline inference script for the Customer Support OpenEnv.

Runs three tasks (create-ticket → resolve-ticket → full-workflow) using an
OpenAI-compatible LLM, emitting the mandatory [START] / [STEP] / [END] log
lines to stdout.

Environment variables
─────────────────────
  API_BASE_URL   LLM inference endpoint  (default: HuggingFace router)
  MODEL_NAME     Model identifier        (default: Qwen/Qwen2.5-72B-Instruct)
  HF_TOKEN       API key / HF token      (required for hosted inference)
  SERVER_URL     OpenEnv server base URL (default: http://localhost:7860)
  TASK           Run a single task instead of all three (optional)

Usage
─────
  # 1. Start the server (separate terminal or background):
  #    uvicorn app.main:app --host 0.0.0.0 --port 7860
  #
  # 2. Run inference:
  #    python inference.py
"""
import json
import os
import subprocess
import sys
import textwrap
import time
from typing import Any, Optional

import httpx
from openai import OpenAI

# ── Configuration ──────────────────────────────────────────────────────────────
API_KEY: str = os.getenv("HF_TOKEN") or os.getenv("API_KEY") or "dummy-key"
API_BASE_URL: str = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME: str = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
SERVER_URL: str = os.getenv("SERVER_URL", "http://localhost:7860").rstrip("/")
BENCHMARK: str = "customer-support-env"
SINGLE_TASK: Optional[str] = os.getenv("TASK")  # optional: run just one task

TASKS: list[str] = ["create-ticket", "resolve-ticket", "full-workflow"]
MAX_STEPS: dict[str, int] = {
    "create-ticket":  10,
    "resolve-ticket": 15,
    "full-workflow":  20,
}
SUCCESS_THRESHOLD: float = 0.5
TEMPERATURE: float = 0.3
MAX_TOKENS: int = 300

# ── Logging helpers (mandatory stdout format) ──────────────────────────────────

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(
    step: int,
    action: str,
    reward: float,
    done: bool,
    error: Optional[str],
) -> None:
    err = error if error else "null"
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f}"
        f" done={str(done).lower()} error={err}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: list[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps}"
        f" score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


# ── Action formatting ──────────────────────────────────────────────────────────

def _fmt_action(action_dict: dict[str, Any]) -> str:
    """Return a compact single-line string representation of the action."""
    atype = action_dict.get("action_type", "unknown")
    parts = [f"{k}={json.dumps(v)}" for k, v in action_dict.items() if k != "action_type" and v is not None]
    inner = ", ".join(parts)
    return f"{atype}({inner})" if inner else atype


# ── LLM interaction ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = textwrap.dedent("""
    You are an AI agent operating a customer-support ticket system.
    At each step you must respond with exactly one JSON action object — no extra text,
    no markdown fences, no explanations.

    Available action_types and their fields:
      create_ticket   – title (str), description (str), priority (low|medium|high|urgent), category (str)
      add_comment     – ticket_id (int), body (str)
      update_status   – ticket_id (int), status (in_progress|resolved|closed)
      search_kb       – query (str)
      link_article    – ticket_id (int), article_id (int)
      noop            – (no extra fields)

    Respond with ONLY a raw JSON object such as:
    {"action_type": "create_ticket", "title": "...", "description": "...", "priority": "high", "category": "billing"}
""").strip()


def _build_user_prompt(obs: dict[str, Any]) -> str:
    state_str = json.dumps(obs.get("state", {}), indent=2)
    available = "\n  ".join(obs.get("available_actions", []))
    last = obs.get("last_action_result") or "none"
    return textwrap.dedent(f"""
        Task: {obs.get('task')}
        Step: {obs.get('step')}
        Instructions: {obs.get('instructions')}

        Last action result: {last}

        Available actions:
          {available}

        Current state:
        {state_str}

        What is your next action? Reply with a single JSON object.
    """).strip()


def _get_llm_action(client: OpenAI, obs: dict[str, Any]) -> dict[str, Any]:
    """Ask the LLM for the next action. Falls back to noop on failure."""
    user_prompt = _build_user_prompt(obs)
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        raw = (completion.choices[0].message.content or "").strip()
        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = "\n".join(
                line for line in raw.splitlines()
                if not line.strip().startswith("```")
            ).strip()
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        print(f"[DEBUG] LLM call failed: {exc}", flush=True)
        return {"action_type": "noop"}


# ── Server management ──────────────────────────────────────────────────────────

def _server_ready(http: httpx.Client) -> bool:
    try:
        r = http.get(f"{SERVER_URL}/health", timeout=3.0)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _start_local_server() -> Optional[subprocess.Popen]:  # type: ignore[type-arg]
    """Start uvicorn in the background if the server is not already running."""
    proc = subprocess.Popen(  # noqa: S603, S607
        ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


# ── Episode runner ─────────────────────────────────────────────────────────────

def run_task(client: OpenAI, http: httpx.Client, task: str) -> float:
    """Run a single task episode. Returns the episode score in [0, 1]."""
    max_steps = MAX_STEPS.get(task, 10)
    rewards: list[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    log_start(task=task, env=BENCHMARK, model=MODEL_NAME)

    try:
        resp = http.post(f"{SERVER_URL}/reset", json={"task": task}, timeout=30.0)
        resp.raise_for_status()
        obs: dict[str, Any] = resp.json()

        for step in range(1, max_steps + 1):
            if obs.get("done", False):
                break

            action_dict = _get_llm_action(client, obs)
            action_str = _fmt_action(action_dict)

            try:
                step_resp = http.post(
                    f"{SERVER_URL}/step",
                    json={"action": action_dict},
                    timeout=30.0,
                )
                step_resp.raise_for_status()
                result: dict[str, Any] = step_resp.json()
            except Exception as exc:  # noqa: BLE001
                log_step(step, action_str, 0.0, True, str(exc))
                steps_taken = step
                break

            reward = float(result.get("reward", 0.0))
            done = bool(result.get("done", False))
            error = result.get("error")

            rewards.append(reward)
            steps_taken = step
            obs = result.get("observation", obs)

            log_step(step=step, action=action_str, reward=reward, done=done, error=error)

            if done:
                break

        # Episode score: cumulative reward clamped to [0, 1]
        score = min(max(sum(rewards), 0.0), 1.0)
        success = score >= SUCCESS_THRESHOLD

    except Exception as exc:  # noqa: BLE001
        print(f"[DEBUG] Episode error: {exc}", flush=True)

    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

    return score


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    server_proc: Optional[subprocess.Popen] = None  # type: ignore[type-arg]
    with httpx.Client() as http:
        # Start server if needed
        if not _server_ready(http):
            print("[DEBUG] Server not reachable — starting local uvicorn ...", flush=True)
            server_proc = _start_local_server()
            for _ in range(30):
                time.sleep(1)
                if _server_ready(http):
                    print("[DEBUG] Server ready.", flush=True)
                    break
            else:
                print("[DEBUG] Server failed to start. Exiting.", flush=True)
                if server_proc:
                    server_proc.terminate()
                sys.exit(1)

        tasks_to_run = [SINGLE_TASK] if SINGLE_TASK else TASKS
        scores: dict[str, float] = {}
        try:
            for task in tasks_to_run:
                scores[task] = run_task(client, http, task)
        finally:
            if server_proc:
                server_proc.terminate()
                server_proc.wait()

    print(
        f"\n[SUMMARY] scores: "
        + ", ".join(f"{t}={s:.3f}" for t, s in scores.items()),
        flush=True,
    )


if __name__ == "__main__":
    main()
