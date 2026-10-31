import "./page-loading-overlay.css";
/**
 * Page Loading Overlay
 *
 * 写作页加载骨架屏。
 */
import { Box, Flex, Skeleton } from "@radix-ui/themes";

interface PageLoadingOverlayProps {
  /** 是否显示 */
  isLoading: boolean;
}

export function PageLoadingOverlay({ isLoading }: PageLoadingOverlayProps) {
  if (!isLoading) {
    return null;
  }

  return (
    <Flex className="writing-page-loading-overlay page-loading-overlay__surface">
      <Box className="writing-page-loading-sidebar writing-page-loading-sidebar--left page-loading-overlay__navigation">
        <Flex
          px="3"
          py="3"
          pr="6"
          align="center"
          gap="2"
        >
          <Skeleton
            height="20px"
            width="72px"
          />
          <Skeleton
            height="14px"
            width="28px"
          />
        </Flex>

        <Box
          px="3"
          pb="3"
        >
          <Skeleton
            height="32px"
            width="100%"
            mb="3"
          />
          <Skeleton
            height="32px"
            width="100%"
          />
        </Box>

        <Box p="2">
          {[1, 2, 3, 4, 5].map((item) => (
            <Box
              key={item}
              p="3"
            >
              <Skeleton
                height="16px"
                width="70%"
                mb="2"
              />
              <Skeleton
                height="12px"
                width="45%"
              />
            </Box>
          ))}
        </Box>
      </Box>

      <Box className="writing-page-loading-editor page-loading-overlay__editor">
        <Flex
          className="writing-page-loading-editor-tabs page-loading-overlay__tabs"
          align="end"
          px="3"
          pt="2"
        >
          <Skeleton
            height="30px"
            width="148px"
          />
        </Flex>

        <Box className="writing-page-loading-editor-content page-loading-overlay__document">
          <Skeleton
            height="28px"
            width="42%"
            mb="6"
          />
          <Flex
            direction="column"
            gap="4"
          >
            <Skeleton
              height="18px"
              width="100%"
            />
            <Skeleton
              height="18px"
              width="96%"
            />
            <Skeleton
              height="18px"
              width="88%"
            />
            <Skeleton
              height="18px"
              width="92%"
            />
            <Skeleton
              height="18px"
              width="64%"
            />
          </Flex>
        </Box>
      </Box>

      <Box className="writing-page-loading-sidebar writing-page-loading-sidebar--right page-loading-overlay__assistant">
        <Box p="4">
          <Skeleton
            height="22px"
            width="96px"
            mb="5"
          />
          <Flex
            direction="column"
            gap="3"
          >
            <Skeleton
              height="36px"
              width="100%"
            />
            <Skeleton
              height="36px"
              width="100%"
            />
            <Skeleton
              height="96px"
              width="100%"
            />
          </Flex>
        </Box>
      </Box>
    </Flex>
  );
}
