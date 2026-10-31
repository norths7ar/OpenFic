import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Routes, Route, useParams } from "react-router";

import App from "../App.tsx";
import { AppLayout } from "../features/app-shell";
import { DiscussionPage } from "../features/assistant";
import { CharactersPage } from "../features/characters";
import { PendingProjectChangesPage } from "../features/pending-project-changes";
import { PromptChainsPage } from "../features/prompt-chains";
import { WorldInfoPage } from "../features/world-info";
import { DocumentWorkspacePage, WritingPage } from "../features/writing";

const DashboardPage = lazy(() =>
  import("../features/dashboard/pages/dashboard-page").then((module) => ({
    default: module.DashboardPage,
  })),
);

function ProjectRouteRedirect() {
  const { projectId } = useParams<{ projectId: string }>();
  return (
    <Navigate
      to={`/projects/${projectId}/write`}
      replace
    />
  );
}

export function AppRoutes({
  appearance,
  version,
  setAppearance,
}: {
  appearance: "light" | "dark";
  version: string;
  setAppearance: (appearance: "light" | "dark") => void;
}) {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          element={
            <AppLayout
              appearance={appearance}
              version={version}
              onAppearanceChange={setAppearance}
            />
          }
        >
          <Route
            path="/"
            element={<App />}
          />
          <Route
            path="/projects/:projectId"
            element={<ProjectRouteRedirect />}
          />
          <Route
            path="/projects/:projectId/write"
            element={<WritingPage workspaceView="write" />}
          />
          <Route
            path="/projects/:projectId/discuss"
            element={<DiscussionPage />}
          />
          <Route
            path="/projects/:projectId/notes"
            element={<DocumentWorkspacePage documentType="note" />}
          />
          <Route
            path="/projects/:projectId/outlines"
            element={<DocumentWorkspacePage documentType="outline" />}
          />
          <Route
            path="/projects/:projectId/changes"
            element={<PendingProjectChangesPage />}
          />
          <Route
            path="/projects/:projectId/world-info"
            element={<WorldInfoPage />}
          />
          <Route
            path="/projects/:projectId/characters"
            element={<CharactersPage />}
          />
          <Route
            path="/world-info"
            element={<WorldInfoPage />}
          />
          <Route
            path="/characters"
            element={<CharactersPage />}
          />
          <Route
            path="/prompt-chains"
            element={<PromptChainsPage />}
          />
          <Route
            path="/dashboard"
            element={
              <Suspense fallback={null}>
                <DashboardPage />
              </Suspense>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
