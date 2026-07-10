# Dataset schema

One JSON object per line (JSONL). Each object is one full episode — a whole multi-turn tool-calling
conversation, not a single Q&A pair. This mirrors `ChatMessage` / `ToolCall` in
`backend/app/ai/base.py` and the tool specs in `backend/app/ai/tools.py`.

```jsonc
{
  "id": "cisco-ospf-neighbor-down-001",   // unique, kebab-case, prefix by vendor
  "vendor": "cisco_ios",                  // "cisco_ios" | "eltex"
  "tags": ["ospf", "troubleshooting"],    // free-form, used for eval-set stratification
  "messages": [
    {
      "role": "system",
      "content": "<copy verbatim from SYSTEM_MESSAGE in backend/app/ai/loop.py>"
    },
    {
      "role": "user",
      "content": "Router in the branch office lost its route to HQ, can you check what's wrong on R2?"
    },
    {
      "role": "assistant",
      "content": "I'll check OSPF neighbor state on R2 first.",
      "tool_calls": [
        {"name": "send_command", "arguments": {"command": "show ip ospf neighbor"}}
      ]
    },
    {
      "role": "tool",
      "tool_name": "send_command",
      "content": "Neighbor ID     Pri   State           Dead Time   Address         Interface\n<realistic output showing the actual problem>"
    },
    {
      "role": "assistant",
      "content": "Neighbor 10.0.0.1 is stuck in EXSTART -- usually an MTU mismatch. Checking interface MTU.",
      "tool_calls": [
        {"name": "send_command", "arguments": {"command": "show interface GigabitEthernet0/1 | include MTU"}}
      ]
    },
    {
      "role": "tool",
      "tool_name": "send_command",
      "content": "  MTU 1500 bytes, BW 1000000 Kbit, DLY 10 usec"
    },
    {
      "role": "assistant",
      "content": "MTU matches on this side, so the mismatch is on the neighbor. Root cause found — recommend checking R1's Gi0/1 MTU next. Summary: OSPF neighbor 10.0.0.1 stuck in EXSTART on R2's Gi0/1, consistent with an MTU mismatch on the peer interface; R2's own MTU (1500) is standard, so check R1's side."
    }
  ]
}
```

## Rules

- **`messages[0]`** is always the system message, copied verbatim from `SYSTEM_MESSAGE` in
  `backend/app/ai/loop.py`. If that prompt changes, regenerate/re-copy it before your next training
  run — training on a stale system prompt wastes the point of matching production.
- **`tool_calls`** only appears on `role: "assistant"` messages. One or more calls per message is
  allowed (matches `ToolCallRequested.calls: list[ToolCall]` in `base.py`), but in practice one
  `send_command` per turn is the realistic pattern — the real loop executes a call, waits for
  output, then lets the model see it before deciding the next command.
- **`role: "tool"`** messages must set `tool_name` to the name of the tool that was called
  (`read_terminal_scrollback` or `send_command`) and `content` to the realistic device output (or
  scrollback text). This is the field the real `ollama_provider.py` reads — see the comment on
  `ChatMessage.tool_name` in `base.py`.
- **The last message is always `role: "assistant"` with no `tool_calls`** — a final natural-language
  answer to the engineer. Don't end an episode mid-tool-call.
- **Command syntax must be correct for the declared `vendor`.** Cisco IOS/IOS-XE and Eltex differ —
  don't reuse a Cisco command verbatim in an `eltex`-tagged episode without checking it's actually
  valid on that platform.
- **Rejected/dangerous-command episodes**: include some where the human rejects a `send_command`
  call. Represent the rejection as the tool result content: `"Command rejected by user, not sent:
  'reload'"` (matches the real string in `tools.py::execute_send_command`), followed by an assistant
  turn that reacts sensibly (asks what to do instead, or proposes a safer diagnostic step) — never
  one that just repeats the same rejected command.
- **No real secrets.** Scrub hostnames/IPs/passwords/SNMP community strings from any real capture
  before it goes in this file. Fine on a small dataset with few epochs, verbatim memorization risk is
  real — don't rely on the model "probably not repeating it back".
- **Keep tool outputs realistic in length.** Full `show tech-support` dumps are unrealistic to hand-
  author and will blow past context budget — trim to the relevant section, the same way an engineer
  would grep/filter, or use a `| include` / `| section` style command in the `send_command` call
  itself.

## Held-out eval set

Keep a separate file, `dataset/eval.jsonl` (same schema), with 30-50 scenarios that never appear in
the training file — mix of both vendors, plus a handful that should trigger the dangerous-command
denylist (`reload`, `erase`, `write erase`, etc.) so you can check the fine-tuned model still
volunteers those through `send_command` normally (the app's `safety.py` forces the confirmation
regardless of what the model does — you're checking the model doesn't develop weird avoidant or
over-eager behavior around them, not re-implementing the safety gate in the model itself).
