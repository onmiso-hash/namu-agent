import { Plugin } from "@opencode/plugin/tui"
type Context = Plugin.Context
import { spawn, spawnSync } from "node:child_process"
import { existsSync } from "node:fs"
import { homedir } from "node:os"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

// index.ts(백엔드 플러그인)의 resolveUv와 같은 로직이지만, 두 플러그인은 OpenCode가
// 따로 로드하는 별개 엔트리포인트라 모듈을 공유하지 않는다 — 작은 중복을 감수하고
// 이미 검증된 index.ts 쪽은 건드리지 않는다.
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

const pluginDir = dirname(fileURLToPath(import.meta.url))
const scriptPath = join(pluginDir, "active_task.py")

type NamuInfo = { version: string; folder: string; task: string }

// 디렉터리별로 한 번 떼어온 값을 잠깐 붙들어 둔다 — 상태줄은 거의 매 렌더(키 입력 등)마다
// 다시 그려지는데, 그때마다 uv 서브프로세스를 새로 띄우면 터미널이 끊겨 보인다.
const CACHE_TTL_MS = 15_000
const cache = new Map<string, { info: NamuInfo; at: number }>()
const pending = new Set<string>()

function fetchNamuInfo(directory: string): Promise<NamuInfo> {
  return new Promise((resolve) => {
    const fallback: NamuInfo = { version: "", folder: "?", task: "⚠ task 조회 오류" }
    let out = ""
    try {
      const child = spawn(resolveUv(), ["run", "--script", scriptPath], {
        stdio: ["pipe", "pipe", "ignore"],
      })
      child.stdout.on("data", (chunk) => {
        out += chunk.toString()
      })
      child.on("close", () => {
        try {
          const parsed = JSON.parse(out.trim() || "{}") as {
            version?: string
            folder?: string
            slug?: string
            title?: string
            error?: boolean
          }
          // 클로드 코드 상태줄(namu_statusline.py)과 같은 문구를 쓴다.
          let task = "진행 task 없음"
          if (parsed.error) task = "⚠ task 조회 오류"
          else if (parsed.slug)
            task = parsed.title && parsed.title !== parsed.slug
              ? `📌 ${parsed.slug} — ${parsed.title}`
              : `📌 ${parsed.slug}`
          resolve({ version: parsed.version ?? "", folder: parsed.folder || "?", task })
        } catch {
          resolve(fallback)
        }
      })
      child.on("error", () => resolve(fallback))
      child.stdin.write(JSON.stringify({ directory }))
      child.stdin.end()
    } catch {
      resolve(fallback)
    }
  })
}

export default Plugin.define({
  id: "namu-statusline",
  setup(context: Context) {
    const [state, setState] = context.storage.memory<{ info: NamuInfo | null }>("namu-statusline", {
      initial: { info: null },
    })

    function refresh() {
      const directory = context.location?.directory
      if (!directory) return
      const cached = cache.get(directory)
      if (cached && Date.now() - cached.at < CACHE_TTL_MS) {
        setState((d) => {
          d.info = cached.info
        })
        return
      }
      if (pending.has(directory)) return
      pending.add(directory)
      fetchNamuInfo(directory).then((info) => {
        pending.delete(directory)
        cache.set(directory, { info, at: Date.now() })
        setState((d) => {
          d.info = info
        })
      })
    }

    refresh()
    const interval = setInterval(refresh, CACHE_TTL_MS)

    // 지금 고른 모델의 이름과 대화 한도. 모델 목록에 없으면 모델 ID를 그대로 쓴다.
    function modelInfo(): { name: string; limit: number } {
      const current = context.ui.model.current()
      if (!current) return { name: "?", limit: 0 }
      const found = (context.data.location.model.list() ?? []).find(
        (m: any) => m?.providerID === current.providerID && (m?.id === current.modelID || m?.modelID === current.modelID),
      ) as any
      return {
        name: (found?.name as string) || current.modelID,
        limit: typeof found?.limit?.context === "number" ? found.limit.context : 0,
      }
    }

    // 대화 사용률 = 마지막 대답이 쓴 토큰 / 모델의 대화 한도. 첫 대답 전에는 "?"
    // (클로드 코드 상태줄과 같은 표시).
    const synced = new Set<string>()
    function contextPercent(sessionID: string | undefined, limit: number): string {
      if (!sessionID || !limit) return "?"
      const messages = context.data.session.message.list(sessionID) ?? []
      if (messages.length === 0 && !synced.has(sessionID)) {
        synced.add(sessionID)
        context.data.session.message.sync(sessionID).catch(() => {})
      }
      for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i] as any
        if (m?.type !== "assistant" || !m?.tokens) continue
        const t = m.tokens
        const used =
          (t.input ?? 0) + (t.output ?? 0) + (t.reasoning ?? 0) + (t.cache?.read ?? 0) + (t.cache?.write ?? 0)
        if (!used) continue
        return `${Math.round((used / limit) * 100)}%`
      }
      return "?"
    }

    function statusLine(sessionID: string | undefined): string {
      const info = state.info
      if (!info) return ""
      const model = modelInfo()
      const badge = info.version ? `[Namu ${info.version}] ` : ""
      return `${badge}[${model.name}] ${info.folder} | ${info.task} | ${contextPercent(sessionID, model.limit)}`
    }

    // 프롬프트 바닥줄(prompt.footer)은 단축키 안내와 한 가로줄을 나눠 써서 잘린다.
    // 그래서 대화 화면은 입력창 바로 위의 폭 전체 자리에, 첫 화면은 맨 아래 줄에 둔다.
    const unclaims = [
      context.ui.slot({
        prepend: "session.composer.top",
        render: (input) => (
          <box width="100%" paddingLeft={2}>
            <text>{statusLine(input.sessionID)}</text>
          </box>
        ),
      }),
      context.ui.slot({
        append: "home.footer.status",
        render: () => <text>{statusLine(undefined)}</text>,
      }),
    ]

    return () => {
      clearInterval(interval)
      for (const u of unclaims) u()
    }
  },
})
