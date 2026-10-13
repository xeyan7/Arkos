import { ServiceMap } from "effect";

export interface ProjectAgentReactorShape {
  readonly ready: true;
}

export class ProjectAgentReactor extends ServiceMap.Service<
  ProjectAgentReactor,
  ProjectAgentReactorShape
>()("arkos/projectAgent/Services/ProjectAgentReactor") {}
