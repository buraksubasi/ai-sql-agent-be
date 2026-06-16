from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.messages import HumanMessage, AIMessage
from database import get_df_connection
from pydantic import BaseModel, Field

# ─── Oturum hafızası ──────────────────────────────────────────────────────────

sessions_memory: dict[str, list] = {}


def get_chat_history(session_id: str) -> list:
    if session_id not in sessions_memory:
        sessions_memory[session_id] = []
    return sessions_memory[session_id]


# ─── Router şeması ────────────────────────────────────────────────────────────

class RouterDecision(BaseModel):
    intent: str = Field(
        description=(
            "Kullanıcı mesajı ürünler, stok, fiyat, kategori veya veritabanı "
            "sorguları ile ilgiliyse 'DB' dönün. Selamlama, hal hatır sorma "
            "veya genel bilgi soruları için 'GENERAL' dönün."
        )
    )


# ─── Ana sınıf ────────────────────────────────────────────────────────────────

class SQLAgentRouter:
    def __init__(self) -> None:
        db = get_df_connection()
        self.llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
        self.chat_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.5)
        toolkit = SQLDatabaseToolkit(db=db, llm=self.llm)
        self.sql_agent = create_sql_agent(
            self.llm, toolkit=toolkit, verbose=True, handle_parsing_errors=True
        )
        self.search_tool = DuckDuckGoSearchRun()
        self.router_llm = self.llm.with_structured_output(RouterDecision)

    # ── Yardımcı ──────────────────────────────────────────────────────────────

    def _history_context(self, session_id: str) -> tuple[list, str]:
        history = get_chat_history(session_id)
        context = ""
        for msg in history[-4:]:
            role = "Kullanıcı" if isinstance(msg, HumanMessage) else "Asistan"
            context += f"{role}: {msg.content}\n"
        return history, context

    def _build_messages(self, history: list, user_content: str) -> list:
        msgs = [
            (
                "system",
                "Sen arkadaş canlısı, yetenekli bir asistansın. "
                "Sana sağlanan konuşma geçmişine ve eğer varsa internet "
                "arama sonuçlarına sadık kalarak kullanıcıya Türkçe yanıt ver.",
            )
        ]
        for msg in history[-6:]:
            role = "user" if isinstance(msg, HumanMessage) else "assistant"
            msgs.append((role, msg.content))
        msgs.append(("user", user_content))
        return msgs

    # ── Senkron çalıştırıcı (mevcut /api/chat endpoint'i için) ───────────────

    def __call__(self, user_question: str, session_id: str) -> str:
        history, history_context = self._history_context(session_id)

        router_prompt = (
            f"Konuşma Geçmişi:\n{history_context}\n"
            f"Yeni Mesaj: {user_question}\n\nNiyeti belirle:"
        )
        decision = self.router_llm.invoke(router_prompt)
        print(f"\n[ROUTER] Session: {session_id} | Niyet: {decision.intent}\n")

        if decision.intent == "DB":
            result = self.sql_agent.invoke({"input": user_question})
            final_response: str = result.get("output", "")
        else:
            search_check = self.llm.invoke(
                f"Soru güncel bilgi, haber veya internet araması gerektiriyor mu? "
                f"Sadece 'EVET' veya 'HAYIR'.\n\nSoru: {user_question}"
            )
            search_context = ""
            if "EVET" in search_check.content.upper():
                try:
                    search_context = (
                        f"\n\n[İnternet Arama Sonuçları]: "
                        f"{self.search_tool.run(user_question)}"
                    )
                except Exception as exc:
                    print(f"[ARAMA HATASI] {exc}")

            msgs = self._build_messages(history, user_question + search_context)
            response = self.chat_llm.invoke(msgs)
            final_response = response.content

        history.append(HumanMessage(content=user_question))
        history.append(AIMessage(content=final_response))
        return final_response

    # ── Asenkron streaming (yeni /api/chat/stream endpoint'i için) ────────────

    async def stream(self, user_question: str, session_id: str):
        """
        Düşünme adımlarını ve nihai yanıtı SSE-uyumlu dict olarak verir.
        Chunk tipleri: "thinking" | "token" | "done" | "error"
        """
        history, history_context = self._history_context(session_id)

        yield {"type": "thinking", "content": "Niyet analiz ediliyor..."}

        router_prompt = (
            f"Konuşma Geçmişi:\n{history_context}\n"
            f"Yeni Mesaj: {user_question}\n\nNiyeti belirle:"
        )
        decision = self.router_llm.invoke(router_prompt)

        final_response = ""

        # ── Senaryo A: Veritabanı sorgusu ─────────────────────────────────────
        if decision.intent == "DB":
            yield {"type": "thinking", "content": "Veritabanı sorgusu tespit edildi, SQL Agent başlatılıyor..."}

            async for event in self.sql_agent.astream_events(
                {"input": user_question}, version="v2"
            ):
                kind = event["event"]
                name = event.get("name", "")
                data = event.get("data", {})

                if kind == "on_tool_start":
                    inp = data.get("input", {})
                    if isinstance(inp, dict):
                        inp_str = str(list(inp.values())[0])[:150] if inp else ""
                    else:
                        inp_str = str(inp)[:150]
                    yield {
                        "type": "thinking",
                        "content": f"**{name}** çalıştırılıyor: `{inp_str}`",
                    }

                elif kind == "on_tool_end":
                    out = str(data.get("output", ""))[:200]
                    if out:
                        yield {"type": "thinking", "content": f"Araç sonucu: {out}"}

                elif kind == "on_chain_end":
                    out = data.get("output", {})
                    if isinstance(out, dict) and "output" in out:
                        candidate: str = out["output"]
                        if candidate:
                            final_response = candidate

            # Son çare: astream_events yanıt vermezse senkron fallback
            if not final_response:
                result = self.sql_agent.invoke({"input": user_question})
                final_response = result.get("output", "Yanıt alınamadı.")

            yield {"type": "token", "content": final_response}

        # ── Senaryo B: Genel sohbet ───────────────────────────────────────────
        else:
            yield {"type": "thinking", "content": "Genel sohbet modu aktif"}

            search_check = self.llm.invoke(
                f"Soru güncel bilgi, haber veya internet araması gerektiriyor mu? "
                f"Sadece EVET veya HAYIR.\n\nSoru: {user_question}"
            )

            search_context = ""
            if "EVET" in search_check.content.upper():
                yield {"type": "thinking", "content": "İnternet araması yapılıyor..."}
                try:
                    result_text = self.search_tool.run(user_question)
                    search_context = f"\n\n[İnternet Arama Sonuçları]: {result_text}"
                    yield {"type": "thinking", "content": "Arama tamamlandı"}
                except Exception as exc:
                    yield {
                        "type": "thinking",
                        "content": f"Arama başarısız: {str(exc)[:80]}",
                    }

            msgs = self._build_messages(history, user_question + search_context)
            yield {"type": "thinking", "content": "Yanıt oluşturuluyor..."}

            async for chunk in self.chat_llm.astream(msgs):
                if chunk.content:
                    final_response += chunk.content
                    yield {"type": "token", "content": chunk.content}

        yield {"type": "done"}

        history.append(HumanMessage(content=user_question))
        history.append(AIMessage(content=final_response))


# ─── Geriye dönük uyumluluk ───────────────────────────────────────────────────

def get_sql_agent_router():
    """main.py'nin eski senkron kullanımı için tutuldu."""
    router = SQLAgentRouter()
    return router
