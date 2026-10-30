"""The four agents. Each does one job and is timed on its own.

  GuardAgent      masks personal data, spots urgent situations          local, ~0 ms
  RetrievalAgent  embeds the question, searches Pinecone (current only)  OpenAI + Pinecone
  AnswerAgent     drafts a JSON answer using ONLY the retrieved KB       OpenAI chat
  VerifierAgent   compares the draft with the retrieved articles and     local, ~0 ms
                  blocks anything uncited, unsupported or unsafe

Only AnswerAgent calls the LLM, and only when retrieval found a relevant article.
Guard and verifier are plain code on purpose: instant, deterministic, and a prompt
injection can't talk them out of their rules.
"""
from .answer import AnswerAgent, Draft
from .guard import GuardAgent, GuardResult
from .retrieval import Hit, RetrievalAgent, RetrievalResult
from .verifier import Verdict, VerifierAgent

__all__ = ["GuardAgent", "GuardResult", "RetrievalAgent", "RetrievalResult", "Hit",
           "AnswerAgent", "Draft", "VerifierAgent", "Verdict"]
