"""Conversational career assistant (Phase 8).

Deterministic by default: understand the question (intents.py), resolve the
things it refers to against the student's own data and the conversation's
earlier result sets (resolver.py), gather facts with traceable sources from
existing Phase 1-7 services (tools.py), and render them (responder.py).
Optional AI rewording (llm_rewrite.py) only rephrases those facts and is
verified claim by claim (verify.py). The assistant never writes Phase 1-7
data; it suggests actions for the frontend to confirm.
"""
