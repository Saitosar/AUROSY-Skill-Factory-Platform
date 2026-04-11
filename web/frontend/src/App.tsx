import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import Authoring from "./pages/Authoring";
import Home from "./pages/Home";
import Pipeline from "./pages/Pipeline";
import PoseStudio from "./pages/PoseStudio";
import ScenarioBuilder from "./pages/ScenarioBuilder";
import Help from "./pages/Help";
import Jobs from "./pages/Jobs";
import Packages from "./pages/Packages";
import Settings from "./pages/Settings";

const SIDEBAR_OPEN_KEY = "skill-factory-sidebar-open";

function readSidebarOpen(): boolean {
  try {
    const v = localStorage.getItem(SIDEBAR_OPEN_KEY);
    if (v === null) return true;
    return v !== "0";
  } catch {
    return true;
  }
}

export default function App() {
  const { t } = useTranslation();
  const [sidebarOpen, setSidebarOpen] = useState(readSidebarOpen);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_OPEN_KEY, sidebarOpen ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [sidebarOpen]);

  return (
    <div className={`layout${sidebarOpen ? "" : " layout--sidebar-collapsed"}`}>
      <aside className="sidebar" aria-hidden={!sidebarOpen}>
        <div className="sidebar-header">
          <h1>AUROSY Skill Factory</h1>
          <button
            type="button"
            className="sidebar-collapse-btn"
            onClick={() => setSidebarOpen(false)}
            aria-expanded={sidebarOpen}
            aria-controls="app-sidebar-nav"
          >
            {t("nav.hideMenu")}
          </button>
        </div>
        <nav id="app-sidebar-nav">
          <NavLink end to="/" className={({ isActive }) => (isActive ? "active" : "")}>
            {t("nav.home")}
          </NavLink>
          <NavLink to="/authoring" className={({ isActive }) => (isActive ? "active" : "")}>
            {t("nav.authoring")}
          </NavLink>
          <NavLink to="/pose" className={({ isActive }) => (isActive ? "active" : "")}>
            {t("nav.poseStudio")}
          </NavLink>
          <NavLink to="/scenarios" className={({ isActive }) => (isActive ? "active" : "")}>
            {t("nav.scenarios")}
          </NavLink>
          <NavLink to="/pipeline" className={({ isActive }) => (isActive ? "active" : "")}>
            {t("nav.pipeline")}
          </NavLink>
          <div className="sidebar-nav-group-label" id="sidebar-platform-label">
            {t("nav.platformSection")}
          </div>
          <div className="sidebar-nav-group" role="group" aria-labelledby="sidebar-platform-label">
            <NavLink to="/jobs" className={({ isActive }) => (isActive ? "active" : "")}>
              {t("nav.jobs")}
            </NavLink>
            <NavLink to="/packages" className={({ isActive }) => (isActive ? "active" : "")}>
              {t("nav.packages")}
            </NavLink>
          </div>
          <hr className="sidebar-nav-divider" aria-hidden />
          <NavLink to="/help" className={({ isActive }) => (isActive ? "active" : "")}>
            {t("nav.help")}
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => (isActive ? "active" : "")}>
            {t("nav.settings")}
          </NavLink>
        </nav>
      </aside>
      <div className="layout-content">
        {!sidebarOpen && (
          <button
            type="button"
            className="sidebar-floating-open"
            onClick={() => setSidebarOpen(true)}
            aria-expanded={sidebarOpen}
            aria-controls="app-sidebar-nav"
          >
            {t("nav.showMenu")}
          </button>
        )}
        <main>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/authoring" element={<Authoring />} />
            <Route path="/telemetry" element={<Navigate to="/pose" replace />} />
            <Route path="/scenarios" element={<ScenarioBuilder />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/jobs/:jobId" element={<Jobs />} />
            <Route path="/packages" element={<Packages />} />
            <Route path="/pose" element={<PoseStudio />} />
            <Route path="/help" element={<Help />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
