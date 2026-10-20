import type { ComponentType, ReactNode } from "react";
import {
  IconArrowUpRight,
  IconBulb,
  IconHammer,
  IconTelescope,
  IconWalk,
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

/** Welcome content only. The real chat owns the project, model, draft, and send action. */
export function ArkosLanding({
  heading,
  onSelectPrompt,
}: {
  heading: ReactNode;
  onSelectPrompt: (prompt: string) => void;
}) {
  return (
    <section className="arkos-welcome" aria-label="Get started">
      <AgentFaces />
      <h2 data-testid="empty-landing-heading">{heading}</h2>
      <p className="arkos-welcome-description">
        Plan, build, and understand your agents. Start with an idea.
      </p>
      <div className="arkos-prompt-grid">
        {prompts.map(({ icon: Icon, color, lines, prompt }) => (
          <button
            type="button"
            className={`arkos-prompt-card ${color}`}
            key={color}
            onClick={() => onSelectPrompt(prompt)}
          >
            <span className="arkos-prompt-card-top">
              <span className="arkos-prompt-icon-wrap">
                <Icon className="arkos-prompt-icon" aria-hidden="true" />
              </span>
              <IconArrowUpRight className="arkos-prompt-arrow" aria-hidden="true" />
            </span>
            <span>
              {lines[0]}
              <br />
              {lines[1]}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
