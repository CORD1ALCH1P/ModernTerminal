interface Rule {
  regex: RegExp
  sgr: string
}

// Ordered by priority: earlier rules win when spans overlap.
const RULES: Rule[] = [
  // Cisco-style prompts: "Router#", "Router>", "Switch(config-if)#"
  { regex: /^[A-Za-z0-9_.-]{1,32}(?:\([\w./-]{1,32}\))?[>#](?=\s|$)/, sgr: '1;35' },
  // Linux-style prompts: "user@host:~$", "user@host:/etc#"
  { regex: /^[\w.-]+@[\w.-]+:[^\s#$]*[#$](?=\s|$)/, sgr: '1;35' },
  // IPv4 addresses
  {
    regex: /\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b/g,
    sgr: '36',
  },
  // Cisco-style MAC (aabb.ccdd.eeff)
  { regex: /\b[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\b/g, sgr: '35' },
  // Standard MAC (aa:bb:cc:dd:ee:ff)
  { regex: /\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b/g, sgr: '35' },
  // Cisco interface names
  {
    regex:
      /\b(?:GigabitEthernet|TenGigabitEthernet|FortyGigE|HundredGigE|FastEthernet|Ethernet|Loopback|Vlan|Serial|Port-channel|Tunnel|Async|Management|Null)\d+(?:\/\d+){0,3}(?:\.\d+)?\b/gi,
    sgr: '34',
  },
  // Negative / down / error states
  {
    regex:
      /\b(?:down|disabled|deny|denied|fail(?:ed|ure)?|error|err-disabled|shutdown|inactive|dead|critical|unreachable|timeout|timed out|refused|not found)\b/gi,
    sgr: '31',
  },
  // Positive / up / ok states
  {
    regex:
      /\b(?:up|enabled|permit(?:ted)?|success(?:ful)?|active|running|connected|established|forwarding|available|ok)\b/gi,
    sgr: '32',
  },
  // Warnings
  { regex: /\b(?:warn(?:ing)?s?|degraded|standby|blocked|blocking|notice|pending)\b/gi, sgr: '33' },
]

interface Span {
  start: number
  end: number
  sgr: string
  priority: number
}

function findSpans(line: string): Span[] {
  const candidates: Span[] = []
  RULES.forEach((rule, priority) => {
    const regex = rule.regex
    if (regex.global) {
      regex.lastIndex = 0
      let match: RegExpExecArray | null
      while ((match = regex.exec(line))) {
        if (match[0].length === 0) {
          regex.lastIndex++
          continue
        }
        candidates.push({ start: match.index, end: match.index + match[0].length, sgr: rule.sgr, priority })
      }
    } else {
      const match = regex.exec(line)
      if (match && match[0].length > 0) {
        candidates.push({ start: match.index, end: match.index + match[0].length, sgr: rule.sgr, priority })
      }
    }
  })

  // Higher-priority (earlier-listed) rules win overlaps, regardless of position.
  candidates.sort((a, b) => a.priority - b.priority || a.start - b.start)
  const selected: Span[] = []
  for (const candidate of candidates) {
    const overlaps = selected.some((s) => candidate.start < s.end && s.start < candidate.end)
    if (!overlaps) selected.push(candidate)
  }
  selected.sort((a, b) => a.start - b.start)
  return selected
}

function highlightLine(line: string): string {
  const spans = findSpans(line)
  if (spans.length === 0) return line

  let result = ''
  let cursor = 0
  for (const span of spans) {
    result += line.slice(cursor, span.start)
    result += `\x1b[${span.sgr}m${line.slice(span.start, span.end)}\x1b[0m`
    cursor = span.end
  }
  result += line.slice(cursor)
  return result
}

/**
 * MobaXterm-style keyword highlighting (interface up/down states, IPs, MACs,
 * Cisco interface names, prompts) for a decoded chunk of terminal output.
 * Skips any chunk that already contains an escape sequence -- e.g. `ls
 * --color`, a colored prompt, or a full-screen app like vim/top/less -- so
 * this never fights with or corrupts existing ANSI styling/cursor addressing.
 */
export function highlightChunk(text: string): string {
  if (text.length === 0 || text.includes('\x1b')) return text
  return text.split('\n').map(highlightLine).join('\n')
}

/**
 * Wraps a byte stream from a terminal connection, injecting ANSI color codes
 * around recognized patterns before the bytes reach xterm.js. Falls back to
 * passing bytes through unchanged for anything that isn't valid UTF-8 (e.g. a
 * binary file transfer) -- decoding is one-way once that happens, so this
 * disables itself for the rest of the connection rather than risk corrupting
 * binary data.
 */
export function createOutputHighlighter() {
  const decoder = new TextDecoder('utf-8', { fatal: true })
  const encoder = new TextEncoder()
  let disabled = false

  return function highlight(bytes: Uint8Array): Uint8Array {
    if (disabled) return bytes
    let text: string
    try {
      text = decoder.decode(bytes, { stream: true })
    } catch {
      disabled = true
      return bytes
    }
    if (text.length === 0) return bytes
    const highlighted = highlightChunk(text)
    if (highlighted === text) return bytes
    return encoder.encode(highlighted)
  }
}
