
import type { ProviderKind } from "@arkos/contracts";
import type { ReactNode, SVGProps } from "react";
import { ArkosLogo } from "./ArkosLogo";
import { cn } from "~/lib/utils";
export type ProviderIconTone = "default" | "header";
export const PROVIDER_ICON_COMPONENT_BY_PROVIDER = { arkos: ArkosLogo } satisfies Record<ProviderKind, typeof ArkosLogo>;
export function providerIconToneClassName(_provider: ProviderKind | null | undefined, _tone: ProviderIconTone = "default") { return "text-foreground"; }
export type ProviderIconProps = Omit<SVGProps<SVGSVGElement>, "ref"> & { provider: ProviderKind | null | undefined; fallback?: ReactNode; tone?: ProviderIconTone };
export function ProviderIcon({provider, fallback = null, tone: _tone, className, ...props}: ProviderIconProps) {
 return provider ? <ArkosLogo {...props} className={cn("text-foreground", className)} /> : fallback;
}
export function ProviderOptionLabel({provider, label, className, iconClassName}: {provider: ProviderKind; label: ReactNode; className?: string; iconClassName?: string}) {
 return <span className={cn("flex min-w-0 items-center gap-2",className)}><ProviderIcon provider={provider} className={cn("size-3.5",iconClassName)}/><span className="min-w-0 truncate">{label}</span></span>;
}
