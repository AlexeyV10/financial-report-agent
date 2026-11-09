"""Ollama adapter: only the project's loopback endpoint, no cloud credentials."""
from dataclasses import dataclass
import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .agent import RunFailure, SYSTEM_PROMPT, TOOLS, VERSION

BASE_URL = "http://127.0.0.1:11435"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_json(route, payload=None, timeout=5):
    if route not in {"/api/version", "/api/tags", "/api/show", "/api/chat", "/api/ps"}:
        raise RunFailure("invalid_local_route")
    data = None if payload is None else json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    req = Request(BASE_URL + route, data=data, headers={"Content-Type": "application/json"})
    try:
        # No environment proxy, remote host, redirect, API key or arbitrary URL.
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=timeout) as res:
            body = res.read(262145)
        if len(body) > 262144:
            raise RunFailure("result_too_large")
        return json.loads(body)
    except (TimeoutError, socket.timeout):
        raise RunFailure("timeout") from None
    except (URLError, HTTPError, OSError):
        raise RunFailure("adapter_unavailable") from None
    except (UnicodeError, ValueError):
        raise RunFailure("invalid_result") from None


@dataclass(frozen=True)
class OllamaAdapter:
    model: str
    model_digest: str
    server_version: str

    @property
    def metadata(self):
        return {"kind": "local_llm", "adapter": "ollama-json-dialogue-v4-limits", "model": self.model,
                "model_digest": self.model_digest, "server_version": self.server_version,
                "endpoint": BASE_URL, "think": False, "temperature": 0, "num_ctx": 8192}

    def probe(self, timeout=5):
        if self.model != "qwen3:4b" or len(self.model_digest) != 64 or any(c not in "0123456789abcdef" for c in self.model_digest):
            raise RunFailure("local_model_not_pinned")
        version = local_json("/api/version", timeout=timeout)
        models = local_json("/api/tags", timeout=timeout)
        if version.get("version") != self.server_version:
            raise RunFailure("local_server_version_mismatch")
        selected = [m for m in models.get("models", []) if m.get("name") == self.model]
        if len(selected) != 1 or selected[0].get("digest") != self.model_digest:
            raise RunFailure("local_model_version_mismatch")
        return {"server_version": version["version"], "model": self.model, "digest": self.model_digest}

    def decide(self, observation, timeout_s):
        self.probe(min(5, timeout_s))
        # Restrict IDs in the visible schema as well as in controller validation.
        tools = json.loads(json.dumps(TOOLS))
        tools[0]["function"]["parameters"]["properties"]["top_k"]["maximum"] = observation["limits"]["max_search_results"]
        previous, current = [f["fact_id"] for f in observation["context"]["catalog"]]
        tools[1]["function"]["parameters"]["properties"]["fact_id"]["enum"] = [previous, current]
        props = tools[2]["function"]["parameters"]["properties"]
        props["previous_fact_id"]["enum"], props["current_fact_id"]["enum"] = [previous], [current]
        if observation.get("calculation") is not None:
            tools[3]["function"]["parameters"]["properties"]["result_id"]["enum"] = [observation["calculation"]["result_id"]]
        schema = {"oneOf": [{"type": "object", "properties": {"tool": {"const": t["function"]["name"]},
                     "arguments": t["function"]["parameters"]}, "required": ["tool", "arguments"], "additionalProperties": False}
                    for t in tools]}
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"task": observation["context"], "tool_schemas": schema}, ensure_ascii=False, separators=(",", ":"))}]
        for turn in observation.get("history", []):
            if turn["action"] is not None:
                action = turn["action"]
                messages.append({"role": "assistant", "content": json.dumps({"tool": action["tool"], "arguments": action["arguments"]}, ensure_ascii=False)})
            messages.append({"role": "user", "content": json.dumps({"observed_tool_result": turn["result"]}, ensure_ascii=False)})
        latest = {k: v for k, v in observation.items() if k not in {"context", "history"}}
        messages.append({"role": "user", "content": "Choose ONE next action from the CURRENT state; do not restart. " + json.dumps(latest, ensure_ascii=False, separators=(",", ":"))})
        payload = {"model": self.model, "stream": False, "think": False, "keep_alive": "5m",
                   "messages": messages,
                   "format": schema, "options": {"temperature": 0, "num_ctx": 8192,
                    "num_predict": observation["limits"]["max_output_tokens"]}}
        result = local_json("/api/chat", payload, timeout_s)
        if result.get("model") != self.model or result.get("done") is not True:
            raise RunFailure("invalid_result")
        usage = {"input_tokens": result.get("prompt_eval_count"), "output_tokens": result.get("eval_count")}
        action = None
        try:
            def unique(pairs):
                obj = {}
                for key, value in pairs:
                    if key in obj:
                        raise ValueError("duplicate_json_key")
                    obj[key] = value
                return obj
            call = json.loads(result.get("message", {}).get("content", ""), object_pairs_hook=unique)
            if not isinstance(call, dict) or set(call) != {"tool", "arguments"}:
                raise ValueError("invalid_action")
            action = {"schema_version": VERSION, "context_id": observation["context"]["context_id"],
                      "tool": call["tool"], "arguments": call["arguments"]}
        except (ValueError, TypeError):
            pass
        # Narratives, multiple calls and reasoning are never executed or logged.
        return {"action": action, "usage": usage}
