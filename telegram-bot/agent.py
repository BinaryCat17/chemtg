import json
import re
import os
import asyncio
import time
from datetime import datetime, date
from typing import List, Dict, Any
from litellm import acompletion
from tavily import TavilyClient
from database import Database
import prompts
import config

class RegistryAgent:
    def __init__(self):
        self.db = Database()
        self.tavily_api_key = config.TAVILY_API_KEY
        self.tavily = TavilyClient(api_key=self.tavily_api_key) if self.tavily_api_key else None
        self.model = config.LLM_MODEL
        self.api_base = os.getenv('LITELLM_BASE_URL')
        self.system_prompt = prompts.get_system_prompt()

    def _log_step(self, title: str, content: str):
        """Красивый вывод шага агента в консоль"""
        separator = "-" * 60
        print(f"\n{separator}\n[AGENT {title.upper()}]\n{content}\n{separator}", flush=True)

    async def run_sql(self, query: str) -> str:
        """Выполняет SQL запрос и возвращает результат"""
        self._log_step("SQL QUERY", query)
        results = self.db.execute_query(query)
        
        # Кастомный сериализатор для datetime
        def datetime_serializer(obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        try:
            res_str = json.dumps(results, ensure_ascii=False, indent=2, default=datetime_serializer)
        except Exception as e:
            res_str = f"Error serializing results: {str(e)}"
            
        log_res = res_str[:1000] + "..." if len(res_str) > 1000 else res_str
        self._log_step("SQL RESULT", log_res)
        return res_str

    async def run_search(self, query: str) -> str:
        """Выполняет поиск в интернете"""
        if not self.tavily:
            return "Web search is disabled (missing API key)."
        self._log_step("WEB SEARCH", query)
        try:
            results = self.tavily.search(query=query, search_depth="advanced", max_results=5)
            # Tavily returns a dict with 'results' list containing 'title', 'url', 'content'
            formatted_results = []
            for r in results.get('results', []):
                formatted_results.append(f"Title: {r.get('title')}\nContent: {r.get('content')}")
            res_str = "\n\n".join(formatted_results)
            
            if not res_str.strip():
                res_str = "No useful results found."
                
            self._log_step("SEARCH RESULT", f"Received {len(res_str)} chars from Tavily")
            return res_str
        except Exception as e:
            return f"Error during web search: {str(e)}"

    async def process_message(self, message: str, history: List[Dict[str, str]]) -> str:
        """Основной цикл обработки сообщения (Reasoning Loop)"""
        messages = [{"role": "system", "content": self.system_prompt}]
        for item in history:
            messages.append(item)
        messages.append({"role": "user", "content": message})

        print(f"\n{'='*95}\n🚀 NEW AGENT SESSION | User: {message}", flush=True)
        print(f"📊 MODEL: {self.model}", flush=True)
        print(f"📊 CONTEXT INFO: Messages={len(messages)}, System Prompt={len(self.system_prompt)} chars", flush=True)
        print(f"--- SYSTEM PROMPT START ---\n{self.system_prompt}\n--- SYSTEM PROMPT END ---", flush=True)
        print(f"{'='*95}", flush=True)

        max_iterations = 8
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            print(f"\n[STEP {iteration}] Requesting LiteLLM ({self.model})...", flush=True)
            start_time = time.time()
            
            try:
                response = await acompletion(
                    model=f"openai/{self.model}",
                    messages=messages,
                    temperature=0.1,  # Увеличено для стабильности старта
                    api_base=self.api_base,
                    api_key="sk-no-key-required"
                )
                
                duration = time.time() - start_time
                print(f"⏱️ Response received in {duration:.2f}s", flush=True)
                
                response_text = response.choices[0].message.content or ""
                
                if not response_text.strip():
                    if iteration == 1:
                        messages.append({"role": "user", "content": "Please start your research now. Use tools if needed. Your output must follow the !@!{JSON}!@! format."})
                        continue
                    return "⚠️ Ошибка: Модель вернула пустой ответ."

                self._log_step("THOUGHTS / RESPONSE", response_text)
                messages.append({"role": "assistant", "content": response_text})
                
                tool_calls = re.findall(r'!@!({.*?})!@!', response_text, re.DOTALL)
                
                if not tool_calls:
                    print("⚠️ WARNING: No !@!{...}!@! format detected. Nudging model.", flush=True)
                    messages.append({
                        "role": "user", 
                        "content": "You didn't use the required !@!{\"tool\": \"...\"}!@! format. ALL actions and final answers MUST be executed via tools. If you are ready to answer the user, use the 'answer-chat' tool."
                    })
                    continue

                final_answer = None
                for call_str in tool_calls:
                    try:
                        call_data = json.loads(call_str)
                        if not isinstance(call_data, dict):
                            raise ValueError("JSON must be a dictionary object.")
                            
                        tool = call_data.get("tool")
                        
                        if tool == "postgresql":
                            query = call_data.get("query")
                            if not query:
                                raise ValueError("Missing 'query' parameter.")
                            result = await self.run_sql(query)
                            messages.append({"role": "user", "content": f"TOOL RESULT (postgresql):\n{result}"})
                            
                        elif tool == "web-search":
                            query = call_data.get("query")
                            if not query:
                                raise ValueError("Missing 'query' parameter.")
                            result = await self.run_search(query)
                            messages.append({"role": "user", "content": f"TOOL RESULT (web-search):\n{result}"})
                            
                        elif tool == "answer-chat":
                            final_answer = call_data.get("answer")
                            if not final_answer:
                                raise ValueError("Missing 'answer' parameter.")
                            break
                        else:
                            err_msg = f"Unknown tool '{tool}'. Allowed: 'postgresql', 'web-search', 'answer-chat'."
                            self._log_step("ERROR", err_msg)
                            messages.append({"role": "user", "content": err_msg})
                            
                    except (json.JSONDecodeError, ValueError) as e:
                        err_msg = f"Tool call error: {str(e)}\nProvided JSON: {call_str[:100]}"
                        self._log_step("ERROR", err_msg)
                        messages.append({"role": "user", "content": f"Your JSON tool call was invalid: {err_msg}. Please fix it."})
                
                if final_answer:
                    print(f"\n✅ FINAL ANSWER DELIVERED (Total time: {time.time()-start_time:.2f}s)\n{'='*95}", flush=True)
                    return final_answer
                
            except Exception as e:
                err_msg = f"⚠️ Agent Error: {str(e)}"
                print(err_msg, flush=True)
                return err_msg

        return "⚠️ Превышено количество итераций."
