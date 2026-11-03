/* Small pure helpers shared by the map UI and its Node tests. */
(function (root) {
  const GROUPS = ["Luzon", "Visayas", "Mindanao"];
  const sectorsFor = (project) => project?.sector || "general";

  function matchesRegion(project, region) {
    return !region || region === "all" || project?.island_group === region;
  }
  function matchesCategory(project, category) {
    if (!category || category === "all") return true;
    const sector = sectorsFor(project);
    if (category === "telecommunications") return sector === "telecommunications" || sector === "cross_sector";
    if (category === "energy") return sector === "energy" || sector === "cross_sector";
    if (category === "infrastructure") return sector === "general" || sector === "infrastructure";
    return false;
  }
  function matchesStatus(project, status) {
    if (!status || status === "all") return true;
    return status === "verified" ? project?.verification_status === "verified" : project?.verification_status !== "verified";
  }
  function hasReliableCoordinates(project) {
    const coords = project?.coordinates;
    if (!coords || coords.lat === null || coords.lat === "" || coords.lon === null || coords.lon === "" ||
        !Number.isFinite(Number(coords.lat)) || !Number.isFinite(Number(coords.lon))) return false;
    if (Number(coords.lat) < -90 || Number(coords.lat) > 90 || Number(coords.lon) < -180 || Number(coords.lon) > 180) return false;
    return (project.evidence || []).some((e) => e.supports_fields?.includes("coordinates") && /^https:\/\//i.test(e.url || "") && !!e.quote_or_fact);
  }
  function filterProjects(projects, filters = {}) {
    return (projects || []).filter((p) => matchesRegion(p, filters.region) && matchesCategory(p, filters.category) && matchesStatus(p, filters.status));
  }

  const api = { GROUPS, matchesRegion, matchesCategory, matchesStatus, hasReliableCoordinates, filterProjects };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.PHIWMapLogic = api;
})(globalThis);
