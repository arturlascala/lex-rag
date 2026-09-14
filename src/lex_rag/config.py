from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="LEX_RAG_",
        extra="ignore",
    )

    data_dir: Path = Field(default=PROJECT_ROOT / "data")
    qdrant_path: Path = Field(default=PROJECT_ROOT / "data" / "qdrant")
    raw_cache_path: Path = Field(default=PROJECT_ROOT / "data" / "raw")
    state_db: Path = Field(default=PROJECT_ROOT / "data" / "state.sqlite")

    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    device: str = "auto"  # "auto" | "cuda" | "cpu" (override via LEX_RAG_DEVICE)

    reranker_score_min: float = 0.55
    dense_prefetch_limit: int = 40
    sparse_prefetch_limit: int = 40

    # O Planalto (WAF) recusa User-Agents não-navegador com "server disconnected".
    # Usamos um UA de navegador; a coleta continua educada (sequencial, com pausa).
    http_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    http_max_parallel: int = 4
    http_polite_delay: float = 0.5  # pausa (s) entre downloads no bootstrap

    # Daemon de inferência (processo residente que segura os modelos quentes).
    # O MCP server é um cliente fino que fala com ele por HTTP no loopback.
    service_host: str = "127.0.0.1"
    service_port: int = 8765

    collection_name: str = "legislacao_federal"
    # Versão do pipeline de ingestão (parser + chunker + embedding). Bump após
    # qualquer fix que mude o resultado do processamento sem mudar o HTML de
    # origem: o delta reindexa toda norma cuja versão gravada não bata com esta.
    # 0.2.0: ordinal separado ("Art. 1 o")
    # 0.3.0: marcador sem ponto ("Art 1º") + veto que roubava o path do artigo
    # 0.4.0: decode cp1252 (aspas e travessões vinham como controle C1)
    pipeline_version: str = "0.4.0"

    log_level: str = "INFO"

    @property
    def service_url(self) -> str:
        return f"http://{self.service_host}:{self.service_port}"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.qdrant_path, self.raw_cache_path):
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
