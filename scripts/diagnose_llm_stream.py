#!/usr/bin/env python3
"""Measure where the first streamed LLM token is delayed.

Run from the repository root with the same environment as the web server:

    .venv/bin/python scripts/diagnose_llm_stream.py \
      --topic '2090年的机器人杀手回到2026年刺杀一个年轻的学生'

This prints every raw SSE message, including reasoning/content fields, but
never prints the API key.
"""
from __future__ import print_function

import argparse
from datetime import datetime
import time

from storyteller.core.config import Config
from storyteller.core.story_generator import DEFAULT_SYSTEM_PROMPT, StoryGenerator
from storyteller.providers.volcengine.llm import VolcengineLLM, _content_from_sse_line


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument(
        "--chunk-size", type=int, default=1,
        help="requests.iter_lines buffer size; use 1 to minimize client buffering",
    )
    args = parser.parse_args()

    config = Config.from_env()
    llm = VolcengineLLM(config)
    messages = [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": StoryGenerator(llm)._build_user_prompt(
                args.topic, "medium", "simple"
            ),
        },
    ]
    body = {
        "model": llm.model,
        "messages": messages,
        "temperature": args.temperature,
        "stream": True,
        "thinking": {"type": "disabled"},
    }
    if args.max_tokens is not None:
        body["max_tokens"] = args.max_tokens

    url = "{}/chat/completions".format(llm.endpoint)
    headers = {
        "Authorization": "Bearer {}".format(llm.api_key),
        "Content-Type": "application/json",
    }

    request_started = time.perf_counter()
    response = llm._session.post(
        url, headers=headers, json=body, stream=True, timeout=60
    )
    headers_received = time.perf_counter()
    try:
        response.raise_for_status()
        first_line_at = None
        first_content_at = None
        first_line = None
        first_content = None
        for line in response.iter_lines(
            chunk_size=args.chunk_size, decode_unicode=False
        ):
            if not line:
                continue
            received_at = time.perf_counter()
            display_line = (
                line.decode("utf-8", errors="replace")
                if isinstance(line, bytes) else str(line)
            )
            print(
                "[{} +{} ms] SSE message: {}".format(
                    datetime.now().astimezone().isoformat(timespec="milliseconds"),
                    _ms(received_at - request_started),
                    display_line,
                ),
                flush=True,
            )
            if first_line_at is None:
                first_line_at = received_at
                first_line = line
            content = _content_from_sse_line(line)
            if content:
                if first_content_at is None:
                    first_content_at = received_at
                    first_content = content
            if display_line.strip() == "data: [DONE]":
                break
        print("model={}".format(llm.model))
        print("endpoint={}".format(url))
        print("http_headers_ms={}".format(_ms(headers_received - request_started)))
        print("first_sse_line_ms={}".format(
            _ms(first_line_at - request_started) if first_line_at else "NOT_RECEIVED"
        ))
        print("first_content_ms={}".format(
            _ms(first_content_at - request_started)
            if first_content_at else "NOT_RECEIVED"
        ))
        if first_line is not None:
            print("first_sse_line_bytes={}".format(len(first_line)))
        if first_content is not None:
            print("first_content_chars={}".format(len(first_content)))
    finally:
        response.close()


def _ms(seconds):
    return int(seconds * 1000)


if __name__ == "__main__":
    main()
