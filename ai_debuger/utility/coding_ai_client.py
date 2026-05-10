from openai import OpenAI
import re


class CodingAIClient:
    """AI Client specialized for coding questions"""
    
    def __init__(self):
        self.client = OpenAI(
            base_url='http://localhost:11434/v1',
            api_key='ollama',
        )
        # Use the best available model
        self.model = "mistral:latest"
    
    def chat(self, message, history=None):
        """
        Chat with the AI about coding topics
        
        Args:
            message: User's message
            history: Previous conversation history (list of dicts with 'role' and 'content')
        
        Returns:
            AI response as string
        """
        system_prompt = """You are an expert coding assistant. You help developers with:
• Writing code (Python, JavaScript, HTML, CSS, etc.)
• Debugging and fixing errors
• Explaining programming concepts
• Best practices and code reviews
• Algorithm design and optimization

RULES:
1. ONLY answer coding and programming questions
2. If asked non-coding questions, politely redirect to coding topics
3. Use markdown formatting for code blocks: ```python or ```javascript
4. Be concise but thorough
5. Provide working, tested code examples
6. Explain complex concepts simply

For code blocks, ALWAYS use proper markdown:
```python
def example():
    return "like this"
```

If user asks non-coding questions like "what's the weather" or "tell me a joke", respond:
"I'm a coding assistant focused on programming questions. How can I help you with code today?"
"""
        
        # Build messages array
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history (last 10 messages for context)
        if history:
            for msg in history[-10:]:
                messages.append({
                    "role": msg.get('role', 'user'),
                    "content": msg.get('content', '')
                })
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        print(f"\n🤖 Calling {self.model}...")
        print(f"   Context: {len(messages)-2} previous messages")
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
                stream=False
            )
            
            ai_response = response.choices[0].message.content.strip()
            
            print(f"✅ Response received ({len(ai_response)} chars)\n")
            
            return ai_response
            
        except Exception as e:
            print(f"❌ ERROR: {e}\n")
            
            # Check if it's a model not found error
            if "model" in str(e).lower() and "not found" in str(e).lower():
                return f"""⚠️ **Model Error**

The AI model `{self.model}` is not installed.

**Quick Fix:**
```bash
# Install the model
ollama pull {self.model}

# Or use a different model
ollama pull llama3.2:3b
```

Then restart your Django server."""
            
            # Generic error
            return f"""⚠️ **Connection Error**

I couldn't connect to the AI service.

**Troubleshooting:**
1. Check Ollama is running: `ollama list`
2. Make sure model is installed: `ollama pull {self.model}`
3. Check terminal logs for details

**Error:** {str(e)}"""
    
    def generate_code(self, prompt, language="python"):
        """
        Generate code based on a prompt
        
        Args:
            prompt: Description of what code to generate
            language: Programming language
        
        Returns:
            Generated code as string
        """
        system_prompt = f"""You are a code generator. Generate ONLY executable {language} code.

RULES:
1. Output ONLY code, no explanations
2. Use proper {language} syntax
3. Add brief comments where helpful
4. Make code production-ready

Format your response as:
```{language}
# Your code here
```"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            code = response.choices[0].message.content.strip()
            
            # Extract code from markdown if present
            code_match = re.search(rf'```{language}\n(.*?)```', code, re.DOTALL | re.IGNORECASE)
            if not code_match:
                code_match = re.search(r'```\n(.*?)```', code, re.DOTALL)
            
            if code_match:
                return code_match.group(1).strip()
            
            return code
            
        except Exception as e:
            return f"# Error generating code: {str(e)}"
    
    def explain_code(self, code, language="python"):
        """
        Explain what a piece of code does
        
        Args:
            code: The code to explain
            language: Programming language
        
        Returns:
            Explanation as string
        """
        prompt = f"""Explain this {language} code clearly and concisely:

```{language}
{code}
```

Format:
1. What it does (1-2 sentences)
2. Key concepts used
3. Potential improvements (if any)"""
        
        return self.chat(prompt)
    
    def debug_code(self, code, error_message="", language="python"):
        """
        Debug code and suggest fixes
        
        Args:
            code: The buggy code
            error_message: Error message (if any)
            language: Programming language
        
        Returns:
            Debug analysis and fixed code
        """
        prompt = f"""Debug this {language} code:

```{language}
{code}
```
"""
        
        if error_message:
            prompt += f"\n**Error Message:**\n```\n{error_message}\n```"
        
        prompt += "\n\nProvide:\n1. What's wrong\n2. Fixed code\n3. Explanation"
        
        return self.chat(prompt)