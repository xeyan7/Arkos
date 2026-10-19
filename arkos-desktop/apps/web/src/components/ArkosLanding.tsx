import { useRef, useState, type ComponentType } from "react";
import {
  IconActivity,
  IconBox,
  IconBrandGithub,
  IconBulb,
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
  IconCircle,
  IconDeviceDesktop,
  IconFilter,
  IconFolder,
  IconHammer,
  IconInbox,
  IconLayoutSidebar,
  IconMicrophone,
  IconPaperclip,
  IconPlayerPlay,
  IconPlus,
  IconRocket,
  IconRobot,
  IconSearch,
  IconSend,
  IconSettings,
  IconShieldLock,
  IconSitemap,
  IconSparkles,
  IconSun,
  IconTelescope,
  IconWalk,
  IconX,
} from "@tabler/icons-react";
import "./ArkosLanding.css";

type LineIcon = ComponentType<{ size?: number; stroke?: number; className?: string }>;
const prompts: { icon: LineIcon; color: string; lines: [string, string]; prompt: string }[] = [
  {
    icon: IconBulb,
    color: "gold",
    lines: ["Plan an agent", "from an idea"],
    prompt: "Help me plan an agent from an idea. ",
  },
  {
    icon: IconHammer,
    color: "violet",
    lines: ["Build and modify", "your agent"],
    prompt: "Help me build and modify my agent. ",
  },
  {
    icon: IconTelescope,
    color: "green",
    lines: ["Explain what your", "agent is doing"],
    prompt: "Explain what my agent is doing. ",
  },
  {
    icon: IconWalk,
    color: "rose",
    lines: ["Trace an agent", "execution"],
    prompt: "Help me trace an agent execution. ",
  },
];
const recentChats = [
  "Feeling Unwell Today",
  "what is the best way to...",
  "Hi",
  "how do I set up a postg...",
  "How are you?",
];
const tools: [string, LineIcon][] = [
  ["Appearance", IconSun],
  ["Workflows", IconSitemap],
  ["Integrations", IconBox],
  ["Resources", IconSparkles],
  ["Connections", IconActivity],
  ["Deployments", IconRocket],
  ["Agents", IconRobot],
  ["GitHub", IconBrandGithub],
  ["Activity", IconActivity],
  ["Run history", IconPlayerPlay],
];

/** Small original vector mascots, matching the reference's overlapping illustrated badges. */
function AgentFaces() {
  return (
    <div className="arkos-agent-faces" aria-label="Your agent team">
      <svg viewBox="0 0 42 42" aria-hidden="true">
        <circle cx="21" cy="21" r="20" fill="#fafaf7" />
        <path d="M12 32 10 22 13 10 23 6 31 12 33 25 27 34Z" fill="#252724" />
        <path d="m17 13 9 1 3 8-4 9-7-3-3-8Z" fill="#fff" />
        <path
          d="m12 10 8 2-7 9 6-2-3 7 5 5-8 1M24 10l-3 7 7-3M20 22h2m4-2h2m-7 6 5 1"
          fill="none"
          stroke="#252724"
          strokeWidth="1.3"
        />
        <path d="m15 34 7-4 7 4" fill="none" stroke="#fff" strokeWidth="2" />
      </svg>
      <svg viewBox="0 0 42 42" aria-hidden="true">
        <circle cx="21" cy="21" r="20" fill="#e9a3c1" />
        <path d="M9 12h24v18H9z" fill="#fffafc" stroke="#333" />
        <path
          d="m9 26-4 6h32l-4-6M15 18h3m6 0h3m-11 5h10"
          fill="none"
          stroke="#333"
          strokeWidth="1.2"
        />
      </svg>
      <svg viewBox="0 0 42 42" aria-hidden="true">
        <circle cx="21" cy="21" r="20" fill="#e9eee6" />
        <path d="m5 20 32-11-9 25-8-10-7 6 2-9Z" fill="#fff" stroke="#3d4944" />
        <path d="m15 21 22-12-17 15v9" fill="none" stroke="#3d4944" />
      </svg>
      <svg viewBox="0 0 42 42" aria-hidden="true">
        <circle cx="21" cy="21" r="20" fill="#f4dfa0" />
        <rect x="7" y="11" width="28" height="22" rx="4" fill="#ffed9e" stroke="#4d4a35" />
        <path d="M7 17h28m-22 6 4 2 4-2m4 0 4 2 4-2m-15 5h9" fill="none" stroke="#4d4a35" />
        <path d="m26 8 3-4" stroke="#4d4a35" />
      </svg>
      <svg viewBox="0 0 42 42" aria-hidden="true">
        <circle cx="21" cy="21" r="20" fill="#f9f9f4" />
        <path d="m10 18 3-10 9-3 10 7 2 12-6 12-13-4Z" fill="#252724" />
        <path d="m15 14 10-3 5 9-4 12-8-3-4-9Z" fill="#fff" />
        <path
          d="m13 16 12-7-3 8 8-3m-12 6h3m4-1h3m-8 7 5 1m-9 3-5 6m15-6 4 7"
          fill="none"
          stroke="#252724"
          strokeWidth="1.4"
        />
      </svg>
      <svg viewBox="0 0 42 42" aria-hidden="true">
        <circle cx="21" cy="21" r="20" fill="#df854e" />
        <rect x="7" y="12" width="28" height="14" rx="4" fill="#fafafa" stroke="#30383c" />
        <rect x="10" y="15" width="9" height="7" rx="2" fill="#c8e0e5" stroke="#30383c" />
        <rect x="23" y="15" width="9" height="7" rx="2" fill="#c8e0e5" stroke="#30383c" />
        <path
          d="M19 18h4m-5 9v8h7v-8M21 12V7m-3 0h6"
          fill="none"
          stroke="#30383c"
          strokeWidth="1.4"
        />
      </svg>
    </div>
  );
}

export function ArkosLanding() {
  const [draft, setDraft] = useState("");
  const [project, setProject] = useState("Bruno");
  const [mode, setMode] = useState("Chat");
  const [fast, setFast] = useState(true);
  const [sidebar, setSidebar] = useState(true);
  const [searching, setSearching] = useState(false);
  const [search, setSearch] = useState("");
  const [notice, setNotice] = useState("");
  const [attachment, setAttachment] = useState("");
  const composer = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const fillDraft = (text: string) => {
    setDraft(text);
    setNotice("");
    composer.current?.focus();
  };
  const reset = () => {
    setDraft("");
    setNotice("");
    setAttachment("");
    composer.current?.focus();
  };

  return (
    <div className={`arkos-landing${sidebar ? "" : " arkos-sidebar-hidden"}`}>
      <aside className="arkos-home-sidebar" aria-label="Workspace navigation">
        <div className="arkos-sidebar-chrome drag-region">
          <button aria-label="Back" onClick={() => window.history.back()}>
            <IconChevronLeft />
          </button>
          <button aria-label="Forward" onClick={() => window.history.forward()}>
            <IconChevronRight />
          </button>
          <button aria-label="Hide sidebar" onClick={() => setSidebar(false)}>
            <IconLayoutSidebar />
          </button>
        </div>
        <div className="arkos-workspace-row">
          <button
            className="arkos-workspace-name"
            onClick={() => setNotice("You’re in Adarsh’s workspace.")}
          >
            Adarsh’s workspace <IconChevronDown />
          </button>
          <button aria-label="Search workspace" onClick={() => setSearching(!searching)}>
            <IconSearch />
          </button>
        </div>
        {searching && (
          <input
            className="arkos-workspace-search"
            autoFocus
            aria-label="Search projects and recent chats"
            placeholder="Search workspace…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        )}
        <nav className="arkos-primary-nav" aria-label="Main navigation">
          {(
            [
              ["New", IconPlus],
              ["Agents", IconRobot],
              ["Cockpit", IconDeviceDesktop],
              ["Inbox", IconInbox],
              ["Activity", IconActivity],
            ] as [string, LineIcon][]
          ).map(([label, Icon]) => (
            <button
              key={label}
              onClick={() =>
                label === "New"
                  ? reset()
                  : setNotice(
                      `${label} will be connected in the next phase. This preview covers the home screen.`,
                    )
              }
            >
              <Icon />
              <span>{label}</span>
              {label === "Inbox" && <span className="arkos-inbox-count">1</span>}
            </button>
          ))}
        </nav>
        <section className="arkos-sidebar-section" aria-label="Projects">
          <div className="arkos-section-heading">
            <span>Projects</span>
            <button aria-label="Filter projects" onClick={() => setSearching(!searching)}>
              <IconFilter />
            </button>
          </div>
          {[
            ["Bruno", "Billing"],
            ["Rowan", "Email Triage"],
          ]
            .filter((p) => p.join(" ").toLowerCase().includes(search.toLowerCase()))
            .map(([name, detail]) => (
              <button
                className="arkos-project-row"
                key={name}
                onClick={() => {
                  setProject(name!);
                  setNotice("");
                }}
                aria-pressed={project === name}
              >
                <span className={`arkos-project-avatar ${name === "Rowan" ? "rowan" : ""}`}>◈</span>
                <span>
                  {name}
                  <span className="arkos-project-detail"> · {detail}</span>
                </span>
              </button>
            ))}
        </section>
        <section className="arkos-sidebar-section arkos-recents" aria-label="Recent chats">
          <div className="arkos-section-heading">Recents</div>
          {recentChats
            .filter((chat) => chat.toLowerCase().includes(search.toLowerCase()))
            .map((chat) => (
              <button key={chat} onClick={() => fillDraft(chat)}>
                <IconCircle />
                <span>{chat}</span>
              </button>
            ))}
        </section>
        <button
          className="arkos-profile"
          onClick={() => setNotice("Adarsh Choudhary · Personal workspace")}
        >
          <span className="arkos-profile-avatar">A</span>
          <span>Adarsh Choudhary</span>
          <IconChevronDown />
        </button>
      </aside>

      <main className="arkos-home-main">
        <header className="arkos-home-header drag-region">
          {!sidebar && (
            <button aria-label="Show sidebar" onClick={() => setSidebar(true)}>
              <IconLayoutSidebar />
            </button>
          )}
          <IconDeviceDesktop />
          <button onClick={() => setNotice("Invoice Tracking Agent Planning · Home")}>
            Invoice Tracking Agent Planning <IconChevronDown />
          </button>
        </header>
        <div className="arkos-home-content">
          <section className="arkos-welcome" aria-label="Get started">
            <AgentFaces />
            <h1>What are we working on today, Adarsh?</h1>
            <div className="arkos-prompt-grid">
              {prompts.map(({ icon: Icon, color, lines, prompt }) => (
                <button className="arkos-prompt-card" key={color} onClick={() => fillDraft(prompt)}>
                  <Icon className={`arkos-prompt-icon ${color}`} />
                  <span>
                    {lines[0]}
                    <br />
                    {lines[1]}
                  </span>
                </button>
              ))}
            </div>
          </section>
          <div className="arkos-composer-area">
            {notice && (
              <div className="arkos-home-notice" role="status">
                <span>{notice}</span>
                <button aria-label="Dismiss message" onClick={() => setNotice("")}>
                  <IconX />
                </button>
              </div>
            )}
            <div className="arkos-composer-context">
              <IconFolder />
              <select
                aria-label="Active agent"
                value={project}
                onChange={(e) => setProject(e.target.value)}
              >
                <option>Bruno</option>
                <option>Rowan</option>
              </select>
              <span className="arkos-connected-apps" aria-label="Connected apps">
                <span>✣</span>
                <span>ϟ</span>
                <span>◈</span>
              </span>
            </div>
            <form
              className="arkos-home-composer"
              onSubmit={(e) => {
                e.preventDefault();
                if (draft.trim())
                  setNotice(
                    "Your draft is ready. Agent execution is not connected in this frontend preview.",
                  );
              }}
            >
              {attachment && (
                <div className="arkos-attachment">
                  <IconPaperclip />
                  {attachment}
                  <button
                    type="button"
                    aria-label="Remove attachment"
                    onClick={() => setAttachment("")}
                  >
                    <IconX />
                  </button>
                </div>
              )}
              <textarea
                ref={composer}
                aria-label={`Describe what ${project} should do`}
                placeholder={`Describe what ${project} should do.`}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
              <div className="arkos-composer-toolbar">
                <div className="arkos-composer-tools">
                  <button
                    type="button"
                    aria-label="Attach file"
                    onClick={() => fileInput.current?.click()}
                  >
                    <IconPaperclip />
                  </button>
                  <input
                    type="file"
                    ref={fileInput}
                    hidden
                    onChange={(e) => setAttachment(e.target.files?.[0]?.name ?? "")}
                  />
                  <button
                    type="button"
                    aria-label="Agent settings"
                    onClick={() => setNotice("Agent settings will be connected in the next phase.")}
                  >
                    <IconSettings />
                  </button>
                  <button
                    className="arkos-speed"
                    type="button"
                    aria-pressed={fast}
                    onClick={() => setFast(!fast)}
                  >
                    <IconShieldLock />
                    {fast ? "Fast" : "Standard"}
                  </button>
                </div>
                <div className="arkos-composer-options">
                  <label className="arkos-model">
                    <span>✺</span>
                    <select aria-label="Model">
                      <option>Sonnet 5</option>
                      <option>Opus 4.6</option>
                      <option>GPT-5.4</option>
                    </select>
                    <IconChevronDown />
                  </label>
                  <div className="arkos-mode" aria-label="Conversation mode">
                    {["Chat", "Test"].map((item) => (
                      <button
                        type="button"
                        key={item}
                        aria-pressed={mode === item}
                        onClick={() => setMode(item)}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    aria-label="Voice input"
                    onClick={() => setNotice("Voice input will be connected in the next phase.")}
                  >
                    <IconMicrophone />
                  </button>
                  <button
                    type="submit"
                    className="arkos-send"
                    aria-label="Send message"
                    disabled={!draft.trim()}
                  >
                    <IconSend />
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      </main>
      <aside className="arkos-home-rail" aria-label="Workspace tools">
        <button aria-label="Toggle sidebar" onClick={() => setSidebar(!sidebar)}>
          <IconLayoutSidebar />
        </button>
        <div>
          {tools.map(([label, Icon]) => (
            <button
              key={label}
              aria-label={label}
              title={label}
              onClick={() => setNotice(`${label} will be connected in the next phase.`)}
            >
              <Icon />
            </button>
          ))}
        </div>
      </aside>
    </div>
  );
}
