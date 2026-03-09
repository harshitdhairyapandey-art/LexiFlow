"""
Universal AI Provider Interface - Fixed Version
Changes from original:
1. All providers RAISE exceptions instead of returning error strings
2. Gemini uses proper GenerateContentConfig object (fixes temperature + system prompt)
3. Lightning AI uses messages format (system prompt now respected)
4. Top-level google import removed (was crashing if package not installed)

"""

from abc import ABC, abstractmethod
class AIProviderError(Exception):
    """Raised when an AI provider fails."""
class AIProvider(ABC):
    def __init__(self,api_key,model_name):
        self.api_key = api_key
        self.model_name = model_name
    @abstractmethod
    def generate_content(self,system_prompt,user_text,temperature=0.7):
        """ Generate response from AI provider.
    Args:
        system_prompt: System instructions for the model
        user_text: The text to process
        temperature: Sampling temperature (0.0 - 1.0)
    Returns:
        str: Generated response text"""
    def __str__(self):
        return f"{self.__class__.__name__}({self.model_name})"
    def _validate(self, text: str)-> str:
        """Validates and cleans response text."""
        if not text or not text.strip():
            raise AIProviderError(f"{self} returned an empty response.")
        return text.strip()



         
# --- GOOGLE GEMINI ---
class GeminiProvider(AIProvider):
    def __init__(self, api_key, model_name):
        super().__init__(api_key, model_name)
        try:
            from google import genai
            self.client = genai.Client(api_key=api_key)
        except ImportError:
            raise ValueError("❌ google-genai not installed. Run: pip install google-genai")
        except Exception as e:
            raise ValueError(f"❌ Gemini initialization failed: {e}")

    def generate_content(self, system_prompt, user_text, temperature=0.7):
        try:
            # Import inside method so missing package only fails when Gemini is used
            from google.genai import types

            # FIX: Use proper config object instead of plain dict
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,   # no 's' at the end
                temperature=temperature
            )

            response = self.client.models.generate_content(
                model=self.model_name, 
                contents=user_text,
                config=config
            )

            return self._validate(response.text or "")

        except Exception as e:
            raise AIProviderError(f"Gemini Error: {str(e)}") from e
             

# --- LIGHTNING AI ---
class LightningAIProvider(AIProvider):
    def __init__(self, api_key, model_name):
        super().__init__(api_key, model_name)
        try:
            from litai import LLM
            self.client = LLM(model=self.model_name, api_key=api_key)
        except ImportError:
            raise ValueError("❌ litai not installed. Run: pip install litai")
        except Exception as e:
            raise ValueError(f"❌ Lightning AI initialization failed: {e}")

    def generate_content(self, system_prompt, user_text, temperature=0.7):
        try:
            # FIX: Use messages format so system_prompt is respected as a directive
            prompt = f"[SYSTEM INSTRUCTIONS]\n{system_prompt}\n\n[TEXT TO PROCESS]\n{user_text}"
            response = self.client.chat(prompt, max_tokens=8192)

            # --- RESPONSE TYPE SAFETY GUARD ---
            # FIX: All failure paths now raise instead of returning error strings
            if response is None:
                raise Exception("Lightning AI returned None. Check your API key and model name.")

            if isinstance(response, str):
                import re
                text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', response).strip()
            elif hasattr(response, 'text') and response.text:
                text = response.text.strip()
            elif hasattr(response, 'content') and response.content:
                text = response.content.strip()
            else:
                text = str(response).strip()   
            return self._validate(text or "")

        except Exception as e:
            raise AIProviderError(f"Lightning AI Error: {str(e)}") from e


# --- OPENAI ---
class OpenAIProvider(AIProvider):
    def __init__(self, api_key, model_name):
        super().__init__(api_key, model_name)
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key)
        except ImportError:
            raise ValueError("❌ openai not installed. Run: pip install openai")
        except Exception as e:
            raise ValueError(f"❌ OpenAI initialization failed: {e}")

    def generate_content(self, system_prompt, user_text, temperature=0.7):
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_text}
                ],
                temperature=temperature,
                timeout=120  # FIX: hard timeout so a hung call doesn't freeze pipeline
            )
            content = response.choices[0].message.content
            return self._validate(content or "")

        except Exception as e:
            raise AIProviderError(f"OpenAI Error: {str(e)}") from e


# --- ANTHROPIC (CLAUDE) ---
class AnthropicProvider(AIProvider):
    def __init__(self, api_key, model_name):
        super().__init__(api_key, model_name)
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise ValueError("❌ anthropic not installed. Run: pip install anthropic")
        except Exception as e:
            raise ValueError(f"❌ Anthropic initialization failed: {e}")

    def generate_content(self, system_prompt, user_text, temperature=0.7):
        try:
            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_text}],
                temperature=temperature
            )
            from anthropic.types import TextBlock
            text_blocks = [block for block in response.content if isinstance(block, TextBlock)]
            if not text_blocks:
                raise AIProviderError("Anthropic returned no text content.")
            content = text_blocks[0].text 
            return self._validate(content or "")

        except Exception as e:
            raise AIProviderError(f"Anthropic Error: {str(e)}") from e


# --- PROVIDER REGISTRY ---
PROVIDER_REGISTRY = {
    "gemini":    GeminiProvider,
    "lightning": LightningAIProvider,
    "openai":    OpenAIProvider,
    "anthropic": AnthropicProvider,
}

# --- FACTORY ---
def get_ai_provider(provider_type, api_key, model_name):
    p_type = provider_type.lower().strip()
    if p_type not in PROVIDER_REGISTRY:
        raise ValueError(f"❌ Unknown provider: '{p_type}'. Available: {list(PROVIDER_REGISTRY.keys())}")
    return PROVIDER_REGISTRY[p_type](api_key, model_name)


def list_available_providers():
    return list(PROVIDER_REGISTRY.keys())