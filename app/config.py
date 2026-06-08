# File: app/config.py
# 엔진 전체 설정. 환경변수(SB_ 접두사) 또는 .env 파일로 주입.
# 임베딩 교체는 embedding_provider 한 줄 + (클라우드면) embed_api_key 로 끝난다.

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- 노트 / 벡터DB 위치 ---
    notes_path: str = "../my-second-brain"   # 헤르메스가 clone한 노트 레포 경로
    chroma_path: str = "./chroma_db"          # Chroma 벡터DB 저장 폴더(파일 기반)
    collection_name: str = "second_brain"     # 실제 컬렉션은 모델별로 자동 분리됨(index.py)
    ignore_dirs: list[str] = ["templates"]    # 인덱싱 제외 폴더

    # --- 임베딩 백엔드 (교체형) ---
    # provider: ollama | lmstudio | llamacpp | tei | openai | voyage | gemini
    embedding_provider: str = "ollama"
    embed_model: str = ""        # 비우면 provider 프리셋 기본 모델
    embed_base_url: str = ""     # 비우면 provider 프리셋 기본 주소(로컬 포트만 다르면 여기만 지정)
    embed_api_key: str = ""      # 클라우드 provider(openai/voyage/gemini) API 키

    # --- 정리(cleanup)용 LLM 백엔드 (중복 병합·요약) ---
    # 임베딩과 달리 '글을 새로 쓰는' 작업이라 생성형 LLM이 필요. 기본은 로컬 ollama.
    llm_provider: str = "ollama"      # 지금은 ollama만 지원
    llm_model: str = "gemma4:e4b"     # 비우면 provider 프리셋 기본 모델
    llm_base_url: str = ""            # 비우면 provider 프리셋 기본 주소(로컬 11434)

    # --- 검색 동작 ---
    auto_sync_on_search: bool = True          # 검색 직전 노트 변경분 자동 재인덱싱

    # --- API 보안 (옵션, 임베딩 키와 무관) ---
    api_key: str = ""                         # 비우면 인증 없음. 설정 시 X-API-Key 헤더 필수

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SB_",
        extra="ignore",
    )
