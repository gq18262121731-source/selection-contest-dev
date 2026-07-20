import { computed, ref, type Ref } from "vue";
import type { SessionUser } from "../api/client";

export type PageKey = "overview" | "topology" | "members" | "robot-follow" | "agent" | "family" | "debug" | "none";

const pageHash: Record<Exclude<PageKey, "none">, string> = {
  overview: "#/overview",
  topology: "#/topology",
  members: "#/members",
  "robot-follow": "#/robot-follow",
  agent: "#/agent",
  family: "#/family",
  debug: "#/debug",
};

const legacyHashes: Record<string, PageKey> = {
  "#/community": "overview",
  "#/relation": "members",
};

function resolveHash(hash: string): PageKey | undefined {
  if (!hash) return undefined;

  const modern = Object.entries(pageHash).find(([, value]) => value === hash)?.[0] as PageKey | undefined;
  if (modern) return modern;
  return legacyHashes[hash];
}

export function useHashRouting(sessionUser: Ref<SessionUser | null>) {
  const activePage = ref<PageKey>("none");
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
      return ["overview", "topology", "members", "robot-follow", "agent"];
    }
    return [];
  });

  let hashListener: (() => void) | null = null;

  function routeTo(page: PageKey) {
    if (page === "none") return;
    if (page === "debug" && !canAccessDebug.value) return;
    if (page !== "debug" && !allowedPages.value.includes(page)) return;
    activePage.value = page;
    routeToNonce.value += 1;
    window.location.hash = pageHash[page];
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
    window.location.hash = nextPage === "none" ? "" : pageHash[nextPage];
    hashListener = () => {
      const found = resolveHash(window.location.hash);
      if (!found) return;
      if (found === "debug") {
        if (canAccessDebug.value) activePage.value = found;
        return;
      }
      if (allowedPages.value.includes(found)) activePage.value = found;
    };
    window.addEventListener("hashchange", hashListener);
  }

  function disposeHashRouting() {
    if (hashListener) window.removeEventListener("hashchange", hashListener);
    hashListener = null;
  }

  function resetToDefaultPage() {
    activePage.value = "none";
    window.location.hash = "";
  }

  return {
    activePage,
    allowedPages,
    canAccessDebug,
    disposeHashRouting,
    initHashRouting,
    resetToDefaultPage,
    routeTo,
    routeToNonce,
  };
}
