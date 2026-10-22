/// <reference types="vite-plus/client" />

import { Theme } from "@radix-ui/themes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18next from "i18next";
import { createRoot } from "react-dom/client";
import { I18nextProvider, initReactI18next } from "react-i18next";
import { MemoryRouter } from "react-router";

import { compareBodyDetails } from "../src/features/pending-project-changes/components/body-diff";
import { BodyDiffMarkdown } from "../src/features/pending-project-changes/components/body-diff-markdown";
import { PendingProjectChangesPanel } from "../src/features/pending-project-changes/components/pending-project-changes-panel";
import en from "../src/i18n/locales/en.json";

import "@radix-ui/themes/styles.css";

// Mount production components and providers; only HTTP is replaced by the browser test.
await i18next.use(initReactI18next).init({
  lng: "en",
  fallbackLng: "en",
  resources: { en: { translation: en } },
});
const params = new URLSearchParams(location.search);
const before = params.get("before") ?? "";
const after = params.get("after") ?? "";
const comparison = compareBodyDetails(before, after);
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

createRoot(document.getElementById("root")!).render(
  <I18nextProvider i18n={i18next}>
    <Theme>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          {params.get("panel") ? (
            <PendingProjectChangesPanel projectId="gap-project" />
          ) : (
            <>
              <section data-testid="before">
                <BodyDiffMarkdown
                  content={before}
                  changes={comparison.before}
                  ranges={comparison.beforeRanges}
                  side="before"
                />
              </section>
              <section data-testid="after">
                <BodyDiffMarkdown
                  content={after}
                  changes={comparison.after}
                  ranges={comparison.afterRanges}
                  side="after"
                />
              </section>
            </>
          )}
        </MemoryRouter>
      </QueryClientProvider>
    </Theme>
  </I18nextProvider>,
);
