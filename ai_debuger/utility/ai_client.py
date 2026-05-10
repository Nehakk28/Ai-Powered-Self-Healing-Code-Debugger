from openai import OpenAI
import json
import re

class EnhancedAIClient:
    """Enhanced AI Client with SMARTER intent detection"""
    
    def __init__(self):
        self.client = OpenAI(
            base_url='http://localhost:11434/v1',
            api_key='ollama',
        )
        # Better model for code generation
        self.model = "mistral:latest"
        # Fallback if codellama not available
        self.fallback_model = "llama3.2:3b"
    
    def detect_intent(self, message, current_code=""):
        """IMPROVED: Smarter intent detection"""
        message_lower = message.lower().strip()
        
        print(f"\n🔍 INTENT DETECTION:")
        print(f"   Message: '{message_lower}'")
        
        # EXPANDED generation keywords - more trigger words
        generation_keywords = [
            # Action verbs
            'create', 'write', 'make', 'generate', 'build', 'design', 
            'code', 'develop', 'implement', 'program',
            
            # Code-specific
            'function', 'class', 'loop', 'for loop', 'while loop',
            'html', 'css', 'javascript', 'python', 'java',
            'login', 'form', 'button', 'page', 'website',
            'script', 'algorithm', 'api', 'database',
            
            # Phrases
            'show me', 'give me', 'can you', 'i need', 'i want',
            'how to', 'help me', 'example of'
        ]
        
        analysis_keywords = [
            'analyze', 'debug', 'fix', 'check', 'review',
            'find bugs', 'optimize', 'improve', "what's wrong",
            'error', 'issue', 'problem'
        ]
        
        # Check for generation first
        for keyword in generation_keywords:
            if keyword in message_lower:
                print(f"   ✅ Matched generation keyword: '{keyword}'")
                print(f"   → Intent: GENERATE\n")
                return 'generate'
        
        # Check for analysis (only if code exists)
        if current_code.strip():
            for keyword in analysis_keywords:
                if keyword in message_lower:
                    print(f"   ✅ Matched analysis keyword: '{keyword}'")
                    print(f"   → Intent: ANALYZE\n")
                    return 'analyze'
        
        print(f"   → Intent: CHAT (no keywords matched)\n")
        return 'chat'
    
    def generate_code(self, request, language="python"):
        """Generate code with better prompting"""
        
        # Try codellama first, fallback to llama3
        try:
            model = self.model
        except:
            model = self.fallback_model
            print(f"⚠️ Using fallback model: {model}")
        
        system_prompt = f"""You are an expert {language} programmer.

CRITICAL RULES:
1. Generate ONLY the code, nothing else
2. No explanations before the code
3. No markdown formatting
4. Just pure, executable {language} code

Example request: "create a for loop"
Your response:
for i in range(5):
    print(i)

Now generate the code for the user's request."""

        try:
            print(f"\n🤖 Calling {model} for code generation...")
            
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": request}
                ],
                temperature=0.2,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content.strip()
            
            print(f"📥 Raw response ({len(content)} chars):")
            print(f"   {content[:150]}...")
            
            # Extract code
            generated_code = self._extract_code_from_response(content, language)
            
            if not generated_code:
                # If extraction failed, use raw content
                generated_code = content
            
            print(f"✅ Generated code ({len(generated_code)} chars)")
            
            return {
                "generated_code": generated_code,
                "explanation": f"I've created the {language} code you requested.",
                "language": language,
                "suggestions": []
            }
            
        except Exception as e:
            print(f"❌ ERROR in generate_code: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "generated_code": f"# Error: {str(e)}\n# Check Ollama is running and model is installed",
                "explanation": f"Error: {str(e)}",
                "language": language,
                "suggestions": []
            }
    
    def analyze_code(self, code, language="python"):
        """Analyze code - NOW RETURNS JSON"""
        system_prompt = f"""You are a professional code analyzer and cross-language translator specializing in {language}.
Your primary goal is to ensure the output code is written in {language}.

Analyze the code and respond with ONLY valid JSON in this exact format:

{{
  "bugs_found": 0,
  "issues": [],
  "corrected_code": "the actual fixed code here",
  "explanation": "detailed explanation of what you found and fixed"
}}

CRITICAL RULES:
1. THE OUTPUT CODE MUST BE IN {language}. This is non-negotiable.
2. If the input is in a different language, TRANSLATE it to {language}.
3. If the input has bugs, FIX THEM while ensuring the output is {language}.
4. Return ONLY the JSON object, no markdown, no extra text, no code blocks.
5. ESCAPE ALL NEWLINES in strings as \\n.
6. Do NOT wrap JSON in ```json ``` markers.

Example for translation (C++ to Python):
{{
  "bugs_found": 0,
  "issues": [],
  "corrected_code": "print('hello')",
  "explanation": "Translated C++ cout to Python print."
}}"""

        try:
            print(f"\n🤖 Analyzing code with {self.fallback_model}...")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"INPUT CODE: \n{code}\n\nTASK: Correct all bugs AND ensure the final output is written in ONLY valid {language}."}
                ],
                temperature=0.2,
                max_tokens=3000
            )
            
            content = response.choices[0].message.content.strip()
            print(f"📥 Raw Analysis Response:\n{content[:500]}...\n{'='*50}")
            
            # Clean up potential markdown code blocks
            if content.startswith('```'):
                print("⚠️ Removing markdown code blocks...")
                content = re.sub(r'^```json\s*\n?|^```\s*\n?|\n?```$', '', content, flags=re.MULTILINE).strip()
                print(f"📥 Cleaned content:\n{content[:500]}...")
            
            # Parse JSON
            try:
                result = json.loads(content)
                print(f"✅ Successfully parsed JSON")
            except json.JSONDecodeError as json_err:
                print(f"❌ JSON Parse Error: {json_err}")
                print(f"❌ Failed content: {content}")
                # Fallback to regex parsing
                print("⚠️ Falling back to regex parsing...")
                result = self._parse_analysis_response_fallback(content, code)
            
            # Validate and fix structure
            if "bugs_found" not in result:
                result["bugs_found"] = 0
            if "corrected_code" not in result:
                result["corrected_code"] = code
            if "explanation" not in result:
                result["explanation"] = "Analysis complete."
            if "issues" not in result:
                result["issues"] = []
            
            # Ensure bugs_found is an integer
            if isinstance(result["bugs_found"], str):
                try:
                    result["bugs_found"] = int(result["bugs_found"])
                except:
                    result["bugs_found"] = 0
            
            print(f"📊 Final result: bugs_found={result['bugs_found']}, has_corrected_code={len(result.get('corrected_code', '')) > 0}")
            
            return result
            
        except Exception as e:
            print(f"❌ ERROR in analyze_code: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "bugs_found": 0,
                "issues": [],
                "corrected_code": code,
                "explanation": f"Error during analysis: {str(e)}"
            }
    
    def chat(self, message, code_context=None, history=None):
        print("history", history)
        """Simple chat"""
        messages = [
            {"role": "system", "content": "You are a helpful coding assistant. Be concise."}
        ]
        
        if code_context:
            messages.append({
                "role": "system",
                "content": f"User's code:\n```\n{code_context[:1000]}\n```"
            })
        
        messages.append({"role": "user", "content": message})
        
        try:
            response = self.client.chat.completions.create(
                model=self.fallback_model,
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _extract_code_from_response(self, content, language):
        """Extract code from response"""
        # Remove markdown code blocks
        patterns = [
            rf'```{language}\n(.*?)```',
            r'```\n(.*?)```',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # If no code blocks, return as-is (assuming it's already code)
        return content.strip()
    
    def _parse_analysis_response_fallback(self, content, original_code):
        """FALLBACK: Robust parsing for malformed JSON using regex"""
        print("⚠️ Using robust regex fallback parsing...")
        
        result = {
            "bugs_found": 0,
            "issues": [],
            "corrected_code": original_code,
            "explanation": "Analysis complete (fallback parsing used)."
        }
        
        # 1. Try to extract corrected_code
        # Look for "corrected_code": " then everything until the next " that is followed by , or }
        code_match = re.search(r'"corrected_code":\s*"(.*?)"\s*[,}]', content, re.DOTALL)
        if code_match:
            result["corrected_code"] = code_match.group(1).replace('\\n', '\n').replace('\\t', '\t')
        else:
            # Try a broader search if the above fails
            code_match_broad = re.search(r'"corrected_code":\s*"(.*)"', content, re.DOTALL)
            if code_match_broad:
                # This might capture too much, so we take everything until the next likely key
                potential_code = code_match_broad.group(1)
                # Split at the next potential JSON key
                parts = re.split(r'"\s*,\s*"[a-zA-Z_]+":', potential_code)
                result["corrected_code"] = parts[0].strip()

        # 2. Try to extract explanation
        expl_match = re.search(r'"explanation":\s*"(.*?)"\s*[,}]', content, re.DOTALL)
        if expl_match:
            result["explanation"] = expl_match.group(1)
            
        # 3. Try to extract bugs_found
        bugs_match = re.search(r'"bugs_found":\s*(\d+)', content)
        if bugs_match:
            result["bugs_found"] = int(bugs_match.group(1))

        # 4. Try to extract issues (list of strings)
        issues_match = re.search(r'"issues":\s*\[(.*?)\]', content, re.DOTALL)
        if issues_match:
            issues_str = issues_match.group(1)
            issues = re.findall(r'"(.*?)"', issues_str)
            result["issues"] = issues

        # Clean up code if it still has markdown blocks
        if result["corrected_code"]:
            result["corrected_code"] = re.sub(r'^```\w*\n', '', result["corrected_code"])
            result["corrected_code"] = re.sub(r'\n```$', '', result["corrected_code"])

        print(f"✅ Robust fallback parsing complete: bugs_found={result['bugs_found']}, code_len={len(result['corrected_code'])}")
        return result