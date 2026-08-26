import { Box, Button, Flex, Text } from "@radix-ui/themes";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import {
  BookOpen,
  ChartNoAxesCombined,
  ChevronDown,
  ChevronRight,
  FileText,
  FileClock,
  Globe,
  LibraryBig,
  MessageCircle,
  ListTree,
  UserRound,
  Workflow,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useParams } from "react-router";

import { toast } from "@/components";
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
const LAST_PROJECT_ID_KEY = "openfic.appSidebar.lastProjectId";

export function AppSidebar() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const { isMobile, isSidebarOpen, closeSidebar, openSettings } = useAppShell();

  const [isExpanded, setIsExpanded] = useState(false);
  const [isProjectListOpen, setIsProjectListOpen] = useState(false);
  const [isLogoHovered, setIsLogoHovered] = useState(false);
  const [lastProjectId, setLastProjectId] = useState<string | null>(() =>
    window.localStorage.getItem(LAST_PROJECT_ID_KEY),
  );
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
  });
  const projects = useMemo(() => projectsData?.items ?? [], [projectsData?.items]);
  const sidebarProjectId = projectId ?? lastProjectId;

  useEffect(() => {
    if (!projectId) return;
    setLastProjectId(projectId);
    window.localStorage.setItem(LAST_PROJECT_ID_KEY, projectId);
  }, [projectId]);

  useEffect(() => {
    if (!projectsData || !lastProjectId) return;
    if (projects.some((project) => project.id === lastProjectId)) return;
    setLastProjectId(null);
    window.localStorage.removeItem(LAST_PROJECT_ID_KEY);
  }, [lastProjectId, projects, projectsData]);

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
    const items: AppSidebarNavItem[] = [];

    if (sidebarProjectId) {
      items.push(
        {
          label: t("topbar.writing"),
          href: `/projects/${sidebarProjectId}/write`,
          icon: BookOpen,
          active: pathname === `/projects/${sidebarProjectId}/write`,
        },
        {
          label: t("sidebar.discuss"),
          href: `/projects/${sidebarProjectId}/discuss`,
          icon: MessageCircle,
          active: pathname === `/projects/${sidebarProjectId}/discuss`,
        },
        {
          label: t("topbar.workspace"),
          href: `/projects/${sidebarProjectId}/world-info`,
          icon: Globe,
          active: pathname === `/projects/${sidebarProjectId}/world-info`,
        },
        {
          label: t("topbar.characters"),
          href: `/projects/${sidebarProjectId}/characters`,
          icon: UserRound,
          active: pathname === `/projects/${sidebarProjectId}/characters`,
        },
        {
          label: t("sidebar.outlines"),
          href: `/projects/${sidebarProjectId}/outlines`,
          icon: ListTree,
          active: pathname === `/projects/${sidebarProjectId}/outlines`,
        },
        {
          label: t("sidebar.notes"),
          href: `/projects/${sidebarProjectId}/notes`,
          icon: FileText,
          active: pathname === `/projects/${sidebarProjectId}/notes`,
        },
        {
          label: t("pendingProjectChanges.navLabel"),
          href: `/projects/${sidebarProjectId}/changes`,
          icon: FileClock,
          active: pathname === `/projects/${sidebarProjectId}/changes`,
        },
      );
    }

    return items;
  }, [location.pathname, sidebarProjectId, t]);

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
    ["write", "discuss", "world-info", "characters", "outlines", "notes", "changes"].find(
      (section) => location.pathname.endsWith(`/${section}`),
    ) ?? "write";

  const handleProjectChange = useCallback(
    (nextProjectId: string) => {
      setLastProjectId(nextProjectId);
      window.localStorage.setItem(LAST_PROJECT_ID_KEY, nextProjectId);
      navigate(`/projects/${nextProjectId}/${projectSection}`);
      setIsProjectListOpen(false);
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

              <Flex
                align="center"
                width="100%"
                mb="1"
                className="app-sidebar-bookshelf-row"
                data-active={location.pathname === "/" ? "true" : "false"}
              >
                <button
                  type="button"
                  className="app-sidebar-bookshelf-main"
                  onClick={navigateToProjects}
                  aria-current={location.pathname === "/" ? "page" : undefined}
                >
                  <Flex
                    align="center"
                    justify="center"
                    width="40px"
                    height="40px"
                  >
                    <LibraryBig size={20} />
                  </Flex>
                  {(isMobile || isExpanded) && (
                    <Text
                      size="2"
                      weight={location.pathname === "/" ? "bold" : "medium"}
                    >
                      {t("sidebar.bookshelf")}
                    </Text>
                  )}
                </button>
                {(isMobile || isExpanded) && (
                  <button
                    type="button"
                    className="app-sidebar-bookshelf-toggle"
                    aria-label={t("topbar.currentProject")}
                    aria-expanded={isProjectListOpen}
                    onClick={() => setIsProjectListOpen((open) => !open)}
                  >
                    {isProjectListOpen ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                  </button>
                )}
              </Flex>

              {(isMobile || isExpanded) && isProjectListOpen && (
                <Flex
                  direction="column"
                  gap="1"
                  mb="2"
                  pl="5"
                  width="100%"
                >
                  {projects.map((project) => (
                    <Button
                      key={project.id}
                      variant={project.id === projectId ? "soft" : "ghost"}
                      color="gray"
                      size="1"
                      onClick={() => handleProjectChange(project.id)}
                      style={{ width: "100%", justifyContent: "flex-start" }}
                    >
                      <Text truncate>{project.title}</Text>
                    </Button>
                  ))}
                </Flex>
              )}

              <SidebarNav
                items={navItems}
                isExpanded={isMobile || isExpanded}
              />

              <Flex
                mt="auto"
                direction="column"
                gap="1"
                width="100%"
              >
                <SidebarNav
                  items={toolNavItems}
                  isExpanded={isMobile || isExpanded}
                />
                <SidebarActions
                  isExpanded={isMobile || isExpanded}
                  settingsLabel={t("topbar.settings")}
                  onOpenSettings={handleOpenSettings}
                />
              </Flex>
            </Flex>
          </MotionBox>
        )}
      </AnimatePresence>
    </>
  );
}
