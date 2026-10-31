import { Button, Flex, Text } from "@radix-ui/themes";
import { useTranslation } from "react-i18next";

export function QueryError({
  onRetry,
  isRetrying = false,
}: {
  onRetry: () => void;
  isRetrying?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <Flex
      direction="column"
      align="center"
      justify="center"
      gap="3"
      p="5"
      role="alert"
    >
      <Text color="red">{t("common.error")}</Text>
      <Button
        onClick={onRetry}
        disabled={isRetrying}
      >
        {t("common.retryRequest")}
      </Button>
    </Flex>
  );
}
