import { useTranslation } from "react-i18next";
import { NavLink, Route, Routes } from "react-router-dom";
import BackendBanner from "./components/BackendBanner";
import LanguageSwitcher from "./components/LanguageSwitcher";
import Authoring from "./pages/Authoring";
import Home from "./pages/Home";
import Pipeline from "./pages/Pipeline";
import PoseStudio from "./pages/PoseStudio";
import ScenarioBuilder from "./pages/ScenarioBuilder";
import Help from "./pages/Help";
import Jobs from "./pages/Jobs";
import Packages from "./pages/Packages";
import Settings from "./pages/Settings";
import Telemetry from "./pages/Telemetry";

export default function App() {
  const { t } = useTranslation();
  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>AUROSY Skill Factory</h1>
        <LanguageSwitcher />
        <nav>
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
          <NavLink to="/telemetry" className={({ isActive }) => (isActive ? "active" : "")}>
            {t("nav.telemetry")}
          </NavLink>
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
        <BackendBanner />
        <main>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/authoring" element={<Authoring />} />
            <Route path="/telemetry" element={<Telemetry />} />
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
