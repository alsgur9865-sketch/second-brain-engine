# File: app/config.py
# 엔진 전체 설정. 환경변수(SB_ 접두사) 또는 .env 파일로 주입.
# 임베딩 프로바이더 교체가 여기서 시작된다 — embedding_provider 값만 바꾸면 됨.

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- 노트 / 벡터DB 위치 ---
    notes_path: str = "../my-second-brain"   # 헤르메스가 clone한 노트 레포 경로
    chroma_path: str = "./chroma_db"          # Chroma 벡터DB 저장 폴더(파일 기반)
    collection_name: str = "second_brain"
    ignore_dirs: list[str] = ["templates"]    # 인덱싱 제외 폴더(양식 등, 검색 노이즈 방지)

    # --- 임베딩 프로바이더 선택 (교체형) ---
    embedding_provider: str = "ollama"        # "ollama" | "openai"

    # Ollama (로컬, 기본값) — gemma 돌리는 그 Ollama 그대로 사용
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "bge-m3"        # 다국어·한국어 강력. (가벼운 대안: nomic-embed-text)

    # OpenAI (교체 시) — SB_EMBEDDING_PROVIDER=openai 로 전환
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_embed_model: str = "text-embedding-3-small"

    # --- 검색 동작 ---
    auto_sync_on_search: bool = True          # 검색 직전 노트 변경분 자동 재인덱싱

    # --- API 보안 (옵션) ---
    api_key: str = ""                         # 비우면 인증 없음. 설정 시 X-API-Key 헤더 필수

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SB_",
        extra="ignore",
    )
