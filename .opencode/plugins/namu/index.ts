import { Plugin } from "@opencode/plugin"
import { spawn, spawnSync } from "node:child_process"
import { existsSync, readFileSync, statSync } from "node:fs"
import { homedir } from "node:os"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const SERVER_NAME = "namu-memory"
const SKILL_IDS = ["namu", "namu-task", "namu-update"]
const BRIEFED_TTL_MS = 7 * 24 * 60 * 60 * 1000
const FIRST_SESSION_BUNDLE_CAP = 8000

// closing_guard.py와 같은 마무리 신호 판정 (정규식·40자 상한·물음표 제외).
const CLOSING_RE =
  /(마무리|마치자|끝내자|끝냅|세션\s*(을\s*|은\s*)?종료|세션\s*끝|오늘은?\s*여기까지|그만하자|wrap\s*up|접자)/i
const CLOSING_SIGNAL_MAX_LEN = 40

function isClosingSignal(text: string): boolean {
  const t = text.trim()
  if (!t || t.length > CLOSING_SIGNAL_MAX_LEN) return false
  if (t.endsWith("?") || t.endsWith("？")) return false
  return CLOSING_RE.test(t)
}

let cachedUv: string | null = null

function resolveUv(): string {
  if (cachedUv) return cachedUv
  try {
    const found = spawnSync("sh", ["-c", "command -v uv"], { encoding: "utf-8" })
    const bin = (found.stdout ?? "").toString().trim().split("\n")[0]?.trim()
    if (found.status === 0 && bin) {
      cachedUv = bin
      return bin
    }
  } catch {
    // fall through
  }
  const homeUv = join(homedir(), ".local", "bin", "uv")
  cachedUv = existsSync(homeUv) ? homeUv : "uv"
  return cachedUv
}

function runHookScript(args: {
  script: string
  argv?: string[]
  stdinJson: unknown
  cwd: string
  repoRoot: string
  timeoutMs: number
}): Promise<string> {
  // spawnSync를 쓰면 스크립트가 도는 동안 opencode 서버 전체(다른 세션 포함)가 멈춘다.
  return new Promise((resolve) => {
    let stdout = ""
    let settled = false
    const done = (text: string) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(text.trim())
    }
    let child: ReturnType<typeof spawn>
    try {
      child = spawn(resolveUv(), ["run", "--script", args.script, ...(args.argv ?? [])], {
        cwd: args.cwd,
        env: {
          ...process.env,
          CLAUDE_PROJECT_DIR: args.cwd,
          NAMU_REPO_ROOT: args.repoRoot,
          PYTHONIOENCODING: "utf-8",
        },
        stdio: ["pipe", "pipe", "ignore"],
      })
    } catch {
      resolve("")
      return
    }
    const timer = setTimeout(() => {
      child.kill("SIGKILL")
      done("")
    }, args.timeoutMs)
    child.stdout?.setEncoding("utf-8")
    child.stdout?.on("data", (chunk: string) => {
      stdout += chunk
    })
    child.on("error", () => done(""))
    child.on("close", () => done(stdout))
    child.stdin?.on("error", () => {})
    child.stdin?.end(JSON.stringify(args.stdinJson ?? {}))
  })
}

function tryParseJson(text: string): any | null {
  const t = text.trim()
  if (!t.startsWith("{")) return null
  try {
    return JSON.parse(t)
  } catch {
    return null
  }
}

/** 훅 스크립트 stdout에서 모델에 닿을 본문을 뽑는다 (JSON 봉투 또는 날 markdown). */
function hookText(stdout: string): string {
  const parsed = tryParseJson(stdout)
  if (parsed) {
    const specific = parsed.hookSpecificOutput ?? {}
    const text =
      specific.additionalContext ?? parsed.systemMessage ?? parsed.reason ?? ""
    if (typeof text === "string" && text.trim()) return text.trim()
    return ""
  }
  return stdout.trim()
}

function parseSkillFile(dir: string): { name: string; description: string; body: string } | null {
  const file = join(dir, "SKILL.md")
  if (!existsSync(file)) return null
  const raw = readFileSync(file, "utf-8")
  const match = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/)
  if (!match) return null
  let name = ""
  let description = ""
  for (const line of match[1].split("\n")) {
    const m = line.match(/^(\w+):\s*(.*)$/)
    if (!m) continue
    if (m[1] === "name") name = m[2].trim()
    if (m[1] === "description") description = m[2].trim()
  }
  return { name, description, body: match[2].trim() }
}

function userTexts(info: any): { text: string; at: number | null }[] {
  const out: { text: string; at: number | null }[] = []
  const role = info?.info?.role ?? info?.role
  if (role !== "user") return out
  const atRaw = info?.info?.time?.created ?? info?.time?.created ?? null
  const at = typeof atRaw === "number" ? atRaw : null
  const parts = info?.parts ?? info?.info?.parts ?? []
  const texts: string[] = []
  if (Array.isArray(parts)) {
    for (const part of parts) {
      if (part?.type === "text" && typeof part?.text === "string" && part.text.trim()) {
        texts.push(part.text)
      }
    }
  } else if (typeof parts === "string" && parts.trim()) {
    texts.push(parts)
  }
  const text = texts.join("\n").trim()
  // 도구 결과만 든 항목은 사람 발화로 세지 않는다 (closing_guard와 같은 기준).
  if (text) out.push({ text, at })
  return out
}

export default Plugin.define({
  id: "namu",
  async setup(ctx) {
    // ctx.location.directory는 플러그인 폴더가 아니라 사용자가 연 프로젝트 폴더다.
    const pluginDir = dirname(fileURLToPath(import.meta.url))
    const options = (ctx.options ?? {}) as Record<string, unknown>
    const repoRoot =
      typeof options.repoRoot === "string" && options.repoRoot
        ? options.repoRoot
        : join(pluginDir, "..", "..", "..")
    const namuPluginDir = join(repoRoot, "namu-plugin")
    const hooksDir = join(namuPluginDir, "hooks")
    const skillsDir = join(namuPluginDir, "skills")
    const mcpServer = join(namuPluginDir, "mcp_server.py")
    const closingCheck = join(pluginDir, "closing_check.py")

    if (!existsSync(mcpServer)) {
      console.error(`[namu] memory server not found at ${mcpServer} (repoRoot=${repoRoot})`)
      return
    }

    // 1. 기억 서버 등록 (Claude Code 플러그인과 같은 서버 — 도구 전부 노출).
    await ctx.mcp.transform((editor) => {
      editor.set(SERVER_NAME, {
        type: "local",
        command: [resolveUv(), "run", "--script", mcpServer],
        timeout: { startup: 120000 },
      })
    })

    // 2. 스킬 등록 (파일을 미리 읽어 transform에 넘긴다).
    const skills = SKILL_IDS.map((id) => ({ id, ...parseSkillFile(join(skillsDir, id)) })).filter(
      (s) => s.body && s.description,
    )
    if (skills.length > 0) {
      await ctx.skill.transform((editor) => {
        for (const s of skills) {
          editor.add({
            id: s.id,
            name: s.name || s.id,
            description: s.description as string,
            path: join(skillsDir, s.id),
            content: s.body as string,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
          } as any)
        }
      })
    } else {
      console.error(`[namu] no skills found under ${skillsDir}`)
    }

    // 3. 명령 등록 (/namu · /namu-task · /namu-update).
    const skillDirective = (id: string, extra: string) =>
      `ID가 \`${id}\`인 스킬을 skill 도구로 불러온 뒤, 그 절차대로 수행하라.${extra}`
    await ctx.command.transform((editor) => {
      editor.add({
        name: "namu",
        description: "NAMU 세션 브리핑 — 쪽지·열린 작업·관련 교훈을 정해진 형식으로 보여준다",
        execute: async ({ sessionID, prompt, delivery }) => {
          await ctx.session.prompt({
            ...prompt,
            sessionID,
            text: `${skillDirective("namu", "")}${prompt.text ? `\n\n추가 요청: ${prompt.text}` : ""}`,
            delivery,
          })
        },
      })
      editor.add({
        name: "namu-task",
        description: "NAMU 멀티스텝 작업 오케스트레이션 — recall→분할→코딩→검수→사용자 게이트→record",
        execute: async ({ sessionID, prompt, delivery }) => {
          await ctx.session.prompt({
            ...prompt,
            sessionID,
            text: `${skillDirective("namu-task", " 코딩은 `namu-coder` 서브에이전트, 검수는 `namu-reviewer` 서브에이전트에게 맡긴다. 검수 fail이면 자동 재실행하지 말고 사용자에게 ① 재실행(횟수 입력) / ② 통과 처리 / ③ 중단 중 선택을 물어본다.")}${prompt.text ? `\n\n작업 대상: ${prompt.text}` : ""}`,
            delivery,
          })
        },
      })
      editor.add({
        name: "namu-update",
        description: "NAMU 플러그인 원클릭 업데이트",
        execute: async ({ sessionID, prompt, delivery }) => {
          await ctx.session.prompt({
            ...prompt,
            sessionID,
            text: `${skillDirective("namu-update", "")}${prompt.text ? `\n\n추가 요청: ${prompt.text}` : ""}`,
            delivery,
          })
        },
      })
    })

    const sessionDir = async (sessionID: string): Promise<string> => {
      try {
        const session = await ctx.session.get({ sessionID })
        const dir = (session as any)?.location?.directory
        if (typeof dir === "string" && dir) return dir
      } catch {
        // fall through
      }
      return process.cwd()
    }

    // 4. 세션 첫 호출 묶음: 브리핑 + 저장소 뒤처짐 + 판 드리프트 + 주간 점검.
    //    (Claude Code SessionStart 훅 묶음에 대응. OpenCode에 세션 시작 훅이
    //    없어 첫 모델 호출 때 한 번만 주입한다.)
    await ctx.session.hook("context", async (event) => {
      try {
        const seenKey = `namu:briefed:${event.sessionID}`
        let seenAt = 0
        try {
          const seen = (await ctx.storage.get(seenKey)) as { at?: number } | undefined
          if (seen && typeof seen.at === "number") seenAt = seen.at
        } catch {
          seenAt = 0
        }
        if (Date.now() - seenAt > BRIEFED_TTL_MS) {
          const dir = await sessionDir(event.sessionID)
          const common = {
            session_id: event.sessionID,
            cwd: dir,
            hook_event_name: "SessionStart",
          }
          // 서로 기다릴 이유가 없으니 동시에 돌리고, 순서(브리핑 먼저)는 결과를 모을 때 지킨다.
          const scripts: [string, number][] = [
            ["session_recall.py", 90000],
            ["repo_sync_check.py", 60000],
            ["version_drift_check.py", 60000],
            ["weekly_review_check.py", 60000],
          ]
          const outs = await Promise.all(
            scripts.map(([script, timeoutMs]) =>
              runHookScript({ script: join(hooksDir, script), stdinJson: common, cwd: dir, repoRoot, timeoutMs }),
            ),
          )
          const parts = outs.map(hookText).filter((text) => text)
          const bundle = parts.join("\n\n").slice(0, FIRST_SESSION_BUNDLE_CAP)
          if (bundle) event.system.push({ type: "text", text: bundle })
          try {
            await ctx.storage.set(seenKey, { at: Date.now() })
          } catch {
            // 저장 실패는 다음 호출 때 다시 시도하면 된다.
          }
        }

        // 5. 상시 주의 재알림 (UserPromptSubmit 훅에 대응 — 매 모델 호출 직전에 주입).
        const reminder = await namuReminder(hooksDir, repoRoot)
        if (reminder) event.system.push({ type: "text", text: reminder })
      } catch (error) {
        console.error("[namu] context hook failed:", error)
      }
    })

    // 6. 마무리 검사 (Stop 훅에 대응 — OpenCode에 세션 종료 훅이 없어 권고로만 동작).
    await ctx.session.hook("prompt", async (event) => {
      try {
        const text = event.prompt.text ?? ""
        if (!isClosingSignal(text)) return
        const dir = await sessionDir(event.sessionID)
        const history = await ctx.session.context({ sessionID: event.sessionID }).catch(() => [])
        const said: { text: string; at: number | null }[] = []
        for (const item of history ?? []) {
          said.push(...userTexts(item))
        }
        said.push({ text: text.trim(), at: Date.now() })
        let sinceMs = 0
        try {
          const session = await ctx.session.get({ sessionID: event.sessionID })
          sinceMs = toMs((session as any)?.time?.created)
        } catch {
          sinceMs = 0
        }
        const resumedAt = previousClosingResumeMs(said)
        if (resumedAt !== null) sinceMs = Math.max(sinceMs, resumedAt)
        if (!sinceMs) {
          // 세션 시작 시각을 모르면 가장 이른 사람 발화, 그것도 없으면 지금부터 본다.
          // 모른다고 epoch(1970)부터 보면 옛 [다음] 줄이 근거가 되어 항상 통과해 버린다.
          const first = said.find((s) => s.at !== null)
          sinceMs = first?.at ?? Date.now()
        }
        const out = await runHookScript({
          script: closingCheck,
          stdinJson: { since_epoch_ms: sinceMs },
          cwd: dir,
          repoRoot,
          timeoutMs: 30000,
        })
        const parsed = tryParseJson(out) ?? { touched: [], satisfied: [] }
        const satisfied: string[] = Array.isArray(parsed.satisfied) ? parsed.satisfied : []
        if (satisfied.length > 0) return
        const touched: string[] = Array.isArray(parsed.touched) ? parsed.touched : []
        const note =
          `[나무 마무리 검사] 이번 세션의 작업일지에 [다음]/[완료]/[중단] 줄이 없습니다` +
          (touched.length > 0 ? `(기록이 들어간 task: ${touched.join(", ")})` : "(이번 세션에 남긴 줄이 아예 없습니다)") +
          `. 마무리의 본체는 [다음] 줄 갱신이므로, namu_record(bowl='tasks', status='다음', summary='<다음 세션이 어디서 시작하면 되는지>', reason='<왜>', body='<요약>')로 남기거나 남길 일이 없으면 그렇게 답한 뒤, 사용자에게 확인받고 마치세요.`
        event.prompt.text = `${text}\n\n${note}`
      } catch (error) {
        console.error("[namu] prompt hook failed:", error)
      }
    })

    // 7. 고치기 전 저장소 뒤처짐 검사 (PreToolUse 훅에 대응 — 뒤처져 있으면 묻는다).
    await ctx.permission.hook("evaluate", async (event) => {
      try {
        if (event.action !== "edit" || event.effect === "deny") return
        const target = (event.resources ?? []).find(
          (r) => typeof r === "string" && r.includes("/"),
        )
        if (!target) return
        const dir = await sessionDir(event.sessionID)
        const out = await runHookScript({
          script: join(hooksDir, "repo_sync_check.py"),
          argv: ["pretool"],
          stdinJson: { tool_input: { file_path: target } },
          cwd: dir,
          repoRoot,
          timeoutMs: 20000,
        })
        const parsed = tryParseJson(out)
        const reason = parsed?.hookSpecificOutput?.permissionDecisionReason
        if (typeof reason === "string" && reason.trim()) {
          event.effect = "ask"
          event.message = reason.trim()
        }
      } catch (error) {
        console.error("[namu] permission hook failed:", error)
      }
    })
  },
})

let reminderCache: { mtimeMs: number; text: string } | null = null

async function namuReminder(hooksDir: string, repoRoot: string): Promise<string> {
  try {
    const profileYaml = join(homedir(), ".namu", "memory", "profile.yaml")
    let mtimeMs = 0
    try {
      mtimeMs = statSync(profileYaml).mtimeMs
    } catch {
      return ""
    }
    if (reminderCache && reminderCache.mtimeMs === mtimeMs) return reminderCache.text
    const out = await runHookScript({
      script: join(hooksDir, "prompt_reminder.py"),
      stdinJson: {},
      cwd: process.cwd(),
      repoRoot,
      timeoutMs: 15000,
    })
    const text = hookText(out)
    reminderCache = { mtimeMs, text }
    return text
  } catch {
    return ""
  }
}

/** 세션 시작 시각을 epoch ms로. 모르면 0 (호출 쪽에서 대체 기준을 쓴다). */
function toMs(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (typeof value === "string" && value) {
    const parsed = Date.parse(value)
    return Number.isFinite(parsed) ? parsed : 0
  }
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value.getTime()
  return 0
}

/** 이어 연 긴 세션에서 앞선 마무리 뒤 일이 다시 시작된 시각 (closing_guard와 같은 규칙). */
function previousClosingResumeMs(said: { text: string; at: number | null }[]): number | null {
  const earlier = said.slice(0, -1)
  for (let i = earlier.length - 1; i >= 0; i--) {
    if (!isClosingSignal(earlier[i].text)) continue
    const resumed = earlier[i + 1] ?? earlier[i]
    return resumed.at
  }
  return null
}
