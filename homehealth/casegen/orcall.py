"""Minimal OpenRouter chat call. Reads key from env OPENROUTER_API_KEY; never prints/saves it."""
import json, os, time, urllib.request, urllib.error
URL = "https://openrouter.ai/api/v1/chat/completions"
def chat(model, system, user, max_tokens, temperature, timeout=1500, extra=None):
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens, "temperature": temperature, "usage": {"include": True}}
    if extra: body.update(extra)
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "Content-Type": "application/json",
        "X-Title": "jevfly-casegen-bakeoff"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: resp = json.loads(r.read())
        err = None
    except urllib.error.HTTPError as e:
        resp = {"error_body": e.read().decode(errors="replace")[:2000]}; err = f"HTTP {e.code}"
    except Exception as e:
        resp = {}; err = repr(e)[:300]
    lat = round(time.time() - t0, 1)
    ch = (resp.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    u = resp.get("usage") or {}
    return {"model": model, "resolved_model": resp.get("model"), "provider": resp.get("provider"), "error": err,
            "latency_s": lat, "finish_reason": ch.get("finish_reason"), "native_finish_reason": ch.get("native_finish_reason"),
            "content": msg.get("content") or "", "has_reasoning": bool(msg.get("reasoning")),
            "usage": {"prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
                      "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                      "cost_usd": u.get("cost")}, "raw_error": resp.get("error") or resp.get("error_body")}

def parse_json(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"): t = t.rstrip()[:-3]
    try: return json.loads(t), "strict" if t == text.strip() else "fenced"
    except Exception: pass
    i, j = t.find("{"), t.rfind("}")
    if i >= 0 and j > i:
        try: return json.loads(t[i:j+1]), "extracted"
        except Exception: pass
    return None, "invalid"
