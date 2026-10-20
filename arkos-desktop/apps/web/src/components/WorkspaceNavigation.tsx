import type { AppRailItem } from "./AppRail";
import { useSidebar } from "./ui/sidebar";

export function WorkspaceNavigation({
  items,
  label = "Workspace navigation",
}: {
  items: readonly AppRailItem[];
  label?: string;
}) {
  const { isMobile, setOpenMobile } = useSidebar();
  return (
    <nav aria-label={label} className="workspace-navigation">
      {items.map((item) => {
        const Icon = item.active ? item.glyphs.active : item.glyphs.idle;
        return (
          <button
            type="button"
            key={item.id}
            className="workspace-navigation-row"
            aria-current={item.active ? "page" : undefined}
            onClick={() => {
              item.onSelect();
              if (isMobile) setOpenMobile(false);
            }}
            onMouseEnter={item.onMouseEnter}
            onFocus={item.onFocus}
          >
            <span aria-hidden="true" className="workspace-navigation-icon">
              <Icon className="size-4" />
            </span>
            <span className="workspace-navigation-label">{item.label}</span>
            {item.badge ? (
              <span className="workspace-navigation-badge" aria-label={item.badge.accessibleLabel}>
                ●
              </span>
            ) : null}
          </button>
        );
      })}
    </nav>
  );
}
