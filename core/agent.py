import json
import re
import os
import asyncio
import time
import yaml
from datetime import datetime, date
from typing import List, Dict, Any
from litellm import acompletion
from tavily import TavilyClient
from database import Database
import prompts
import config

class RegistryAgent:
    def __init__(self, session_id: str = "default"):
        self.db = Database()
        self.tavily_api_key = config.TAVILY_API_KEY
        self.tavily = TavilyClient(api_key=self.tavily_api_key) if self.tavily_api_key else None
        self.model = config.LLM_MODEL
        self.api_base = os.getenv('LITELLM_BASE_URL')
        
        # Загружаем конфиг LiteLLM если он есть
        self.litellm_config = {}
        config_path = os.getenv("CONFIG_YAML_PATH", os.path.join(os.getcwd(), "config.yaml"))
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.litellm_config = yaml.safe_load(f)
                print(f"✅ LiteLLM config.yaml loaded: {len(self.litellm_config.get('model_list', []))} models from {config_path}")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки config.yaml: {e}")

        # Если мы не в Докере, сбрасываем адрес прокси-сервера
        if not self.api_base or "litellm:4000" in self.api_base:
            self.api_base = None
        self.system_prompt = prompts.get_system_prompt()
        self.session_id = session_id
        
        # Создаем директорию логов, если её нет
        self.log_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_path = os.path.join(self.log_dir, f"session_{self.session_id}.log")

    def _to_log(self, text: str, mode: str = 'a'):
        """Выводит текст в консоль и записывает в файл сессии"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {text}"
        print(log_entry, flush=True)
        try:
            with open(self.log_path, mode, encoding='utf-8') as f:
                f.write(log_entry + "\n")
        except Exception as e:
            print(f"Logging error: {e}")

    def _log_step(self, title: str, content: str):
        """Красивый вывод шага агента в консоль и лог"""
        separator = "-" * 60
        log_text = f"\n{separator}\n[AGENT {title.upper()}]\n{content}\n{separator}"
        self._to_log(log_text)

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
        # Ищем параметры модели в конфиге
        model_params = {}
        if self.litellm_config and 'model_list' in self.litellm_config:
            for item in self.litellm_config['model_list']:
                if item.get('model_name') == self.model:
                    model_params = item.get('litellm_params', {})
                    break

        target_model = model_params.get('model', self.model)
        target_api_key = model_params.get('api_key')
        
        # Если API ключ указан через os.environ/
        if isinstance(target_api_key, str) and target_api_key.startswith("os.environ/"):
            env_var = target_api_key.replace("os.environ/", "")
            target_api_key = os.getenv(env_var)
            
        if not target_api_key:
            target_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("XAI_API_KEY") or "sk-no-key-required"

        header = f"\n{'='*95}\n🚀 NEW AGENT MESSAGE | User: {message}\n"
        header += f"📊 SESSION ID: {self.session_id}\n"
        header += f"📊 MODEL: {self.model} -> {target_model}\n"
        header += f"📊 CONTEXT INFO: Messages={len(history)+2}, System Prompt={len(self.system_prompt)} chars\n"
        header += f"{'='*95}"
        self._to_log(header, mode='a')

        messages = [{"role": "system", "content": self.system_prompt}]
        for item in history:
            messages.append(item)
        messages.append({"role": "user", "content": message})

        max_iterations = 8
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            self._to_log(f"\n[STEP {iteration}] Requesting LiteLLM ({target_model})...")
            start_time = time.time()
            
            try:
                # В EXE режиме LiteLLM использует параметры из config.yaml или переменные окружения
                response = await acompletion(
                    model=target_model,
                    messages=messages,
                    temperature=0.1,
                    api_base=self.api_base,
                    api_key=target_api_key
                )
                
                duration = time.time() - start_time
                self._to_log(f"⏱️ Response received in {duration:.2f}s")
                # Убрано логирование полного объекта response, чтобы не засорять логи длинными кэшами и ID
                # self._to_log(f"DEBUG: Full response object: {response}")
                
                response_text = response.choices[0].message.content or ""
                
                if not response_text.strip():
                    self._to_log(f"DEBUG: Empty response text! Finish reason: {response.choices[0].finish_reason}")
                    if iteration == 1:
                        messages.append({"role": "user", "content": "Please start your research now. Use tools if needed. Your output must follow the !@!{JSON}!@! format."})
                        continue
                    return "⚠️ Ошибка: Модель вернула пустой ответ."

                self._log_step("THOUGHTS / RESPONSE", response_text)
                messages.append({"role": "assistant", "content": response_text})
                
                # Ищем все блоки !@!{...}!@!
                tool_calls = re.findall(r'!@!(.*?)!@!', response_text, re.DOTALL)
                
                if not tool_calls:
                    self._to_log("⚠️ WARNING: No !@! markers detected.")
                    messages.append({
                        "role": "user", 
                        "content": "ERROR: Your response must be wrapped in `!@!{\"tool\": \"...\"}!@!` markers. If this is a final answer, use `answer-chat`. Ensure all data is verified via `sqlite` before answering. Do not apologize, just provide the corrected tool call."
                    })
                    continue

                final_answer = None
                tool_results_combined = []
                
                for call_str in tool_calls:
                    try:
                        # Очищаем строку от возможных артефактов
                        cleaned_call = call_str.strip()
                        
                        # Исправляем проблему литеральных переносов строк внутри JSON
                        # (заменяем реальные переносы на \n, чтобы json.loads не падал)
                        if "\n" in cleaned_call:
                            # Но делаем это осторожно, только если это не валидный JSON
                            try:
                                json.loads(cleaned_call)
                            except json.JSONDecodeError:
                                # Если падает, пробуем экранировать переносы
                                cleaned_call = cleaned_call.replace("\n", "\\n")

                        # Если модель прислала экранированный JSON внутри маркеров
                        if cleaned_call.startswith('\\"'):
                            cleaned_call = cleaned_call.replace('\\"', '"')
                        
                        # Декодируем JSON
                        call_data = json.loads(cleaned_call)
                        
                        # Если это список (не должно быть, но на всякий случай)
                        if isinstance(call_data, list) and len(call_data) > 0:
                            call_data = call_data[0]

                        if not isinstance(call_data, dict):
                            raise ValueError(f"JSON must be a dictionary, got {type(call_data)}")
                            
                        # Извлекаем имя инструмента, игнорируя лишние кавычки в ключе
                        tool = call_data.get("tool") or call_data.get('"tool"')
                        
                        if not tool:
                            self._to_log(f"DEBUG: Missing 'tool' key in JSON: {cleaned_call}")
                            raise KeyError("tool")
                        
                        if tool == "sqlite":
                            query = call_data.get("query") or call_data.get('"query"')
                            if not query: raise ValueError("Missing 'query' parameter.")
                            result = await self.run_sql(query)
                            tool_results_combined.append(f"--- TOOL RESULT (sqlite) ---\n{result}")
                            
                        elif tool == "web-search":
                            query = call_data.get("query") or call_data.get('"query"')
                            if not query: raise ValueError("Missing 'query' parameter.")
                            result = await self.run_search(query)
                            tool_results_combined.append(f"--- TOOL RESULT (web-search) ---\n{result}")
                            
                        elif tool == "answer-chat":
                            final_answer = call_data.get("answer") or call_data.get('"answer"')
                            if not final_answer: raise ValueError("Missing 'answer' parameter.")
                            break
                        else:
                            err_msg = f"Unknown tool '{tool}'."
                            self._log_step("ERROR", err_msg)
                            tool_results_combined.append(err_msg)
                            
                    except Exception as e:
                        err_msg = f"Tool call error: {str(e)}\nInput: {call_str[:100]}"
                        self._log_step("ERROR", err_msg)
                        tool_results_combined.append(f"Your JSON tool call was invalid: {str(e)}. Please fix it.")
                
                if final_answer:
                    self._to_log(f"\n✅ FINAL ANSWER DELIVERED (Total time: {time.time()-start_time:.2f}s)\n{'='*95}")
                    return final_answer
                    
                if tool_results_combined:
                    combined_text = "\n\n".join(tool_results_combined)
                    messages.append({"role": "user", "content": combined_text})
                
            except Exception as e:
                err_msg = f"⚠️ Agent Error: {str(e)}"
                self._to_log(err_msg)
                return err_msg

        return "⚠️ Превышено количество итераций."
