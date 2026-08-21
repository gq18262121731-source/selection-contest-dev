import { computed, ref, type Ref } from "vue";
import type { SessionUser } from "../api/client";
import {
  buildRobotEmergencyHash,
  parseRobotEmergencyIncidentId,
  ROBOT_EMERGENCY_HASH,
} from "../utils/robotEmergencyPolicy";

export type PageKey = "overview" | "members" | "companion" | "robot-tasks" | "robot-status" | "robot-navigation" | "robot-emergency" | "robot-follow" | "report" | "agent" | "family" | "debug" | "none";

const pageHash: Record<Exclude<PageKey, "none">, string> = {
  overview: "#/overview",
  members: "#/members",
  companion: "#/companion",
  "robot-tasks": "#/robot-tasks",
  "robot-status": "#/robot-status",
  "robot-navigation": "#/robot-navigation",
  "robot-emergency": ROBOT_EMERGENCY_HASH,
  "robot-follow": "#/robot-follow",
  report: "#/report",
  agent: "#/agent",
  family: "#/family",
  debug: "#/debug",
};

const legacyHashes: Record<string, PageKey> = {
  "#/community": "overview",
  "#/relation": "members",
  "#/topology": "members",
};

function resolveHash(hash: string): PageKey | undefined {
  if (!hash) return undefined;

  const [path] = hash.split("?", 1);
  const modern = Object.entries(pageHash).find(([, value]) => value === path)?.[0] as PageKey | undefined;
  if (modern) return modern;
  return legacyHashes[path];
}

export function useHashRouting(sessionUser: Ref<SessionUser | null>) {
  const activePage = ref<PageKey>("none");
  const activeIncidentId = ref<string | null>(null);
  /**
   * Used to trigger "re-enter page" refresh behavior even when the hash
   * doesn't change (e.g. clicking the same nav item repeatedly).
   */
  const routeToNonce = ref(0);
  const canAccessDebug = computed(
    () => sessionUser.value?.role === "community" || sessionUser.value?.role === "admin",
  );
  const allowedPages = computed<PageKey[]>(() => {
    if (!sessionUser.value) return [];
    if (sessionUser.value.role === "family") return ["family"];
    if (sessionUser.value.role === "community" || sessionUser.value.role === "admin") {
      return ["overview", "members", "companion", "robot-tasks", "robot-status", "robot-navigation", "robot-follow", "robot-emergency", "report", "agent"];
    }
    return [];
  });

  let hashListener: (() => void) | null = null;

  function routeTo(page: PageKey) {
    if (page === "none") return;
    if (page === "robot-emergency") return;
    if (page === "debug" && !canAccessDebug.value) return;
    if (page !== "debug" && !allowedPages.value.includes(page)) return;
    activePage.value = page;
    activeIncidentId.value = null;
    routeToNonce.value += 1;
    window.location.hash = pageHash[page];
  }

  function routeToEmergency(incidentId: string) {
    if (!allowedPages.value.includes("robot-emergency")) return;
    activeIncidentId.value = incidentId;
    activePage.value = "robot-emergency";
    routeToNonce.value += 1;
    window.location.hash = buildRobotEmergencyHash(incidentId);
  }

  function initHashRouting() {
    const requested = resolveHash(window.location.hash);
    const fallback = sessionUser.value?.role === "family"
      ? "family"
      : sessionUser.value?.role === "community" || sessionUser.value?.role === "admin"
        ? "overview"
        : "none";
    const nextPage = requested && (requested === "debug" ? canAccessDebug.value : allowedPages.value.includes(requested))
      ? requested
      : fallback;

    activePage.value = nextPage;
    activeIncidentId.value = nextPage === "robot-emergency"
      ? parseRobotEmergencyIncidentId(window.location.hash)
      : null;
    if (nextPage !== "robot-emergency") {
      window.location.hash = nextPage === "none" ? "" : pageHash[nextPage];
    }
    hashListener = () => {
      const found = resolveHash(window.location.hash);
      if (!found) return;
      if (found === "debug") {
        if (canAccessDebug.value) activePage.value = found;
        return;
      }
      if (allowedPages.value.includes(found)) {
        activePage.value = found;
        activeIncidentId.value = found === "robot-emergency"
          ? parseRobotEmergencyIncidentId(window.location.hash)
          : null;
      }
    };
    window.addEventListener("hashchange", hashListener);
  }

  function disposeHashRouting() {
    if (hashListener) window.removeEventListener("hashchange", hashListener);
    hashListener = null;
  }

  function resetToDefaultPage() {
    activePage.value = "none";
    activeIncidentId.value = null;
    window.location.hash = "";
  }

  return {
    activePage,
    activeIncidentId,
    allowedPages,
    canAccessDebug,
    disposeHashRouting,
    initHashRouting,
    resetToDefaultPage,
    routeTo,
    routeToEmergency,
    routeToNonce,
  };
}
