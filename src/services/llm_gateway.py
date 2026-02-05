"""
LLM Gateway Service - Unified interface for LLM API calls with retry, caching, and model tiering
"""
import json
import hashlib
import time
from typing import Optional, Dict, Any, List
from enum import Enum
import asyncio
from functools import wraps

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from anthropic import AsyncAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class ModelTier(str, Enum):
    """Model tier for selecting appropriate LLM based on task complexity"""
    FAST = "fast"  # Lightweight tasks, use cheaper/faster models
    STANDARD = "standard"  # Standard complexity tasks
    ADVANCED = "advanced"  # Complex reasoning, use most capable models


class LLMProvider(str, Enum):
    """Supported LLM providers"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class LLMGateway:
    """
    Unified gateway for all LLM API calls.
    Handles authentication, retry logic, caching, and model selection.
    """

    def __init__(
        self,
        provider: LLMProvider = LLMProvider.OPENAI,
        api_key: Optional[str] = None,
        enable_cache: bool = True,
        max_retries: int = 3,
        timeout: int = 120
    ):
        self.provider = provider
        self.enable_cache = enable_cache
        self.max_retries = max_retries
        self.timeout = timeout
        self._cache: Dict[str, Any] = {}

        # Initialize the appropriate client
        if provider == LLMProvider.OPENAI:
            if not OPENAI_AVAILABLE:
                raise ImportError("OpenAI package not installed. Run: pip install openai")
            self.client = AsyncOpenAI(api_key=api_key, timeout=timeout)
        elif provider == LLMProvider.ANTHROPIC:
            if not ANTHROPIC_AVAILABLE:
                raise ImportError("Anthropic package not installed. Run: pip install anthropic")
            self.client = AsyncAnthropic(api_key=api_key, timeout=timeout)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        # Model mapping based on tier
        self.model_mapping = self._get_model_mapping()

    def _get_model_mapping(self) -> Dict[ModelTier, str]:
        """Get model names based on provider and tier"""
        if self.provider == LLMProvider.OPENAI:
            return {
                ModelTier.FAST: "gpt-4.1-mini",
                ModelTier.STANDARD: "gpt-4o",
                ModelTier.ADVANCED: "gpt-4-turbo"
            }
        elif self.provider == LLMProvider.ANTHROPIC:
            return {
                ModelTier.FAST: "claude-3-haiku-20240307",
                ModelTier.STANDARD: "claude-3-5-sonnet-20241022",
                ModelTier.ADVANCED: "claude-3-opus-20240229"
            }
        return {}

    def _get_cache_key(self, messages: List[Dict], model: str, temperature: float) -> str:
        """Generate cache key from request parameters"""
        content = json.dumps({
            "messages": messages,
            "model": model,
            "temperature": temperature
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    async def call_with_retry(
        self,
        messages: List[Dict[str, str]],
        model_tier: ModelTier = ModelTier.STANDARD,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Call LLM with exponential backoff retry logic.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model_tier: Complexity tier for model selection
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens in response
            response_format: Optional response format specification (e.g., {"type": "json_object"})
            **kwargs: Additional provider-specific parameters

        Returns:
            Dict containing response text and metadata
        """
        model = self.model_mapping.get(model_tier, "gpt-4o")

        # Check cache first
        if self.enable_cache:
            cache_key = self._get_cache_key(messages, model, temperature)
            if cache_key in self._cache:
                cached_result = self._cache[cache_key]
                cached_result["from_cache"] = True
                return cached_result

        # Retry logic with exponential backoff
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                result = await self._call_llm(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    **kwargs
                )

                # Cache successful result
                if self.enable_cache:
                    self._cache[cache_key] = result

                return result

            except Exception as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    # Exponential backoff: 2s, 4s, 8s
                    wait_time = 2 ** (attempt + 1)
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Max retries exceeded
                    raise RuntimeError(
                        f"LLM call failed after {self.max_retries} attempts: {str(last_exception)}"
                    )

    async def _call_llm(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        response_format: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Internal method to make actual LLM API call"""
        start_time = time.time()

        if self.provider == LLMProvider.OPENAI:
            call_params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }
            if response_format:
                call_params["response_format"] = response_format

            response = await self.client.chat.completions.create(**call_params)

            return {
                "content": response.choices[0].message.content,
                "model": response.model,
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
                "latency_seconds": time.time() - start_time,
                "from_cache": False
            }

        elif self.provider == LLMProvider.ANTHROPIC:
            # Convert messages format for Anthropic
            system_message = None
            user_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_message = msg["content"]
                else:
                    user_messages.append({"role": msg["role"], "content": msg["content"]})

            call_params = {
                "model": model,
                "messages": user_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }
            if system_message:
                call_params["system"] = system_message

            response = await self.client.messages.create(**call_params)

            return {
                "content": response.content[0].text,
                "model": response.model,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "latency_seconds": time.time() - start_time,
                "from_cache": False
            }

        raise ValueError(f"Unsupported provider: {self.provider}")

    async def call_with_json_response(
        self,
        messages: List[Dict[str, str]],
        model_tier: ModelTier = ModelTier.STANDARD,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Call LLM and parse JSON response.

        Returns:
            Dict containing parsed JSON from response and metadata
        """
        if self.provider == LLMProvider.OPENAI:
            # OpenAI supports json_object response format
            result = await self.call_with_retry(
                messages=messages,
                model_tier=model_tier,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                **kwargs
            )
        else:
            # For other providers, instruct in prompt
            messages = messages.copy()
            if messages and messages[0]["role"] == "system":
                messages[0]["content"] += "\n\nYou must respond with valid JSON only."
            else:
                messages.insert(0, {"role": "system", "content": "You must respond with valid JSON only."})

            result = await self.call_with_retry(
                messages=messages,
                model_tier=model_tier,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

        # Parse JSON from content
        try:
            parsed_content = json.loads(result["content"])
            result["parsed_json"] = parsed_content
            return result
        except json.JSONDecodeError as e:
            # Attempt to extract JSON from markdown code block
            content = result["content"]
            if "```json" in content:
                try:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                    parsed_content = json.loads(json_str)
                    result["parsed_json"] = parsed_content
                    return result
                except (IndexError, json.JSONDecodeError):
                    pass

            raise ValueError(f"Failed to parse JSON from LLM response: {str(e)}\nContent: {content[:500]}")

    def clear_cache(self):
        """Clear the response cache"""
        self._cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        return {
            "cache_size": len(self._cache),
            "cache_enabled": self.enable_cache
        }
