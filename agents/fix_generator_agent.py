from langchain_core.messages import SystemMessage, HumanMessage

from agents import llm
from agents.state import IncidentState

SYSTEM_PROMPT = """You are an expert software engineer generating a targeted code fix.

Output the fix in EXACTLY this delimited format — no other text:

===FILE===
<filename.py>
===ORIGINAL===
<the exact buggy code snippet, as short as possible>
===FIXED===
<the corrected replacement code>
===EXPLANATION===
<one or two sentences explaining what was wrong and what you changed>

Rules:
- Keep the fix minimal and surgical
- The ORIGINAL section must reflect the actual code visible in the error logs
- The FIXED section must be a drop-in replacement for ORIGINAL
- Use the exact variable names, function names, and line numbers from the stack trace
- Do NOT wrap code in markdown fences inside these sections
- For None/missing-object errors: prefer an explicit `if x is None:` guard
- For bounds/index errors: prefer an explicit `if index < len(collection):` check
- For zero-division errors: prefer an explicit `if denominator == 0:` guard using the exact variable name
- For missing-key errors: prefer `.get(key)` over try/except"""


def fix_generator_agent(state: IncidentState) -> dict:
    human_content = (
        f"Root Cause:\n{state['root_cause']}\n\n"
        f"Relevant Files: {', '.join(state['relevant_files']) or 'unknown'}\n\n"
        f"Error Logs:\n```\n{state['raw_logs']}\n```"
    )

    if state.get("critic_feedback"):
        human_content += (
            f"\n\nPREVIOUS FIX FAILED — Critic Feedback:\n{state['critic_feedback']}"
            "\n\nDo NOT repeat the previous approach. Address the feedback directly."
        )

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ])

    patch_text = response.content.strip()

    # Extract explanation separately for display
    explanation = ""
    if "===EXPLANATION===" in patch_text:
        parts = patch_text.split("===EXPLANATION===")
        explanation = parts[-1].strip()

    return {
        "code_patch": patch_text,
        "patch_explanation": explanation,
        "status": "fix_generated",
    }
