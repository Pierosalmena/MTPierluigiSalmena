# diag.py
import os, time, asyncio
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

print("Step 1: .env loaded")
key = os.environ.get("OPENAI_API_KEY")
print(f"  OPENAI_API_KEY present: {bool(key)}")
print(f"  starts with: {key[:7] if key else 'NONE'}...")

print("\nStep 2: import openai")
from openai import OpenAI
client = OpenAI(api_key=key)
print("  ok")

print("\nStep 3: direct chat call to gpt-5-mini (60s timeout)")
t = time.time()
try:
    r = client.with_options(timeout=60).chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": "reply with just OK"}],
    )
    print(f"  returned in {time.time()-t:.1f}s: {r.choices[0].message.content!r}")
except Exception as e:
    print(f"  FAILED after {time.time()-t:.1f}s: {type(e).__name__}: {e}")

print("\nStep 4: import ragas")
from ragas.llms import llm_factory
from ragas.metrics import DiscreteMetric
print("  ok")

print("\nStep 5: build ragas llm + metric")
llm = llm_factory("gpt-5-mini", client=client)
m = DiscreteMetric(
    name="support",
    allowed_values=["supported", "partially_supported", "unsupported"],
    prompt="Reply with 'supported'. ANSWER: {answer} CONTEXT: {context}",
)
print("  ok")

print("\nStep 6: ONE synchronous score call (90s timeout via openai client)")
t = time.time()
try:
    score = m.score(llm=llm, answer="hello world", context="hello world")
    print(f"  returned in {time.time()-t:.1f}s: value={score.value!r}")
except Exception as e:
    print(f"  FAILED after {time.time()-t:.1f}s: {type(e).__name__}: {e}")

print("\nDone.")