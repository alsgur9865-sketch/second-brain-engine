# examples — bundled sample vault / 번들 샘플 vault

`vault/` is a tiny Markdown note repo for trying the engine **without setting up
your own notes**. Point the engine at it and search right away:

```bash
# bash / macOS / Linux
SB_NOTES_PATH=examples/vault uvicorn app.main:app --port 8000

# Windows PowerShell
$env:SB_NOTES_PATH="examples/vault"; uvicorn app.main:app --port 8000
```

Then search (semantic — matches by *meaning*, not keywords):

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "how many days do I have to get my money back?", "k": 3}'
```

You should get the **refund-policy** note back even though your query shares
almost no keywords with it.

---

`vault/`는 본인 노트 없이 엔진을 바로 시험해 보라고 넣은 작은 샘플 노트 레포다.
위처럼 `SB_NOTES_PATH`를 여기로 가리키면 즉시 검색된다. "돈 돌려받는 규칙" 처럼
키워드가 안 맞아도 환불 정책 노트가 의미로 잡히는 걸 확인할 수 있다.

> 이 `examples/README.md`는 vault 바깥이라 인덱싱되지 않는다.
