import json.decoder
import requests
import os

import openai
from utils.enums import LLM
import time


def init_chatgpt(OPENAI_API_KEY, OPENAI_GROUP_ID, model, OPENAI_API_BASE=""):
    # if model == LLM.TONG_YI_QIAN_WEN:
    #     import dashscope
    #     dashscope.api_key = OPENAI_API_KEY
    # else:
    #     openai.api_key = OPENAI_API_KEY
    #     openai.organization = OPENAI_GROUP_ID
    openai.api_key = OPENAI_API_KEY
    openai.organization = OPENAI_GROUP_ID
    if OPENAI_API_BASE:
        openai.api_base = OPENAI_API_BASE


def ask_completion(model, batch, temperature):
    response = openai.Completion.create(
        model=model,
        prompt=batch,
        temperature=temperature,
        max_tokens=200,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        stop=[";"]
    )
    response_clean = [_["text"] for _ in response["choices"]]
    return dict(
        response=response_clean,
        **response["usage"]
    )


def ask_chat(model, messages: list, temperature, n):
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=200,
        n=n
    )
    response_clean = [choice["message"]["content"] for choice in response["choices"]]
    if n == 1:
        response_clean = response_clean[0]
    return dict(
        response=response_clean,
        **response["usage"]
    )


def ask_llm(model: str, batch: list, temperature: float, n:int):
    n_repeat = 0
    while True:
        try:
            if model in LLM.TASK_COMPLETIONS:
                # TODO: self-consistency in this mode
                assert n == 1
                response = ask_completion(model, batch, temperature)
            elif model in LLM.TASK_CHAT:
                # batch size must be 1
                assert len(batch) == 1, "batch must be 1 in this mode"
                messages = [{"role": "user", "content": batch[0]}]
                response = ask_chat(model, messages, temperature, n)
                response['response'] = [response['response']]
            elif model in LLM.TASK_OLLAMA:
                # Ollama generate API: POST either /api/generate or /v1/generate {model, prompt, options}
                assert len(batch) == 1, "batch must be 1 in this mode"
                # Prefer openai.api_base if set (init_chatgpt sets it), otherwise use env var OLLAMA_BASE_URL
                base_from_openai = getattr(openai, 'api_base', None)
                base = base_from_openai or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
                # normalize base (remove trailing slash)
                base = base.rstrip('/')

                # Try candidate endpoints in order. Some Ollama versions expose /api/generate, others use /v1/generate
                candidate_paths = ["/api/generate", "/v1/generate", "/generate"]

                prompt = batch[0]
                all_completions = []
                total_tokens = 0
                last_exc = None

                for path in candidate_paths:
                    url = base + path
                    try:
                        for _ in range(max(1, n)):
                            r = requests.post(url, json={
                                "model": model,
                                "prompt": prompt,
                                "options": {
                                    "temperature": temperature,
                                    "stop": [";"]
                                },
                                "stream": False
                            }, timeout=600)
                            r.raise_for_status()
                            data = r.json()
                            completion = data.get("response", "")
                            all_completions.append(completion)
                            total_tokens += int(data.get("eval_count", 0)) + int(data.get("prompt_eval_count", 0))
                        # if we reach here, this endpoint worked
                        # print a small debug message and break
                        print(f"Using Ollama endpoint: {url}")
                        last_exc = None
                        break
                    except requests.HTTPError as he:
                        # try next candidate if 404 or similar
                        last_exc = he
                        # continue to next candidate endpoint
                        continue
                    except requests.RequestException as rexc:
                        last_exc = rexc
                        continue

                if last_exc is not None and not all_completions:
                    # if none of the endpoints worked, raise the last exception to be handled below
                    raise last_exc

                response = {
                    "response": all_completions,
                    "total_tokens": total_tokens
                }
            break
        except openai.error.RateLimitError:
            n_repeat += 1
            print(f"Repeat for the {n_repeat} times for RateLimitError", end="\n")
            time.sleep(1)
            continue
        except json.decoder.JSONDecodeError:
            n_repeat += 1
            print(f"Repeat for the {n_repeat} times for JSONDecodeError", end="\n")
            time.sleep(1)
            continue
        except requests.RequestException as e:
            n_repeat += 1
            print(f"Repeat for the {n_repeat} times for Ollama error: {e}", end="\n")
            time.sleep(1)
            continue
        except Exception as e:
            n_repeat += 1
            print(f"Repeat for the {n_repeat} times for exception: {e}", end="\n")
            time.sleep(1)
            continue

    return response

