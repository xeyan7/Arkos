"""Local NDJSON transport for the unmodified Arkos AIAgent engine.

One process owns one conversation, so prompt caches and working directories are
never shared across unrelated desktop sessions. stdout is reserved for IPC.
"""
import argparse
import json
import os
import sys
import threading


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--config-home")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    os.environ["ARKOS_HOME"] = os.path.abspath(args.home)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    sys.path.insert(0, os.path.abspath(args.engine))
    protocol = sys.stdout
    sys.stdout = sys.stderr
    lock = threading.Lock()

    def emit(value):
        with lock:
            protocol.write(json.dumps(value, ensure_ascii=True, default=str) + "\n")
            protocol.flush()

    try:
        from run_agent import AIAgent
        from arkos_cli.config import load_config_readonly
        from arkos_cli.runtime_provider import resolve_runtime_provider
    except Exception as exc:
        emit({"event": "fatal", "message": str(exc)})
        return 1
    if args.probe:
        emit({"event": "ready", "engine": "AIAgent", "python": sys.version.split()[0]})
        return 0

    agent = None
    history = []
    worker = None
    current_turn = None

    def run_turn(request):
        nonlocal agent, history
        turn_id = request["turnId"]
        streamed = []

        def delta(text):
            if text:
                streamed.append(str(text))
                emit({"event": "delta", "turnId": turn_id, "text": str(text)})

        try:
            if agent is None:
                # Resolve the owner's configured provider without moving conversation state
                # out of Electron userData. Credentials never cross the IPC boundary.
                try:
                    if args.config_home:
                        os.environ["ARKOS_HOME"] = os.path.abspath(args.config_home)
                        from dotenv import load_dotenv
                        load_dotenv(os.path.join(args.config_home, ".env"), override=False)
                    config = load_config_readonly()
                    model_config = config.get("model", {})
                    if isinstance(model_config, str):
                        model_config = {"default": model_config}
                    model = model_config.get("default", "")
                    runtime = resolve_runtime_provider(
                        requested=model_config.get("provider"), target_model=model or None
                    )
                finally:
                    os.environ["ARKOS_HOME"] = os.path.abspath(args.home)
                keys = ("provider", "api_key", "base_url", "api_mode", "acp_command", "acp_args")
                agent = AIAgent(
                    **{key: runtime[key] for key in keys if runtime.get(key) is not None},
                    model=model, session_id=args.session, platform="gui", quiet_mode=True,
                    skip_background_review=True,
                )
            result = agent.run_conversation(
                request["input"], conversation_history=history, stream_callback=delta
            )
            history = result.get("messages", history)
            final = result.get("final_response") or ""
            if not streamed and final:
                delta(final)
            emit({"event": "completed", "turnId": turn_id,
                  "text": final, "error": result.get("error"),
                  "interrupted": bool(result.get("interrupted"))})
        except Exception as exc:
            emit({"event": "completed", "turnId": turn_id, "error": str(exc)})

    emit({"event": "ready", "engine": "AIAgent"})
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                method = request.get("method")
                if method == "turn":
                    if worker and worker.is_alive():
                        emit({"event": "rejected", "message": "A turn is already running"})
                        continue
                    current_turn = request["turnId"]
                    worker = threading.Thread(target=run_turn, args=(request,), daemon=True)
                    worker.start()
                elif method == "interrupt":
                    if agent is not None:
                        agent.interrupt()
                elif method == "shutdown":
                    break
                else:
                    emit({"event": "rejected", "message": "Unknown bridge method"})
            except Exception as exc:
                emit({"event": "rejected", "turnId": current_turn, "message": str(exc)})
    finally:
        if agent is not None and worker and worker.is_alive():
            agent.interrupt()
            worker.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
