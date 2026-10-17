import { useCallback, useEffect, useState } from "react";

/**
 * Hash routing, deliberately.
 *
 * The app is a static bundle deployed as files, so a real path such as /app
 * would 404 on refresh unless the host rewrites every route to index.html. A
 * hash needs no server configuration and survives a hard refresh anywhere,
 * which matters more here than clean URLs.
 */
export type Route = "landing" | "dashboard";

const LANDING_HASH = "#/";
const DASHBOARD_HASH = "#/app";

function routeFromHash(hash: string): Route {
  return hash.replace(/^#/, "").startsWith("/app") ? "dashboard" : "landing";
}

export function useHashRoute(): [Route, () => void, () => void] {
  const [route, setRoute] = useState<Route>(() =>
    typeof window === "undefined" ? "landing" : routeFromHash(window.location.hash),
  );

  useEffect(() => {
    const onChange = () => setRoute(routeFromHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const goToDashboard = useCallback(() => {
    window.location.hash = DASHBOARD_HASH;
    setRoute("dashboard");
  }, []);

  const goToLanding = useCallback(() => {
    window.location.hash = LANDING_HASH;
    setRoute("landing");
  }, []);

  return [route, goToDashboard, goToLanding];
}