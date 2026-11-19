"""OpenAI-compatible DeepSeek transport for the existing agent message format."""

import os


class DeepSeekRequestError(RuntimeError):
    def __init__(self, status_code: int | None, description: str):
        message = f"DeepSeek HTTP {status_code}: {description}" if status_code else f"DeepSeek: {description}"
        super().__init__(message)
        self.status_code = status_code


class DeepSeekClient:
    def __init__(self, *, model: str, temperature: float, max_tokens: int, api_key: str):
        from langchain_openai import ChatOpenAI

        if not 1 <= max_tokens <= 393_216:
            raise ValueError("DEEPSEEK_MAX_TOKENS must be between 1 and 393216.")
        self.max_tokens = max_tokens
        self.client = ChatOpenAI(
            model=model,
            temperature=temperature,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            api_key=api_key,
            extra_body={"thinking": {"type": "disabled"}, "max_tokens": max_tokens},
            use_responses_api=False,
            max_retries=0,
            timeout=90,
        )

    def __getattr__(self, name):
        return getattr(self.client, name)

    def invoke(self, *args, **kwargs):
        from openai import APIConnectionError, APIStatusError
        from agents.benchmark_usage import active_usage

        meter = active_usage()
        request = meter.reserve(self.max_tokens) if meter else None
        try:
            response = self.client.invoke(*args, **kwargs)
        except APIStatusError as error:
            if meter and error.status_code in {400, 401, 402, 403, 404, 422, 429}:
                meter.reject(request)
            description = {
                400: "request parameters rejected",
                401: "authentication rejected",
                402: "insufficient balance",
                403: "access forbidden",
                404: "model or endpoint unavailable",
                422: "request parameters rejected",
                429: "rate limit exceeded",
            }.get(error.status_code, "request failed")
            raise DeepSeekRequestError(error.status_code, description) from None
        except APIConnectionError:
            raise DeepSeekRequestError(None, "connection failed or timed out") from None
        if meter:
            meter.settle(request, response.response_metadata.get("token_usage") or {}, response.usage_metadata or {})
        return response
