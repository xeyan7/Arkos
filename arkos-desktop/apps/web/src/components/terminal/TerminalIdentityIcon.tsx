import type {TerminalIconKey} from "@arkos/shared/terminalThreads";
import {TerminalIcon} from "~/lib/icons";import {cn} from "~/lib/utils";
export default function TerminalIdentityIcon({className}:{iconKey:TerminalIconKey;className?:string}){return <span className={cn("inline-flex shrink-0 items-center justify-center",className)}><TerminalIcon className="size-full text-[var(--color-text-foreground)]"/></span>;}
