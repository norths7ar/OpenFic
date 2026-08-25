import { Box, Button, Flex } from "@radix-ui/themes";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import {
  BookOpen,
  ChartNoAxesCombined,
  Database,
  FileText,
  FileClock,
  Globe,
  LibraryBig,
  MessageCircle,
  UserRound,
  Workflow,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useParams } from "react-router";

import { toast } from "@/components";
import { LabeledSelect } from "@/components/select";
import { ProjectDataDialog } from "@/features/projects/components/project-data-dialog";
import { fetchProject, fetchProjects } from "@/lib/api-client";

import { useAppShell } from "./app-shell-context";
import {
  SIDEBAR_COLLAPSED_WIDTH,
  SIDEBAR_EXPANDED_WIDTH,
  type AppSidebarNavItem,
} from "./app-sidebar.constants";
import { SidebarActions } from "./sidebar-actions";
import { SidebarBrand } from "./sidebar-brand";
import { SidebarNav } from "./sidebar-nav";

const MotionBox = motion.create(Box);
const MotionFlex = motion.create(Flex);

export function AppSidebar() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const { isMobile, isSidebarOpen, closeSidebar, openSettings } = useAppShell();

  const [isExpanded, setIsExpanded] = useState(false);
  const [isProjectDataOpen, setIsProjectDataOpen] = useState(false);
  const [isLogoHovered, setIsLogoHovered] = useState(false);
  const logoPointerInsideRef = useRef(false);
  const prevPathnameRef = useRef(location.pathname);

  const sidebarWidth = isMobile
    ? SIDEBAR_EXPANDED_WIDTH
    : isExpanded
      ? SIDEBAR_EXPANDED_WIDTH
      : SIDEBAR_COLLAPSED_WIDTH;

  useEffect(() => {
    document.documentElement.style.setProperty(
      "--app-sidebar-width",
      `${isMobile ? 0 : sidebarWidth}px`,
    );
  }, [isMobile, sidebarWidth]);

  useEffect(() => {
    if (isMobile && isSidebarOpen && prevPathnameRef.current !== location.pathname) {
      closeSidebar();
    }

    prevPathnameRef.current = location.pathname;
  }, [closeSidebar, isMobile, isSidebarOpen, location.pathname]);

  const { data: projectsData } = useQuery({
    queryKey: ["projects", "app-sidebar"],
    queryFn: () => fetchProjects({ page: 1, pageSize: 100 }),
    enabled: !!projectId,
  });
  const projects = projectsData?.items ?? [];

  const { error: currentProjectError } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => fetchProject(projectId!),
    enabled: !!projectId,
  });

  useEffect(() => {
    if (!projectId || !axios.isAxiosError(currentProjectError)) return;
    if (currentProjectError.response?.status !== 404) return;

    toast.error(t("projects.projectUnavailable"));
    navigate("/", { replace: true });
  }, [currentProjectError, navigate, projectId, t]);

  const navItems = useMemo<AppSidebarNavItem[]>(() => {
    const pathname = location.pathname;
    const items: AppSidebarNavItem[] = [
      {
        label: t("sidebar.bookshelf"),
        href: "/",
        icon: LibraryBig,
        active: pathname === "/",
      },
    ];

    if (projectId) {
      items.push(
        {
          label: t("topbar.writing"),
          href: `/projects/${projectId}/write`,
          icon: BookOpen,
          active: pathname === `/projects/${projectId}/write`,
        },
        {
          label: t("sidebar.discuss"),
          href: `/projects/${projectId}/discuss`,
          icon: MessageCircle,
          active: pathname === `/projects/${projectId}/discuss`,
        },
        {
          label: t("topbar.workspace"),
          href: `/projects/${projectId}/world-info`,
          icon: Globe,
          active: pathname === `/projects/${projectId}/world-info`,
        },
        {
          label: t("topbar.characters"),
          href: `/projects/${projectId}/characters`,
          icon: UserRound,
          active: pathname === `/projects/${projectId}/characters`,
        },
        {
          label: t("sidebar.notes"),
          href: `/projects/${projectId}/notes`,
          icon: FileText,
          active: pathname === `/projects/${projectId}/notes`,
        },
        {
          label: t("pendingProjectChanges.navLabel"),
          href: `/projects/${projectId}/changes`,
          icon: FileClock,
          active: pathname === `/projects/${projectId}/changes`,
        },
      );
    }

    return items;
  }, [location.pathname, projectId, t]);

  const toolNavItems = useMemo<AppSidebarNavItem[]>(
    () => [
      {
        label: t("topbar.promptChains"),
        href: "/prompt-chains",
        icon: Workflow,
        active: location.pathname.startsWith("/prompt-chains"),
      },
      {
        label: t("dashboard.title"),
        href: "/dashboard",
        icon: ChartNoAxesCombined,
        active: location.pathname.startsWith("/dashboard"),
      },
    ],
    [location.pathname, t],
  );

  const toggleExpanded = useCallback(() => {
    if (isMobile) {
      closeSidebar();
      return;
    }

    logoPointerInsideRef.current = false;
    setIsLogoHovered(false);
    setIsExpanded((prev) => !prev);
  }, [closeSidebar, isMobile]);

  const handleLogoPointerEnter = useCallback(() => {
    logoPointerInsideRef.current = true;
    if (!isExpanded) {
      setIsLogoHovered(true);
    }
  }, [isExpanded]);

  const handleLogoPointerLeave = useCallback(() => {
    logoPointerInsideRef.current = false;
    setIsLogoHovered(false);
  }, []);

  const handleLogoPointerMove = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      if (!isExpanded && logoPointerInsideRef.current) {
        const { left, right, top, bottom } = event.currentTarget.getBoundingClientRect();
        const isInside =
          event.clientX >= left &&
          event.clientX <= right &&
          event.clientY >= top &&
          event.clientY <= bottom;

        if (isInside && !isLogoHovered) {
          setIsLogoHovered(true);
        }
      }
    },
    [isExpanded, isLogoHovered],
  );

  const navigateToProjects = useCallback(() => {
    navigate("/");
  }, [navigate]);

  const handleOpenSettings = useCallback(() => {
    if (isMobile) {
      closeSidebar();
    }
    openSettings();
  }, [closeSidebar, isMobile, openSettings]);

  const projectSection =
    ["write", "discuss", "world-info", "characters", "notes", "changes"].find((section) =>
      location.pathname.endsWith(`/${section}`),
    ) ?? "write";

  const handleProjectChange = useCallback(
    (nextProjectId: string) => {
      navigate(`/projects/${nextProjectId}/${projectSection}`);
    },
    [navigate, projectSection],
  );

  return (
    <>
      <AnimatePresence initial={false}>
        {isMobile && isSidebarOpen && (
          <motion.div
            key="mobile-sidebar-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: "var(--app-status-bar-height)",
              background: "rgba(0, 0, 0, 0.36)",
              zIndex: 99,
            }}
            onClick={closeSidebar}
          />
        )}
      </AnimatePresence>

      <AnimatePresence initial={false}>
        {(!isMobile || isSidebarOpen) && (
          <MotionBox
            key={isMobile ? "mobile-sidebar" : "desktop-sidebar"}
            position="fixed"
            top="0"
            left="0"
            bottom="var(--app-status-bar-height)"
            initial={isMobile ? { x: -SIDEBAR_EXPANDED_WIDTH } : false}
            animate={
              isMobile ? { x: 0, width: SIDEBAR_EXPANDED_WIDTH } : { x: 0, width: sidebarWidth }
            }
            exit={isMobile ? { x: -SIDEBAR_EXPANDED_WIDTH } : undefined}
            transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            style={{
              borderRight: "1px solid var(--gray-a5)",
              background: "color-mix(in srgb, var(--color-background) 92%, transparent)",
              backdropFilter: "blur(12px)",
              zIndex: 100,
              overflow: "hidden",
              boxShadow: isMobile ? "var(--shadow-5)" : undefined,
              clipPath: isMobile ? "inset(0 -64px 0 0)" : undefined,
            }}
          >
            <Flex
              direction="column"
              height="100%"
              p="3"
            >
              <SidebarBrand
                isExpanded={isMobile || isExpanded}
                isHovered={isLogoHovered}
                expandLabel={t("topbar.expand")}
                projectsLabel={t("sidebar.bookshelf")}
                collapseLabel={t("topbar.collapse")}
                onToggleExpanded={toggleExpanded}
                onNavigateHome={navigateToProjects}
                onPointerEnter={handleLogoPointerEnter}
                onPointerLeave={handleLogoPointerLeave}
                onPointerMove={handleLogoPointerMove}
              />

              <Box
                style={{
                  width: "100%",
                  height: 13,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "flex-start",
                  margin: "6px 0",
                  flexShrink: 0,
                }}
              >
                <MotionBox
                  initial={false}
                  animate={{
                    width: isMobile || isExpanded ? SIDEBAR_EXPANDED_WIDTH - 40 : 32,
                    marginLeft: isMobile || isExpanded ? 8 : 4,
                  }}
                  transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
                  style={{
                    height: 1,
                    background: "var(--gray-a5)",
                  }}
                />
              </Box>

              {projectId && (isMobile || isExpanded) && (
                <Box
                  mb="2"
                  width="100%"
                >
                  <LabeledSelect
                    label={t("topbar.currentProject")}
                    value={projectId}
                    options={projects.map((project) => ({
                      value: project.id,
                      label: project.title,
                    }))}
                    onChange={handleProjectChange}
                    disabled={projects.length === 0}
                    triggerStyle={{ width: "100%" }}
                    placeholder={t("topbar.currentProject")}
                  />
                  <Button
                    variant="ghost"
                    size="1"
                    onClick={() => setIsProjectDataOpen(true)}
                    style={{ width: "100%", justifyContent: "flex-start", marginTop: 4 }}
                  >
                    <Database size={15} />
                    {t("projectData.open")}
                  </Button>
                </Box>
              )}

              <SidebarNav
                items={navItems}
                isExpanded={isMobile || isExpanded}
              />

              <Box mt="auto">
                <SidebarNav
                  items={toolNavItems}
                  isExpanded={isMobile || isExpanded}
                />
              </Box>

              <MotionFlex
                layout
                mt="auto"
                direction={isMobile || isExpanded ? "row" : "column"}
                align="center"
                justify={isMobile || isExpanded ? "end" : "center"}
                gap="1"
                width="100%"
                transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
              >
                <SidebarActions
                  isExpanded={isMobile || isExpanded}
                  settingsLabel={t("topbar.settings")}
                  onOpenSettings={handleOpenSettings}
                />
              </MotionFlex>
            </Flex>
          </MotionBox>
        )}
      </AnimatePresence>

      {projectId && (
        <ProjectDataDialog
          open={isProjectDataOpen}
          projectId={projectId}
          onOpenChange={setIsProjectDataOpen}
        />
      )}
    </>
  );
}
