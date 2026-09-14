"""Daemon de inferência do lex-rag.

Processo residente que carrega os modelos (BGE-M3 + reranker) uma única vez e
mantém o Qdrant embedded aberto, evitando o cold start a cada sessão do MCP.
"""
