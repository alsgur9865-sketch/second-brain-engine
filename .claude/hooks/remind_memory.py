# File: .claude/hooks/remind_memory.py
# Stop hook — 세션이 끝날 때 "기억을 안 남겼으면" 한 번만 환기한다(능동+리마인더의 '리마인더').
# 동작: 이번 세션에 사용자 메시지가 충분히 많은데 second-brain remember를 한 번도 안 불렀으면,
#       Claude에게 "남길 기억 있으면 저장하라"고 환기(exit 2). 그 외엔 조용히 통과(exit 0).
# 무한루프 방지: stop_hook_active면 즉시 통과.

import json
import sys

# 사용자 메시지가 이 수 미만이면(짧은 질문·잡담) 환기하지 않는다.
MIN_USER_MESSAGES = 3
# transcript에서 remember 호출을 식별하는 문자열(MCP 툴 이름).
REMEMBER_MARK = "mcp__second-brain__remember"


def _is_real_user_message(line: str) -> bool:
    """transcript 한 줄이 '사람이 친 입력'이면 True. tool_result만 든 user 줄은 제외."""
    try:
        obj = json.loads(line)
    except (ValueError, TypeError):
        return False
    if obj.get("type") != "user":
        return False
    content = obj.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        # 텍스트 블록이 하나라도 있으면 사람 입력으로 본다(tool_result만이면 제외).
        return any(isinstance(b, dict) and b.get("type") == "text" for b in content)
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, TypeError):
        return 0  # 입력이 이상하면 조용히 통과

    if payload.get("stop_hook_active"):
        return 0  # 이미 hook으로 한 번 환기했음 → 무한루프 방지

    transcript = payload.get("transcript_path", "")
    if not transcript:
        return 0

    user_messages = 0
    remembered = False
    try:
        with open(transcript, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if REMEMBER_MARK in line:
                    remembered = True
                if _is_real_user_message(line):
                    user_messages += 1
    except FileNotFoundError:
        return 0

    if not remembered and user_messages >= MIN_USER_MESSAGES:
        sys.stderr.write(
            "이번 세션에 second-brain에 남길 게 있었는지 확인하세요. "
            "확정된 결정·버그 원인·할 일·배운 점이 있으면, 먼저 recall로 중복을 확인하고 "
            "mcp__second-brain__remember로 저장하세요(folder=decisions/bugs/todos). "
            "남길 게 없으면 그대로 종료해도 됩니다.\n"
        )
        return 2  # Stop을 막고 위 메시지를 Claude에게 전달

    return 0


if __name__ == "__main__":
    sys.exit(main())
